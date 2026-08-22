import os
import selectors
import socket
import tempfile
import time
import unittest

import blingmud
import server_runtime


class FakeClock(object):
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class SelectorSocketpairIntegrationTests(unittest.TestCase):
    def setUp(self):
        probe_reader, probe_writer = socket.socketpair()

        try:
            probe_writer.sendall(b"x")

            if probe_reader.recv(1) != b"x":
                self.skipTest("local socketpair probe did not round-trip")
        except PermissionError:
            self.skipTest("sandbox does not permit local socketpair writes")
        finally:
            probe_reader.close()
            probe_writer.close()

        self.clock = FakeClock(100.0)
        self.server = server_runtime.SelectorMudServer(
            ("unused", 0),
            lambda server, connection: None,
            time_source=self.clock
        )
        self.server_socket, self.client_socket = socket.socketpair()
        self.server_socket.setblocking(False)
        self.client_socket.setblocking(False)
        self.connection = server_runtime.SelectorConnection(
            self.server,
            self.server_socket,
            ("local-socketpair", 0),
            self.clock
        )

        with self.server.connections_lock:
            self.server.connections.add(self.connection)

        self.server.selector.register(
            self.server_socket,
            selectors.EVENT_READ,
            self.connection
        )
        self.output = bytearray()
        self.original_database = None
        self.database_path = None

    def tearDown(self):
        try:
            player = None

            if self.connection.session is not None:
                player = self.connection.session.player

            if player is not None:
                with blingmud.SESSIONS_LOCK:
                    blingmud.SESSIONS.pop(player.name.lower(), None)

                if player.room is not None:
                    player.room.leave(player, announce=False)
        finally:
            try:
                self.server.server_close()
            finally:
                self.client_socket.close()

                if self.original_database is not None:
                    blingmud.USERS_DB = self.original_database

                if self.database_path is not None:
                    os.unlink(self.database_path)

    def _read_available_output(self):
        while True:
            try:
                data = self.client_socket.recv(65536)
            except BlockingIOError:
                return

            if not data:
                return

            self.output.extend(data)

    def _pump_until(self, predicate, timeout=1.5):
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            self.server.serve_once(0.01)
            self._read_available_output()

            if predicate():
                return

        self.fail("selector integration condition did not complete in time")

    def test_real_readiness_drives_fragmented_telnet_input_and_output(self):
        session = blingmud.Session(
            self.connection,
            self.connection.address,
            blingmud.WORLD
        )
        self.connection.attach_session(session)
        self.connection.authenticated = True
        session.prompt("> ", maximum_length=32)
        self.client_socket.sendall(bytes((server_runtime.IAC,)))
        self.client_socket.sendall(bytes((server_runtime.WILL, 1)))
        self.client_socket.sendall(b"fab")
        self.server.serve_once(0.05)
        self.client_socket.sendall(b"ulous\r\n")
        self._pump_until(lambda: not self.connection.input_lines.empty())

        self.assertEqual(session.read_line(maximum_length=32), "fabulous")
        self._pump_until(lambda: not self.connection.has_output())
        self.assertIn(b"> ", self.output)
        self.assertIn(b"fabulous", self.output)

    def test_selector_auth_pool_hides_password_and_promotes_once(self):
        descriptor, self.database_path = tempfile.mkstemp(
            prefix="blingmud-selector-",
            suffix=".sqlite"
        )
        os.close(descriptor)
        self.original_database = blingmud.USERS_DB
        blingmud.USERS_DB = self.database_path
        blingmud.init_user_database()
        password = "a long local socketpair password"
        blingmud.create_user("SocketPairUser", password)
        session = blingmud.Session(
            self.connection,
            self.connection.address,
            blingmud.WORLD
        )
        gameplay_starts = []
        session.start_gameplay_worker = lambda: gameplay_starts.append(
            session
        ) or True
        controller = blingmud.PreAuthController(
            self.server,
            self.connection,
            session
        )
        self.connection.auth_controller = controller
        controller.start()
        self.client_socket.sendall(b"SocketPairUser\r\n")
        self._pump_until(
            lambda: controller.state == controller.STATE_PASSWORD
        )
        self.client_socket.sendall(password.encode("utf-8") + b"\r\n")
        self._pump_until(lambda: self.connection.authenticated)
        self.server.serve_once(0.01)
        self._read_available_output()

        self.assertEqual(gameplay_starts, [session])
        self.assertIs(blingmud.SESSIONS["socketpairuser"], session)
        self.assertNotIn(password.encode("utf-8"), self.output)
        self.assertIn(b"Password: ", self.output)

    def test_graceful_drain_and_fake_clock_idle_close_use_selector(self):
        self.connection.sendall(b"final notice\r\n")
        self.server.request_graceful_shutdown(1.0)
        self._pump_until(lambda: self.server.stopping.is_set())

        self.assertEqual(self.server.graceful_shutdown_deadline, 101.0)
        self.assertIn(b"final notice", self.output)
        self.assertFalse(self.connection.has_output())

        self.server.stopping.clear()
        self.server.graceful_shutdown_deadline = None
        self.clock.now += server_runtime.PREAUTH_IDLE_SECONDS + 1.0
        self.server.serve_once(0.0)
        self.assertTrue(self.connection.closed)
        self.assertNotIn(self.connection, self.server.connections)


if __name__ == "__main__":
    unittest.main()
