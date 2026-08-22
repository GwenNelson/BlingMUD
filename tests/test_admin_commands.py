import unittest

import blingmud
from core import COMMANDS, Player, Room


class RecordingRequest(object):
    def __init__(self):
        self.sent = []
        self.close_graces = []
        self.shutdown_called = False

    def sendall(self, data):
        self.sent.append(data)

    def request_close_after_output(self, grace):
        self.close_graces.append(grace)

    def shutdown(self, how):
        self.shutdown_called = True

    def close(self):
        pass


class FakeServerControl(object):
    def __init__(self):
        self.shutdown_graces = []

    def request_graceful_shutdown(self, grace):
        self.shutdown_graces.append(grace)

    def connection_snapshot(self):
        return {
            "total": 3,
            "preauth": 1,
            "authenticated": 2,
            "shutdown_pending": False
        }


class SmallWorld(object):
    def __init__(self):
        self.starting_room = Room("start", "Start", "A room.")
        self.rooms = {"start": self.starting_room}


class FakeWorldCoordinator(object):
    def __init__(self):
        self.calls = []

    def save_if_changed(self, wait=False, timeout=None):
        self.calls.append((wait, timeout))
        return "saved" if wait else "queued"

    def status_snapshot(self):
        return {"runs": 1, "last_error": None}


class AdminCommandTests(unittest.TestCase):
    def setUp(self):
        self.world = SmallWorld()
        self.server = FakeServerControl()
        self.admin_request = RecordingRequest()
        self.target_request = RecordingRequest()
        self.admin = blingmud.Session(
            self.admin_request,
            ("127.0.0.1", 1),
            self.world,
            server_control=self.server
        )
        self.target = blingmud.Session(
            self.target_request,
            ("127.0.0.1", 2),
            self.world,
            server_control=self.server
        )
        self.admin_player = Player("Administrator")
        self.target_player = Player("Target")
        self.admin_player.is_admin = True
        self.admin_player.session = self.admin
        self.target_player.session = self.target
        self.admin.player = self.admin_player
        self.target.player = self.target_player
        self.world.starting_room.enter(self.admin_player, announce=False)
        self.world.starting_room.enter(self.target_player, announce=False)
        self.original_world_coordinator = blingmud.WORLD_SAVE_COORDINATOR

        with blingmud.SESSIONS_LOCK:
            blingmud.SESSIONS["administrator"] = self.admin
            blingmud.SESSIONS["target"] = self.target

    def tearDown(self):
        blingmud.WORLD_SAVE_COORDINATOR = self.original_world_coordinator

        with blingmud.SESSIONS_LOCK:
            blingmud.SESSIONS.pop("administrator", None)
            blingmud.SESSIONS.pop("target", None)

        for player in (self.admin_player, self.target_player):
            if player.room is not None:
                player.room.leave(player, announce=False)

    def transcript(self, request):
        return b"".join(request.sent).decode("utf-8", "replace")

    def test_shutdown_requires_confirmation_and_announces_before_request(self):
        COMMANDS["shutdown"].execute(self.admin, "")
        self.assertEqual(self.server.shutdown_graces, [])
        self.assertIn("confirm", self.transcript(self.admin_request))

        COMMANDS["shutdown"].execute(self.admin, "now maintenance")
        self.assertEqual(self.server.shutdown_graces, [1.0])
        self.assertIn("maintenance", self.transcript(self.admin_request))
        self.assertIn("maintenance", self.transcript(self.target_request))

    def test_kick_is_bounded_and_requests_output_preserving_close(self):
        COMMANDS["kick"].execute(self.admin, "Target repeated soup crimes")
        self.assertFalse(self.target.running)
        self.assertEqual(self.target_request.close_graces, [1.0])
        self.assertIn("repeated soup crimes", self.transcript(self.target_request))
        self.assertIn("Kick requested", self.transcript(self.admin_request))

        self.target.running = True
        COMMANDS["kick"].execute(self.admin, "Target " + ("x" * 201))
        self.assertEqual(self.target_request.close_graces, [1.0])

    def test_closed_gameplay_worker_does_not_execute_one_queued_command(self):
        handled = []

        def close_during_read(*arguments, **keywords):
            self.target.running = False
            return "/bling"

        self.target.read_line = close_during_read
        self.target.handle_command = lambda line: handled.append(line)
        self.target.login_room = self.world.starting_room
        self.target._gameplay_loop()
        self.assertEqual(handled, [])

    def test_heal_uses_shared_clamped_health_api(self):
        self.target_player.health = 40
        COMMANDS["heal"].execute(self.admin, "Target 25")
        self.assertEqual(self.target_player.health, 65)
        COMMANDS["heal"].execute(self.admin, "Target full")
        self.assertEqual(self.target_player.health, 100)
        COMMANDS["heal"].execute(self.admin, "Missing")
        self.assertIn("not online", self.transcript(self.admin_request))

    def test_save_supports_target_world_and_nonblocking_all_pass(self):
        admin_calls = []
        target_calls = []
        self.admin.save_if_changed = lambda wait=False, timeout=None: (
            admin_calls.append((wait, timeout)) or "unchanged"
        )
        self.target.save_if_changed = lambda wait=False, timeout=None: (
            target_calls.append((wait, timeout)) or "queued"
        )
        world = FakeWorldCoordinator()
        blingmud.WORLD_SAVE_COORDINATOR = world

        COMMANDS["save"].execute(self.admin, "Target")
        self.assertEqual(target_calls, [(True, 2.0)])
        COMMANDS["save"].execute(self.admin, "world")
        self.assertEqual(world.calls, [(True, 2.0)])
        COMMANDS["save"].execute(self.admin, "all")
        self.assertEqual(admin_calls, [(False, None)])
        self.assertEqual(target_calls[-1], (False, None))
        self.assertEqual(world.calls[-1], (False, None))

    def test_adminstatus_reports_bounded_operational_views(self):
        COMMANDS["adminstatus"].execute(self.admin, "")
        transcript = self.transcript(self.admin_request)
        self.assertIn("connections: total=3", transcript)
        self.assertIn("db_schema=2", transcript)
        self.assertIn("character_writer: unavailable", transcript)

        COMMANDS["adminstatus"].execute(self.admin, "rooms")
        self.assertIn("room start", self.transcript(self.admin_request))


if __name__ == "__main__":
    unittest.main()
