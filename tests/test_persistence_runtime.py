import os
import tempfile
import threading
import unittest

import blingmud
from core import Player, Room
from persistence_runtime import (
    AUTOSAVE_INTERVAL_SECONDS,
    AutosaveCoordinator,
    PersistenceWriter
)
from player_state import restore_player_state, serialize_player_state


class FakeClock(object):
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeSession(object):
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def save_if_changed(self, wait=False):
        self.calls += 1
        return self.results.pop(0)


class RecordingRequest(object):
    def __init__(self):
        self.shutdown_called = False
        self.close_called = False

    def sendall(self, data):
        pass

    def shutdown(self, how):
        self.shutdown_called = True

    def close(self):
        self.close_called = True


class StateWorld(object):
    def __init__(self):
        self.starting_room = Room("start", "Start", "A room.")
        self.rooms = {"start": self.starting_room}


class PersistenceWriterTests(unittest.TestCase):
    def test_pending_snapshots_for_one_player_are_coalesced_to_latest(self):
        blocking_started = threading.Event()
        release = threading.Event()
        writes = []

        def save(username, encoded_state):
            if username == "blocker":
                blocking_started.set()
                self.assertTrue(release.wait(1.0))

            writes.append((username, encoded_state))

        writer = PersistenceWriter(save, pending_key_limit=4)
        writer.start()

        try:
            writer.submit("blocker", "hold")
            self.assertTrue(blocking_started.wait(1.0))
            first = writer.submit("Player", "state one")
            second = writer.submit("player", "state two")
            release.set()

            self.assertTrue(writer.flush(1.0))
            self.assertTrue(first.wait(0.1))
            self.assertTrue(second.wait(0.1))
            self.assertEqual(
                writes,
                [("blocker", "hold"), ("player", "state two")]
            )
        finally:
            release.set()
            writer.shutdown(1.0)

    def test_pending_player_limit_rejects_growth(self):
        blocking_started = threading.Event()
        release = threading.Event()

        def save(username, encoded_state):
            blocking_started.set()
            self.assertTrue(release.wait(1.0))

        writer = PersistenceWriter(save, pending_key_limit=1)
        writer.start()

        try:
            writer.submit("in-flight", "one")
            self.assertTrue(blocking_started.wait(1.0))
            accepted = writer.submit("pending", "two")
            rejected = writer.submit("overflow", "three")

            self.assertFalse(rejected.wait(0.1))
            self.assertIn("full", str(rejected.error))
            release.set()
            self.assertTrue(accepted.wait(1.0))
        finally:
            release.set()
            writer.shutdown(1.0)

    def test_shutdown_returns_after_timeout_if_write_is_stuck(self):
        blocking_started = threading.Event()
        release = threading.Event()

        def save(username, encoded_state):
            blocking_started.set()
            release.wait(1.0)

        writer = PersistenceWriter(save)
        writer.start()
        writer.submit("Player", "state")
        self.assertTrue(blocking_started.wait(1.0))

        self.assertFalse(writer.shutdown(0.01))
        release.set()
        self.assertTrue(writer.shutdown(1.0))

    def test_failed_write_completes_receipt_without_killing_writer(self):
        attempts = []

        def save(username, encoded_state):
            attempts.append(encoded_state)

            if encoded_state == "bad":
                raise OSError("disk unavailable")

        writer = PersistenceWriter(save)
        writer.start()

        try:
            failed = writer.submit("Player", "bad")
            self.assertFalse(failed.wait(1.0))
            self.assertIn("disk unavailable", str(failed.error))

            succeeded = writer.submit("Player", "good")
            self.assertTrue(succeeded.wait(1.0))
            self.assertEqual(attempts, ["bad", "good"])
        finally:
            writer.shutdown(1.0)


class AutosaveCoordinatorTests(unittest.TestCase):
    def test_autosave_runs_every_sixty_seconds_and_counts_results(self):
        clock = FakeClock(100.0)
        changed = FakeSession(("queued",))
        unchanged = FakeSession(("unchanged",))
        busy = FakeSession(("busy",))
        failed = FakeSession(("failed",))
        coordinator = AutosaveCoordinator(
            lambda: [changed, unchanged, busy, failed],
            time_source=clock
        )

        self.assertFalse(coordinator.tick())
        clock.now += AUTOSAVE_INTERVAL_SECONDS
        self.assertTrue(coordinator.tick())

        self.assertEqual(changed.calls, 1)
        self.assertEqual(unchanged.calls, 1)
        self.assertEqual(busy.calls, 1)
        self.assertEqual(failed.calls, 1)
        self.assertEqual(coordinator.queued, 1)
        self.assertEqual(coordinator.unchanged, 1)
        self.assertEqual(coordinator.busy, 1)
        self.assertEqual(coordinator.failed, 1)
        self.assertFalse(coordinator.tick())


