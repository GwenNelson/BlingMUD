import unittest
import hashlib
import os
import stat
import tempfile

import blingmud
from core import Item, NPC, NPCManager, Room


class DummyRequest(object):
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        return b""


class HandleCommandRegressionTests(unittest.TestCase):
    def setUp(self):
        self.request = DummyRequest()
        self.session = blingmud.Session(self.request, ("127.0.0.1", 0), blingmud.WORLD)
        self.session.player = blingmud.Player("Tester")
        self.session.player.session = self.session
        self.session.player.is_admin = True

    def tearDown(self):
        blingmud.COMMANDS.pop("regression_test", None)

    def test_admin_command_dispatch_uses_session_instance(self):
        calls = []

        class RegressionCommand(blingmud.Command):
            name = "regression_test"
            admin_only = True

            def execute(self, session, arguments):
                calls.append((session, arguments))

        blingmud.COMMANDS["regression_test"] = RegressionCommand()

        self.session.handle_command("/regression_test hello")

        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], self.session)
        self.assertEqual(calls[0][1], "hello")


class ItemRegressionTests(unittest.TestCase):
    def test_worn_where_is_preserved(self):
        item = Item("ring", wearable=True, worn_where="Finger")

        self.assertTrue(item.wearable)
        self.assertEqual(item.worn_where, "Finger")


class PasswordRegressionTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifiable(self):
        first = blingmud.password_hash("correct horse battery staple")
        second = blingmud.password_hash("correct horse battery staple")

        self.assertNotEqual(first, second)
        self.assertTrue(
            first.startswith(blingmud.PASSWORD_HASH_SCHEME + "$")
        )
        self.assertTrue(
            blingmud.verify_password("correct horse battery staple", first)
        )
        self.assertFalse(blingmud.verify_password("wrong password", first))

    def test_legacy_sha256_hash_can_be_verified_for_migration(self):
        legacy = hashlib.sha256(b"old password").hexdigest()

        self.assertTrue(blingmud.verify_password("old password", legacy))
        self.assertTrue(blingmud.password_hash_needs_upgrade(legacy))

    def test_malformed_password_hash_is_rejected(self):
        self.assertFalse(
            blingmud.verify_password("password", "pbkdf2_sha256$bad$data")
        )
        self.assertFalse(blingmud.verify_password(None, "stored hash"))

    def test_admin_hash_file_is_owner_only(self):
        descriptor, path = tempfile.mkstemp()
        os.close(descriptor)

        try:
            blingmud.write_admin_password_hash("stored hash", path)
            mode = stat.S_IMODE(os.stat(path).st_mode)

            self.assertEqual(mode, 0o600)
            with open(path, "r") as handle:
                self.assertEqual(handle.read(), "stored hash")
        finally:
            os.unlink(path)

    def test_successful_login_upgrades_legacy_user_hash(self):
        descriptor, path = tempfile.mkstemp()
        os.close(descriptor)
        original_database = blingmud.USERS_DB
        key = "legacyuser"

        try:
            blingmud.USERS_DB = path
            blingmud.init_user_database()
            blingmud.create_user("LegacyUser", "old password")
            legacy = hashlib.sha256(b"old password").hexdigest()
            blingmud.update_user_password_hash("LegacyUser", legacy)

            session = blingmud.Session(
                DummyRequest(),
                ("127.0.0.1", 0),
                blingmud.WORLD
            )
            answers = iter(("LegacyUser", "old password"))
            session.prompt = lambda prompt: None
            session.read_line = lambda hidden=False: next(answers)

            self.assertTrue(session.login())

            upgraded = blingmud.load_user("LegacyUser")["password"]
            self.assertTrue(
                upgraded.startswith(blingmud.PASSWORD_HASH_SCHEME + "$")
            )
            self.assertTrue(blingmud.verify_password("old password", upgraded))
        finally:
            with blingmud.SESSIONS_LOCK:
                blingmud.SESSIONS.pop(key, None)
            blingmud.USERS_DB = original_database
            os.unlink(path)


class NPCManagerRegressionTests(unittest.TestCase):
    def test_removing_npc_unregisters_it_from_manager(self):
        manager = NPCManager.instance()
        room = Room("test_room", "Test Room", "A test room.")
        npc = NPC("Test NPC")

        room.add_npc(npc)
        self.assertIn(npc, manager.npcs)

        room.remove_npc(npc)

        self.assertNotIn(npc, room.npcs)
        self.assertNotIn(npc, manager.npcs)
        self.assertIsNone(npc.room)


if __name__ == "__main__":
    unittest.main()
