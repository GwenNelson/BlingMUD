import io
import json
import unittest

import blingmud
from core import COMMANDS, Player, Room
from operational_log import OPS_LOG


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
        self.original_ai_runtime = blingmud.AI_RUNTIME

        with blingmud.SESSIONS_LOCK:
            blingmud.SESSIONS["administrator"] = self.admin
            blingmud.SESSIONS["target"] = self.target

    def tearDown(self):
        blingmud.WORLD_SAVE_COORDINATOR = self.original_world_coordinator
        blingmud.AI_RUNTIME = self.original_ai_runtime

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
        self.assertIn("db_schema=4", transcript)
        self.assertIn("database: path=", transcript)
        self.assertIn("character_writer: unavailable", transcript)

        COMMANDS["adminstatus"].execute(self.admin, "rooms")
        self.assertIn("room start", self.transcript(self.admin_request))

    def test_adminstatus_ai_reports_only_bounded_runtime_metadata(self):
        class Provider(object):
            status = "healthy"

        class Runtime(object):
            provider = Provider()

            @staticmethod
            def status_snapshot():
                return {"queued": 0, "submitted": 1, "closed": False}

        blingmud.AI_RUNTIME = Runtime()
        COMMANDS["adminstatus"].execute(self.admin, "ai")
        transcript = self.transcript(self.admin_request)
        self.assertIn("npc_ai: provider=healthy", transcript)
        self.assertIn("submitted", transcript)
        self.assertNotIn("prompt", transcript.lower())
        self.assertNotIn("key", transcript.lower())

    def test_adminai_controls_runtime_without_exposing_provider_data(self):
        class Provider(object):
            status = "healthy"
            def clear_circuit(self):
                self.cleared = True

        class Runtime(object):
            def __init__(self):
                self.provider = Provider()
                self.enabled = True
            def status_snapshot(self):
                return {"enabled": self.enabled, "queued": 0}
            def set_enabled(self, value):
                self.enabled = bool(value)
                return self.enabled
            def clear_circuit(self):
                self.provider.clear_circuit()
            def refresh_catalogue(self):
                return True

        runtime = Runtime()
        blingmud.AI_RUNTIME = runtime
        COMMANDS["adminai"].execute(self.admin, "disable")
        self.assertFalse(runtime.enabled)
        COMMANDS["adminai"].execute(self.admin, "enable")
        self.assertTrue(runtime.enabled)
        COMMANDS["adminai"].execute(self.admin, "clear")
        self.assertTrue(runtime.provider.cleared)
        transcript = self.transcript(self.admin_request)
        self.assertIn("disabled", transcript)
        self.assertIn("enabled", transcript)
        self.assertNotIn("key", transcript.lower())

    def test_adminai_inspect_reports_only_bounded_npc_metadata(self):
        class Provider(object):
            status = "healthy"
        class Behavior(object):
            def persistent_state(self, npc_id):
                return {
                    "state": "working", "resources": {"x": 1},
                    "memory": {"traveller": "private name"}
                }
        class NPC(object):
            behavior = Behavior()
        class Runtime(object):
            provider = Provider()
            def status_snapshot(self): return {"enabled": True}
        original = self.admin.world.rooms
        self.admin.world.rooms = {"crossroads": type("Room", (), {"knight": NPC()})()}
        blingmud.AI_RUNTIME = Runtime()
        COMMANDS["adminai"].execute(self.admin, "inspect knight")
        transcript = self.transcript(self.admin_request)
        self.assertIn("memory_entries=1", transcript)
        self.assertNotIn("private name", transcript)
        self.admin.world.rooms = original

    def test_admin_log_records_action_without_reason_text(self):
        sink = io.StringIO()
        original_sink = OPS_LOG.sink
        original_enabled = OPS_LOG.enabled
        OPS_LOG.sink = sink
        OPS_LOG.enabled = True

        try:
            COMMANDS["shutdown"].execute(
                self.admin,
                "now a private operator explanation"
            )
        finally:
            OPS_LOG.sink = original_sink
            OPS_LOG.enabled = original_enabled

        document = json.loads(sink.getvalue())
        self.assertEqual(document["event"], "admin.shutdown")
        self.assertEqual(document["actor"], "Administrator")
        self.assertTrue(document["reason_supplied"])
        self.assertNotIn("private operator explanation", sink.getvalue())

    def test_tell_uses_canonical_session_lookup_and_bounds_message(self):
        COMMANDS["tell"].execute(self.admin, "TARGET hello there")
        self.assertIn("Administrator tells you: hello there", self.transcript(self.target_request))
        self.assertIn("You tell Target: hello there", self.transcript(self.admin_request))
        before = len(self.target_request.sent)
        COMMANDS["tell"].execute(self.admin, "target " + ("x" * 201))
        self.assertEqual(before, len(self.target_request.sent))
        self.assertIn("too long", self.transcript(self.admin_request))


if __name__ == "__main__":
    unittest.main()
