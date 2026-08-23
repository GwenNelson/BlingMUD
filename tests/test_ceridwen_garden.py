import unittest

from core import Player
from rooms.ceridwens_cottage import CeridwensCottage
from rooms.overgrown_herb_garden import OvergrownHerbGarden


class Session(object):
    def __init__(self, player):
        self.player = player
        player.session = self
        self.messages = []
    def send(self, text):
        self.messages.append(text)


class CeridwenGardenTests(unittest.TestCase):
    def test_cottage_and_garden_are_bounded_gated_slices(self):
        player = Player("Herbalist")
        session = Session(player)
        cottage = CeridwensCottage()
        garden = OvergrownHerbGarden()
        cottage.enter(player, announce=False)
        cottage.on_command(session, "buy", "salve")
        self.assertIn("rare weed", session.messages[-1])
        cottage.leave(player, announce=False)
        garden.enter(player, announce=False)
        garden.on_command(session, "harvest", "weed")
        self.assertIn("not yet safe", session.messages[-1])
        garden.leave(player, announce=False)


if __name__ == "__main__":
    unittest.main()
