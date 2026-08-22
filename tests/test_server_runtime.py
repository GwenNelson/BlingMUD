import os
import io
import sys
import tempfile
import threading
import time
import unittest

import blingmud
import server_runtime


class FakeClock(object):
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeSocket(object):
    def fileno(self):
        return 123


class FakeConnectionOwner(object):
    def __init__(self):
        self.close_requests = []
        self.wake_count = 0

    def request_close(self, connection):
        self.close_requests.append(connection)

    def wake(self):
        self.wake_count += 1


class AdmissionConnection(object):
    def __init__(self, ip_address, authenticated=False, closed=False):
        self.ip_address = ip_address
        self.authenticated = authenticated
        self.closed = closed


class ImmediateAuthPool(object):
    def submit(self, function, callback, *arguments):
        try:
            result = function(*arguments)
        except Exception as error:
            callback(None, error)
        else:
            callback(result, None)

        return True


class FakeAuthServer(object):
    def __init__(self, time_source=None):
        self.auth_pool = ImmediateAuthPool()
        self.rate_limiter = server_runtime.AuthRateLimiter(time_source)
        self.promotions = []

    def promote_authenticated(self, connection):
        connection.authenticated = True
        self.promotions.append(connection)
        return True


class RuntimeConfigurationTests(unittest.TestCase):
    def test_listener_defaults_remain_public_and_port_is_configurable(self):
        self.assertEqual(
            blingmud.configured_server_address({}),
            ("0.0.0.0", 4000)
        )
        self.assertEqual(
            blingmud.configured_server_address({
                "BLINGMUD_HOST": "127.0.0.1",
                "BLINGMUD_PORT": "4444"
            }),
            ("127.0.0.1", 4444)
        )

    def test_invalid_listener_configuration_fails_closed(self):
        invalid_environments = (
            {"BLINGMUD_HOST": ""},
            {"BLINGMUD_HOST": None},
            {"BLINGMUD_PORT": "not-a-number"},
            {"BLINGMUD_PORT": "0"},
            {"BLINGMUD_PORT": "65536"}
        )

        for environment in invalid_environments:
            with self.assertRaises(ValueError):
                blingmud.configured_server_address(environment)

    def test_broken_maintenance_callback_does_not_block_later_work(self):
        runtime = object.__new__(server_runtime.SelectorMudServer)
        calls = []

        def broken():
            raise RuntimeError("broken maintenance")

        runtime.maintenance_callbacks = [broken, lambda: calls.append("ok")]
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            runtime._run_maintenance()
            warning = sys.stderr.getvalue()
        finally:
            sys.stderr = original_stderr

        self.assertEqual(calls, ["ok"])
        self.assertIn("maintenance callback failed", warning)


class ConnectionAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.admission = server_runtime.ConnectionAdmission()

    def test_per_ip_limit_is_enforced(self):
        connections = [
            AdmissionConnection("192.0.2.10")
            for unused in range(server_runtime.PER_IP_CONNECTION_LIMIT)
        ]

        reason = self.admission.rejection_reason(
            connections,
            "192.0.2.10"
        )

        self.assertIn("address", reason)

    def test_preauth_and_authenticated_limits_are_separate(self):
        preauth = [
            AdmissionConnection("192.0.2.{0}".format(index))
            for index in range(server_runtime.PREAUTH_CONNECTION_LIMIT)
        ]
        authenticated = [
            AdmissionConnection(
                "198.51.100.{0}".format(index),
                authenticated=True
            )
            for index in range(
                server_runtime.AUTHENTICATED_CONNECTION_LIMIT
            )
        ]

        self.assertIn(
            "login",
            self.admission.rejection_reason(preauth, "203.0.113.1")
        )
        self.assertIn(
            "authenticated",
            self.admission.rejection_reason(
                authenticated,
                "203.0.113.1"
            )
        )

    def test_closed_connections_do_not_consume_limits(self):
        connections = [
            AdmissionConnection("192.0.2.10", closed=True)
            for unused in range(server_runtime.TOTAL_CONNECTION_LIMIT)
        ]

        self.assertIsNone(
            self.admission.rejection_reason(connections, "192.0.2.10")
        )


class AuthRateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(1000.0)
        self.limiter = server_runtime.AuthRateLimiter(self.clock)

    def test_five_failures_block_only_the_ip_and_account_pair(self):
        for unused in range(server_runtime.AUTH_FAILURE_LIMIT):
            self.limiter.record_authentication_failure(
                "192.0.2.1",
                "Player"
            )

        self.assertFalse(
            self.limiter.authentication_allowed("192.0.2.1", "player")
        )
        self.assertTrue(
            self.limiter.authentication_allowed("192.0.2.2", "player")
        )
        self.assertTrue(
            self.limiter.authentication_allowed("192.0.2.1", "other")
        )

        self.clock.now += server_runtime.AUTH_FAILURE_WINDOW_SECONDS + 1
        self.assertTrue(
            self.limiter.authentication_allowed("192.0.2.1", "player")
        )

    def test_success_can_clear_failure_history(self):
        self.limiter.record_authentication_failure("192.0.2.1", "Player")
        self.limiter.clear_authentication_failures("192.0.2.1", "player")

        self.assertTrue(
            self.limiter.authentication_allowed("192.0.2.1", "Player")
        )

    def test_only_three_creation_slots_exist_per_hour(self):
        for unused in range(server_runtime.ACCOUNT_CREATION_LIMIT):
            self.assertTrue(
                self.limiter.claim_account_creation("192.0.2.1")
            )

        self.assertFalse(
            self.limiter.claim_account_creation("192.0.2.1")
        )

        self.limiter.release_account_creation("192.0.2.1")
        self.assertTrue(
            self.limiter.claim_account_creation("192.0.2.1")
        )


class BoundedWorkerPoolTests(unittest.TestCase):
    def test_workers_and_pending_queue_have_a_hard_limit(self):
        release = threading.Event()
        callbacks = []
        pool = server_runtime.BoundedWorkerPool(1, 1)

        def blocked(value):
            self.assertTrue(release.wait(1.0))
            return value

        def completed(result, error):
            callbacks.append((result, error))

        try:
            self.assertTrue(pool.submit(blocked, completed, "first"))
            self.assertTrue(pool.submit(blocked, completed, "second"))
            self.assertFalse(pool.submit(blocked, completed, "third"))
            release.set()

            deadline = time.monotonic() + 1.0

            while len(callbacks) < 2 and time.monotonic() < deadline:
                pool.drain()
                time.sleep(0.005)

            self.assertEqual(
                sorted(result for result, error in callbacks),
                ["first", "second"]
            )
            self.assertTrue(all(error is None for result, error in callbacks))
        finally:
            release.set()
            pool.shutdown()


class SelectorConnectionTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(50.0)
        self.owner = FakeConnectionOwner()
        self.connection = server_runtime.SelectorConnection(
            self.owner,
            FakeSocket(),
            ("192.0.2.1", 1234),
            self.clock
        )
        self.session = blingmud.Session(
            self.connection,
            self.connection.address,
            blingmud.WORLD
        )
        self.connection.attach_session(self.session)

    def test_selector_feeds_session_line_queue_without_socket_recv(self):
        self.connection.authenticated = True
        self.session.prompt("> ", maximum_length=4)
        self.connection.feed_received(b"abcdef\r\n")

        self.assertEqual(self.session.read_line(maximum_length=4), "abcd")
        self.assertIn(b"abcd", self.connection.peek_output())

    def test_hidden_selector_input_is_not_echoed(self):
        self.connection.authenticated = True
        self.session.prompt("Password: ", hidden=True)
        self.connection.feed_received(b"secret password\r\x00")

        self.assertEqual(
            self.session.read_line(hidden=True),
            "secret password"
        )
        self.assertNotIn(b"secret password", self.connection.peek_output())

    def test_tab_event_reaches_sequential_session_before_line(self):
        tabs = []
        self.connection.authenticated = True
        self.session.handle_tab_completion = lambda text: tabs.append(text)
        self.connection.feed_received(b"/lo\tok\n")

        self.assertEqual(self.session.read_line(), "/look")
        self.assertEqual(tabs, ["/lo"])

    def test_input_configuration_does_not_wait_for_session_send_lock(self):
        completed = threading.Event()

        def configure():
            self.connection.configure_input(True, 12)
            completed.set()

        worker = threading.Thread(target=configure, daemon=True)

        with self.session.send_lock:
            worker.start()
            worker.join(0.5)

        self.assertFalse(worker.is_alive())
        self.assertTrue(completed.is_set())

    def test_command_completion_replaces_matching_live_input(self):
        self.connection.authenticated = True
        self.session.player = blingmud.Player("Completer")
        self.session.player.session = self.session
        blingmud.WORLD.starting_room.enter(
            self.session.player,
            announce=False
        )
        self.session.prompt("> ")
        self.connection.feed_received(b"/lo")

        try:
            self.session.handle_tab_completion("/lo")

            self.assertEqual(
                self.connection.input_parser.current_text,
                "/look "
            )
            self.assertEqual(self.session.current_input, "/look ")
        finally:
            blingmud.WORLD.starting_room.leave(
                self.session.player,
                announce=False
            )

    def test_stale_tab_event_cannot_clobber_newer_input(self):
        self.connection.authenticated = True
        self.session.player = blingmud.Player("FastTyper")
        self.session.player.session = self.session
        blingmud.WORLD.starting_room.enter(
            self.session.player,
            announce=False
        )
        self.session.prompt("> ")
        self.connection.feed_received(b"/lo")
        stale_text = self.connection.input_parser.current_text
        self.connection.feed_received(b"ok")

        try:
            self.session.handle_tab_completion(stale_text)

            self.assertEqual(
                self.connection.input_parser.current_text,
                "/look"
            )
        finally:
            blingmud.WORLD.starting_room.leave(
                self.session.player,
                announce=False
            )

    def test_fragmented_telnet_negotiation_does_not_enter_input(self):
        self.connection.authenticated = True
        self.connection.feed_received(bytes((server_runtime.IAC,)))
        self.connection.feed_received(bytes((server_runtime.WILL, 1)))
        self.connection.feed_received(b"hello\n")

        self.assertEqual(self.connection.read_line(), "hello")

    def test_output_queue_overflow_requests_disconnect(self):
        with self.assertRaises(BufferError):
            self.connection.sendall(
                b"x" * (server_runtime.OUTPUT_QUEUE_LIMIT + 1)
            )

        self.assertEqual(self.owner.close_requests, [self.connection])
        self.assertLessEqual(
            len(self.connection.output_buffer),
            server_runtime.OUTPUT_QUEUE_LIMIT
        )

    def test_broken_preauth_handler_closes_only_its_connection(self):
        def broken_handler(line):
            raise RuntimeError("broken login state")

        self.connection.set_line_handler(broken_handler)
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            self.connection.feed_received(b"hello\n")
            warning = sys.stderr.getvalue()
        finally:
            sys.stderr = original_stderr

        self.assertEqual(self.owner.close_requests, [self.connection])
        self.assertIn("Pre-authentication input handler failed", warning)

    def test_input_queue_is_discarded_when_connection_closes(self):
        self.connection.authenticated = True
        self.connection.feed_received(b"stale command\n")
        self.connection.mark_closed()

        self.assertIsNone(self.connection.read_line())
        self.assertFalse(self.session.running)

    def test_preauth_and_authenticated_idle_actions_are_bounded(self):
        self.assertIsNone(self.connection.idle_action(169.0))
        self.assertEqual(self.connection.idle_action(170.0), "disconnect")

        self.connection.authenticated = True
        warning_at = (
            self.connection.last_input_at
            + server_runtime.AUTHENTICATED_IDLE_WARNING_SECONDS
        )
        disconnect_at = (
            self.connection.last_input_at
            + server_runtime.AUTHENTICATED_IDLE_DISCONNECT_SECONDS
        )

        self.assertEqual(self.connection.idle_action(warning_at), "warn")
        self.assertIsNone(self.connection.idle_action(warning_at + 1))
        self.assertEqual(
            self.connection.idle_action(disconnect_at),
            "disconnect"
        )


