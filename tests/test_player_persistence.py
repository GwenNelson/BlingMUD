import io
import json
import os
import sys
import tempfile
import unittest

import blingmud
from core import Item, Player, Room
from items.giant_acorn import GiantAcorn
from items.pimp_hat import PimpHat
from items.possum_token import RoyalPossumBottleCap
from player_state import (
    MAX_PLAYER_STATE_BYTES,
    PLAYER_STATE_VERSION,
    PlayerStateError,
    new_player_state_json,
    restore_player_state,
    serialize_player_state
)


class StateWorld(object):
    def __init__(self):
        self.starting_room = Room("start", "Start", "The starting room.")
        self.other_room = Room("other", "Other", "Another room.")
        self.rooms = {
            self.starting_room.room_id: self.starting_room,
            self.other_room.room_id: self.other_room
        }


class RecordingRequest(object):
    def __init__(self, received=b""):
        self.received = list(received)
        self.sent = []
        self.shutdown_called = False
        self.close_called = False

    def recv(self, size):
        if not self.received:
            return b""

        return bytes((self.received.pop(0),))

    def sendall(self, data):
        self.sent.append(data)

    def shutdown(self, how):
        self.shutdown_called = True

    def close(self):
        self.close_called = True


class PlayerStateUnitTests(unittest.TestCase):
    def setUp(self):
        self.world = StateWorld()

    def test_state_round_trip_preserves_supported_gameplay_state(self):
        player = Player("Saver")
        player.room = self.world.other_room
        hat = PimpHat()
        token = RoyalPossumBottleCap()
        acorn = GiantAcorn()
        player.inventory = [hat, token, acorn]
        player.equipment[hat.worn_where] = hat
        player.fabulousness = 37
        player.is_admin = True

        encoded = serialize_player_state(player)
        restored = Player("Saver")
        room = restore_player_state(restored, encoded, self.world)

        self.assertIs(room, self.world.other_room)
        self.assertEqual(restored.fabulousness, 37)
        self.assertEqual(len(restored.inventory), 3)
        self.assertIsInstance(restored.inventory[0], PimpHat)
        self.assertIsInstance(
            restored.inventory[1],
            RoyalPossumBottleCap
        )
        self.assertIsInstance(restored.inventory[2], GiantAcorn)
        self.assertIs(restored.equipment["Head"], restored.inventory[0])
        self.assertFalse(restored.is_admin)

    def test_legacy_empty_state_migrates_to_safe_defaults(self):
        player = Player("Legacy")

        room = restore_player_state(player, "{}", self.world)

        self.assertIs(room, self.world.starting_room)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.equipment, {})
        self.assertEqual(player.fabulousness, 0)

    def test_missing_room_falls_back_to_starting_room(self):
        document = json.loads(new_player_state_json())
        document["room_id"] = "removed_room"
        player = Player("Traveller")

        room = restore_player_state(
            player,
            json.dumps(document),
            self.world
        )

        self.assertIs(room, self.world.starting_room)

    def test_invalid_state_is_rejected_before_mutating_player(self):
        invalid_documents = (
            "not json",
            json.dumps({"version": True}),
            json.dumps({
                "version": PLAYER_STATE_VERSION,
                "room_id": "start",
                "stats": {"fabulousness": 0},
                "inventory": [{"template": "arbitrary_python_class"}],
                "equipment": {}
            }),
            " " * (MAX_PLAYER_STATE_BYTES + 1)
        )

        for encoded in invalid_documents:
            player = Player("Untouched")
            marker = Item("marker")
            player.inventory.append(marker)
            player.fabulousness = 9

            with self.assertRaises(PlayerStateError):
                restore_player_state(player, encoded, self.world)

            self.assertEqual(player.inventory, [marker])
            self.assertEqual(player.fabulousness, 9)

    def test_unsupported_live_item_prevents_lossy_save(self):
        player = Player("Collector")
        player.inventory.append(Item("unregistered prototype"))

        with self.assertRaises(PlayerStateError):
            serialize_player_state(player)


