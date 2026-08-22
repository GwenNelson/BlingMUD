import unittest

import blingmud
from core import Item


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


if __name__ == "__main__":
    unittest.main()