class SelectorAuthenticationTests(unittest.TestCase):
    def setUp(self):
        descriptor, self.database_path = tempfile.mkstemp()
        os.close(descriptor)
        self.original_database = blingmud.USERS_DB
        blingmud.USERS_DB = self.database_path
        blingmud.init_user_database()
        blingmud.create_user("SelectorUser", "a sufficiently long password")
        self.owner = FakeConnectionOwner()
        self.connection = server_runtime.SelectorConnection(
            self.owner,
            FakeSocket(),
            ("192.0.2.1", 1234)
        )
        self.server = FakeAuthServer()
        self.session = blingmud.Session(
            self.connection,
            self.connection.address,
            blingmud.WORLD
        )
        self.worker_started = []
        self.session.start_gameplay_worker = lambda: self.worker_started.append(
            self.session
        ) or True
        self.controller = blingmud.PreAuthController(
            self.server,
            self.connection,
            self.session
        )
        self.connection.auth_controller = self.controller
        self.controller.start()

    def tearDown(self):
        with blingmud.SESSIONS_LOCK:
            blingmud.SESSIONS.pop("selectoruser", None)

        blingmud.USERS_DB = self.original_database
        os.unlink(self.database_path)

    def test_only_authenticated_player_receives_gameplay_worker(self):
        self.assertEqual(self.worker_started, [])

        self.controller.on_line("SelectorUser")
        self.assertEqual(
            self.controller.state,
            blingmud.PreAuthController.STATE_PASSWORD
        )
        self.assertEqual(self.worker_started, [])

        self.controller.on_line("a sufficiently long password")

        self.assertTrue(self.connection.authenticated)
        self.assertIsNotNone(self.session.player)
        self.assertEqual(self.worker_started, [self.session])
        self.assertIs(
            blingmud.SESSIONS["selectoruser"],
            self.session
        )

    def test_fifth_bad_password_closes_after_bounded_output(self):
        self.controller.on_line("SelectorUser")

        for unused in range(server_runtime.AUTH_FAILURE_LIMIT):
            self.controller.on_line("wrong password")

        self.assertTrue(self.connection.close_after_output)
        self.assertFalse(self.connection.authenticated)
        self.assertEqual(self.worker_started, [])


if __name__ == "__main__":
    unittest.main()
