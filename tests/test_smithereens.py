import unittest

from core import Player
from rooms.smithereens import Smithereens


class Session(object):
    def __init__(self, player):
        self.player = player
        player.session = self
        self.messages = []
    def send(self, text):
        self.messages.append(text)


class SmithereensTests(unittest.TestCase):
    def setUp(self):
        self.room = Smithereens()
        self.player = Player("ForgeWalker")
        self.session = Session(self.player)
        self.room.enter(self.player, announce=False)

    def tearDown(self):
        if self.player.room is not None:
            self.player.room.leave(self.player, announce=False)

    def test_browse_and_tackdriver_interactions_are_local(self):
        self.room.on_command(self.session, "browse", "scrap")
        self.room.on_command(self.session, "examine", "hammer")
        self.room.on_command(self.session, "listen", "hammer")
        self.assertTrue(any("scrap rack" in message for message in self.session.messages))
        self.assertTrue(any("Tackdriver" in message for message in self.session.messages))


if __name__ == "__main__":
    unittest.main()
