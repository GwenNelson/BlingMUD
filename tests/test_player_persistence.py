import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest

import blingmud
from core import (
    DEFAULT_MAX_HEALTH,
    Item,
    PLAYER_INVENTORY_LIMIT,
    Player,
    Room
)
from items.drinks import HornBornSpecial, ValHealingPotion, ValkyrieMead
from items.giant_acorn import GiantAcorn
from items.pimp_hat import PimpHat
from items.possum_token import RoyalPossumBottleCap
from player_state import (
    MAX_STATUS_TIMESTAMP,
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
        potion = ValHealingPotion()
        mead = ValkyrieMead()
        special = HornBornSpecial()
        player.inventory = [hat, token, acorn, potion, mead, special]
        player.equipment[hat.worn_where] = hat
        player.fabulousness = 37
        player.max_health = 140
        player.health = 83
        player.intoxication = 46
        player.recently_respawned = True
        player.is_admin = True

        encoded = serialize_player_state(player)
        restored = Player("Saver")
        room = restore_player_state(restored, encoded, self.world)

        self.assertIs(room, self.world.other_room)
        self.assertEqual(restored.fabulousness, 37)
        self.assertEqual(len(restored.inventory), 6)
        self.assertIsInstance(restored.inventory[0], PimpHat)
        self.assertIsInstance(
            restored.inventory[1],
            RoyalPossumBottleCap
        )
        self.assertIsInstance(restored.inventory[2], GiantAcorn)
        self.assertIsInstance(restored.inventory[3], ValHealingPotion)
        self.assertIsInstance(restored.inventory[4], ValkyrieMead)
        self.assertIsInstance(restored.inventory[5], HornBornSpecial)
        self.assertIs(restored.equipment["Head"], restored.inventory[0])
        self.assertEqual(restored.max_health, 140)
        self.assertEqual(restored.health, 83)
        self.assertEqual(restored.intoxication, 46)
        self.assertTrue(restored.recently_respawned)
        self.assertFalse(restored.is_admin)

    def test_legacy_empty_state_migrates_to_safe_defaults(self):
        player = Player("Legacy")

        room = restore_player_state(player, "{}", self.world)

        self.assertIs(room, self.world.starting_room)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.equipment, {})
        self.assertEqual(player.fabulousness, 0)
        self.assertEqual(player.max_health, DEFAULT_MAX_HEALTH)
        self.assertEqual(player.health, DEFAULT_MAX_HEALTH)
        self.assertEqual(player.intoxication, 0)

    def test_older_version_one_stats_gain_safe_health_defaults(self):
        document = {
            "version": 1,
            "room_id": "other",
            "stats": {"fabulousness": 12},
            "inventory": [],
            "equipment": {}
        }
        player = Player("Compatible")

        room = restore_player_state(
            player,
            json.dumps(document),
            self.world
        )

        self.assertIs(room, self.world.other_room)
        self.assertEqual(player.fabulousness, 12)
        self.assertEqual(player.max_health, DEFAULT_MAX_HEALTH)
        self.assertEqual(player.health, DEFAULT_MAX_HEALTH)
        self.assertEqual(player.intoxication, 0)
        self.assertFalse(player.recently_respawned)

    def test_version_one_intoxication_migrates_without_fake_offline_decay(self):
        document = {
            "version": 1,
            "room_id": "other",
            "stats": {
                "fabulousness": 0,
                "max_health": 100,
                "health": 90,
                "intoxication": 12
            },
            "inventory": [],
            "equipment": {}
        }
        player = Player("Migrating")
        restore_player_state(
            player,
            json.dumps(document),
            self.world,
            time_source=lambda: 500.0
        )
        self.assertEqual(player.intoxication, 12)
        self.assertFalse(player.recently_respawned)
        self.assertEqual(player.last_status_update, 500.0)

    def test_version_two_applies_bounded_offline_intoxication_decay(self):
        document = json.loads(new_player_state_json(time_source=lambda: 100.0))
        document["stats"]["intoxication"] = 10
        document["status"]["recently_respawned"] = True
        player = Player("Sleeper")
        restore_player_state(
            player,
            json.dumps(document),
            self.world,
            time_source=lambda: 400.0
        )
        self.assertEqual(player.intoxication, 5)
        self.assertTrue(player.recently_respawned)
        self.assertEqual(player.last_status_update, 400.0)

        document["status"]["last_status_update"] = 1000.0
        document["stats"]["intoxication"] = 7
        restore_player_state(
            player,
            json.dumps(document),
            self.world,
            time_source=lambda: 500.0
        )
        self.assertEqual(player.intoxication, 7)
        self.assertEqual(player.last_status_update, 1000.0)

    def test_invalid_version_two_status_is_rejected_atomically(self):
        invalid_values = (True, -1, float("nan"), MAX_STATUS_TIMESTAMP + 1)

        for invalid in invalid_values:
            document = json.loads(new_player_state_json())
            document["status"]["last_status_update"] = invalid
            player = Player("UntouchedStatus")
            player.recently_respawned = True

            with self.assertRaises(PlayerStateError):
                restore_player_state(
                    player,
                    json.dumps(document),
                    self.world
                )

            self.assertTrue(player.recently_respawned)

        document = json.loads(new_player_state_json())
        document["status"]["recently_respawned"] = 1

        with self.assertRaises(PlayerStateError):
            restore_player_state(
                Player("InvalidRecentFlag"),
                json.dumps(document),
                self.world
            )

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

    def test_invalid_health_state_is_rejected_atomically(self):
        document = json.loads(new_player_state_json())
        document["stats"]["max_health"] = 100
        document["stats"]["health"] = 101
        player = Player("Untouched")
        marker = PimpHat()
        player.inventory = [marker]
        player.health = 17

        with self.assertRaises(PlayerStateError):
            restore_player_state(player, json.dumps(document), self.world)

        self.assertEqual(player.inventory, [marker])
        self.assertEqual(player.health, 17)

    def test_unsupported_live_item_prevents_lossy_save(self):
        player = Player("Collector")
        player.inventory.append(Item("unregistered prototype"))

        with self.assertRaises(PlayerStateError):
            serialize_player_state(player)

    def test_gameplay_inventory_limit_is_exactly_serializable(self):
        player = Player("Bounded")
        player.inventory = [
            PimpHat()
            for unused in range(PLAYER_INVENTORY_LIMIT)
        ]

        encoded = serialize_player_state(player)
        restored = Player("Bounded")
        restore_player_state(restored, encoded, self.world)
        self.assertEqual(
            len(restored.inventory),
            PLAYER_INVENTORY_LIMIT
        )

        player.inventory.append(PimpHat())

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
        self.assertIn("status", document)

    def test_database_migrations_are_versioned_and_preserve_accounts(self):
        blingmud.create_user("LegacyRow", "a sufficiently long password")
        connection = sqlite3.connect(self.database_path)

        try:
            connection.execute("DROP TABLE world_state")
            connection.execute("PRAGMA user_version = 0")
            connection.commit()
        finally:
            connection.close()

        blingmud.init_user_database()
        self.assertIsNotNone(blingmud.load_user("LegacyRow"))
        self.assertIsNotNone(blingmud.load_world_state())
        connection = sqlite3.connect(self.database_path)

        try:
            version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(version, blingmud.DATABASE_SCHEMA_VERSION)

    def test_database_newer_than_runtime_is_rejected(self):
        connection = sqlite3.connect(self.database_path)

        try:
            connection.execute(
                "PRAGMA user_version = {0}".format(
                    blingmud.DATABASE_SCHEMA_VERSION + 1
                )
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(blingmud.DatabaseMigrationError):
            blingmud.init_user_database()

    def test_claimed_current_but_incomplete_database_is_rejected(self):
        connection = sqlite3.connect(self.database_path)

        try:
            connection.execute("DROP TABLE world_state")
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(blingmud.DatabaseMigrationError):
            blingmud.init_user_database()

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