class SessionAutosaveTests(unittest.TestCase):
    def setUp(self):
        descriptor, self.database_path = tempfile.mkstemp()
        os.close(descriptor)
        self.original_database = blingmud.USERS_DB
        blingmud.USERS_DB = self.database_path
        blingmud.init_user_database()
        blingmud.create_user("Autosaver", "a sufficiently long password")
        self.world = StateWorld()

    def tearDown(self):
        with blingmud.SESSIONS_LOCK:
            blingmud.SESSIONS.pop("autosaver", None)

        blingmud.USERS_DB = self.original_database
        os.unlink(self.database_path)

    def _make_session(self, writer):
        session = blingmud.Session(
            RecordingRequest(),
            ("127.0.0.1", 0),
            self.world,
            persistence_writer=writer
        )
        player = Player("Autosaver")
        player.session = session
        session.player = player
        session.set_persisted_state(
            blingmud.load_user("Autosaver")["state_json"]
        )
        return session, player

    def test_unchanged_snapshot_is_not_written_and_change_is(self):
        writes = []
        writer = PersistenceWriter(
            lambda username, encoded: writes.append((username, encoded))
        )
        writer.start()
        session, player = self._make_session(writer)
        baseline = serialize_player_state(player)
        session.set_persisted_state(baseline)

        try:
            self.assertEqual(session.save_if_changed(), "unchanged")
            self.assertEqual(writes, [])

            player.fabulousness = 17
            self.assertEqual(session.save_if_changed(), "queued")
            self.assertTrue(writer.flush(1.0))
            self.assertEqual(len(writes), 1)
            self.assertEqual(session.save_if_changed(), "unchanged")
        finally:
            writer.shutdown(1.0)

    def test_periodic_save_skips_busy_gameplay_state_without_waiting(self):
        writer = PersistenceWriter(lambda username, encoded: None)
        writer.start()
        session, player = self._make_session(writer)
        player.fabulousness = 19
        locked = threading.Event()
        release = threading.Event()

        def hold_gameplay_state():
            with session.state_lock:
                locked.set()
                release.wait(1.0)

        holder = threading.Thread(target=hold_gameplay_state, daemon=True)
        holder.start()

        try:
            self.assertTrue(locked.wait(1.0))
            self.assertEqual(session.save_if_changed(wait=False), "busy")
        finally:
            release.set()
            holder.join(1.0)
            writer.shutdown(1.0)

        self.assertFalse(holder.is_alive())

    def test_failed_async_save_is_retried_on_next_pass(self):
        attempts = []

        def save(username, encoded):
            attempts.append(encoded)

            if len(attempts) == 1:
                raise OSError("temporary failure")

        writer = PersistenceWriter(save)
        writer.start()
        session, player = self._make_session(writer)
        player.fabulousness = 23

        try:
            self.assertEqual(
                session.save_if_changed(wait=True, timeout=1.0),
                "failed"
            )
            self.assertEqual(
                session.save_if_changed(wait=True, timeout=1.0),
                "queued"
            )
            self.assertEqual(len(attempts), 2)
        finally:
            writer.shutdown(1.0)

    def test_immediate_writer_rejection_does_not_poison_retry_state(self):
        writer = PersistenceWriter(lambda username, encoded: None)
        session, player = self._make_session(writer)
        player.fabulousness = 29

        self.assertEqual(session.save_if_changed(), "failed")
        self.assertEqual(
            session.last_submitted_state_json,
            session.persisted_state_json
        )

        writer.start()

        try:
            self.assertEqual(
                session.save_if_changed(wait=True, timeout=1.0),
                "queued"
            )
        finally:
            writer.shutdown(1.0)

    def test_disconnect_waits_for_final_snapshot_before_room_leave(self):
        writer = PersistenceWriter(blingmud.persist_user_state)
        writer.start()
        session, player = self._make_session(writer)
        player.fabulousness = 44
        self.world.starting_room.enter(player, announce=False)

        with blingmud.SESSIONS_LOCK:
            blingmud.SESSIONS["autosaver"] = session

        try:
            session.disconnect()

            restored = Player("Autosaver")
            room = restore_player_state(
                restored,
                blingmud.load_user("Autosaver")["state_json"],
                self.world
            )
            self.assertEqual(restored.fabulousness, 44)
            self.assertIs(room, self.world.starting_room)
            self.assertIsNone(player.room)
        finally:
            writer.shutdown(1.0)


if __name__ == "__main__":
    unittest.main()