class PlayerStateDatabaseTests(unittest.TestCase):
    def setUp(self):
        descriptor, self.database_path = tempfile.mkstemp()
        os.close(descriptor)
        self.original_database = blingmud.USERS_DB
        blingmud.USERS_DB = self.database_path
        blingmud.init_user_database()
        self.world = StateWorld()

    def tearDown(self):
        with blingmud.SESSIONS_LOCK:
            for key, session in list(blingmud.SESSIONS.items()):
                if session.world is self.world:
                    del blingmud.SESSIONS[key]

        blingmud.USERS_DB = self.original_database
        os.unlink(self.database_path)

    def test_new_account_starts_with_versioned_state(self):
        blingmud.create_user("Versioned", "a sufficiently long password")

        account = blingmud.load_user("Versioned")
        document = json.loads(account["state_json"])

        self.assertEqual(document["version"], PLAYER_STATE_VERSION)
        self.assertEqual(document["inventory"], [])

    def test_login_restores_room_inventory_equipment_and_stats(self):
        password = "another sufficiently long password"
        blingmud.create_user("Returner", password)
        saved_player = Player("Returner")
        saved_player.room = self.world.other_room
        hat = PimpHat()
        saved_player.inventory.append(hat)
        saved_player.equipment[hat.worn_where] = hat
        saved_player.fabulousness = 10
        blingmud.update_user_state(
            saved_player.name,
            serialize_player_state(saved_player)
        )

        session = blingmud.Session(
            RecordingRequest(),
            ("127.0.0.1", 0),
            self.world
        )
        answers = iter(("Returner", password))
        session.prompt = lambda prompt: None
        session.read_line = lambda hidden=False, maximum_length=None: next(
            answers
        )

        self.assertTrue(session.login())
        self.assertIs(session.login_room, self.world.other_room)
        self.assertEqual(session.player.fabulousness, 10)
        self.assertIsInstance(session.player.inventory[0], PimpHat)
        self.assertIs(
            session.player.equipment["Head"],
            session.player.inventory[0]
        )

    def test_login_with_corrupt_state_uses_safe_defaults(self):
        password = "a fifth sufficiently long password"
        blingmud.create_user("Corrupt", password)
        blingmud.update_user_state("Corrupt", "not json")
        request = RecordingRequest()
        session = blingmud.Session(
            request,
            ("127.0.0.1", 0),
            self.world
        )
        answers = iter(("Corrupt", password))
        session.prompt = lambda prompt: None
        session.read_line = lambda hidden=False, maximum_length=None: next(
            answers
        )
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            self.assertTrue(session.login())
            warning = sys.stderr.getvalue()
        finally:
            sys.stderr = original_stderr

        transcript = b"".join(request.sent).decode("utf-8")
        self.assertIs(session.login_room, self.world.starting_room)
        self.assertEqual(session.player.inventory, [])
        self.assertEqual(session.player.equipment, {})
        self.assertEqual(session.player.fabulousness, 0)
        self.assertIn("Invalid saved state", warning)
        self.assertIn("safe defaults", transcript)

    def test_disconnect_saves_before_player_leaves_room(self):
        blingmud.create_user("Leaver", "a third sufficiently long password")
        request = RecordingRequest()
        session = blingmud.Session(request, ("127.0.0.1", 0), self.world)
        player = Player("Leaver")
        player.session = session
        player.inventory.append(RoyalPossumBottleCap())
        session.player = player
        self.world.other_room.enter(player, announce=False)

        with blingmud.SESSIONS_LOCK:
            blingmud.SESSIONS[player.name.lower()] = session

        session.disconnect()

        restored = Player("Leaver")
        room = restore_player_state(
            restored,
            blingmud.load_user("Leaver")["state_json"],
            self.world
        )
        self.assertIs(room, self.world.other_room)
        self.assertIsInstance(
            restored.inventory[0],
            RoyalPossumBottleCap
        )
        self.assertNotIn(player, self.world.other_room.players)
        self.assertIsNone(player.room)
        self.assertTrue(request.shutdown_called)
        self.assertTrue(request.close_called)

    def test_failed_lossy_save_keeps_previous_state_and_still_disconnects(self):
        blingmud.create_user("Unsafe", "a fourth sufficiently long password")
        original_state = blingmud.load_user("Unsafe")["state_json"]
        request = RecordingRequest()
        session = blingmud.Session(request, ("127.0.0.1", 0), self.world)
        player = Player("Unsafe")
        player.session = session
        player.inventory.append(Item("unsupported"))
        session.player = player
        self.world.starting_room.enter(player, announce=False)
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            session.disconnect()
            warning = sys.stderr.getvalue()
        finally:
            sys.stderr = original_stderr

        self.assertEqual(
            blingmud.load_user("Unsafe")["state_json"],
            original_state
        )
        self.assertIn("Could not save", warning)
        self.assertNotIn(player, self.world.starting_room.players)
        self.assertTrue(request.close_called)


class InputBoundTests(unittest.TestCase):
    def test_read_line_discards_input_beyond_its_bound(self):
        request = RecordingRequest(b"abcdef\n")
        session = blingmud.Session(
            request,
            ("127.0.0.1", 0),
            StateWorld()
        )

        result = session.read_line(maximum_length=4)

        self.assertEqual(result, "abcd")
        self.assertEqual(session.current_input, "")


if __name__ == "__main__":
    unittest.main()
