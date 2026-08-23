import unittest

from core import Player, Room
from rooms.temple_of_self import TempleOfSelf


class Request(object):
    def __init__(self):
        self.sent = []
    def sendall(self, data):
        self.sent.append(data)


class Session(object):
    def __init__(self, player):
        self.player = player
        player.session = self
        self.request = Request()
    def send(self, text):
        self.request.sent.append((text + "\n").encode())


class TempleTests(unittest.TestCase):
    def setUp(self):
        self.room = TempleOfSelf()
        self.player = Player("MirrorWalker")
        self.session = Session(self.player)
        self.room.enter(self.player, announce=False)

    def tearDown(self):
        if self.player.room is not None:
            self.player.room.leave(self.player, announce=False)

    def transcript(self):
        return b"".join(self.session.request.sent).decode()

    def test_reflection_and_book_are_bounded_local_text(self):
        self.room.on_command(self.session, "look", "mirror")
        self.room.on_command(self.session, "read", "book")
        self.assertIn("health", self.transcript())
        self.assertIn("Tome of Indulgence", self.transcript())

    def test_meditation_uses_shared_health_api(self):
        self.player.health = 40
        self.room.on_command(self.session, "meditate", "")
        self.assertEqual(self.player.health, 45)

    def test_respec_is_explicitly_gated(self):
        self.room.on_command(self.session, "reforge", "self")
        self.assertIn("not yet unlocked", self.transcript())


if __name__ == "__main__":
    unittest.main()
