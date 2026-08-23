import unittest

import blingmud
from core import Player
from rooms.ceridwens_cottage import CeridwensCottage
from rooms.overgrown_herb_garden import OvergrownHerbGarden
from items.herbs import RareWeed
from player_state import restore_player_state, serialize_player_state


class Session(object):
    def __init__(self, player):
        self.player = player
        player.session = self
        self.messages = []
    def send(self, text):
        self.messages.append(text)


class CeridwenGardenTests(unittest.TestCase):
    def test_advertised_give_command_always_returns_useful_feedback(self):
        player = Player("Herbalist")
        session = Session(player)
        cottage = CeridwensCottage()
        cottage.enter(player, announce=False)
        try:
            self.assertTrue(cottage.on_command(session, "give", ""))
            self.assertEqual(
                session.messages[-1],
                "Give what? Ceridwen is looking for a rare weed."
            )
            self.assertTrue(cottage.on_command(session, "give", "mushroom"))
            self.assertIn("rare weed", session.messages[-1])
        finally:
            cottage.leave(player, announce=False)

    def test_cottage_and_garden_are_bounded_gated_slices(self):
        player = Player("Herbalist")
        session = Session(player)
        cottage = CeridwensCottage()
        garden = OvergrownHerbGarden()
        player.coins = 3
        cottage.enter(player, announce=False)
        cottage.on_command(session, "buy", "salve")
        self.assertIn("rare weed", session.messages[-1])
        cottage.on_command(session, "buy", "experimental")
        self.assertIn("locked", session.messages[-1])
        cottage.leave(player, announce=False)
        garden.enter(player, announce=False)
        garden.on_command(session, "harvest", "weed")
        self.assertIn("harvest one rare weed", session.messages[-1])
        cottage.enter(player, announce=False)
        cottage.on_command(session, "give", "weed")
        cottage.on_command(session, "buy", "experimental")
        self.assertIn("experimental potion", session.messages[-1])

        cottage.on_command(session, "buy", "salve")
        self.assertIn("still brewing", session.messages[-1])
        self.assertIn("unlocked experimental shelf", session.messages[-1])

        cottage.on_command(session, "give", "weed")
        self.assertIn("already unlocked", session.messages[-1])

        cottage.on_command(session, "buy", "mystery")
        self.assertIn("experimental shelf is unlocked", session.messages[-1])
        cottage.leave(player, announce=False)

    def test_rare_weed_round_trips_through_explicit_player_template(self):
        player = Player("SavedHerbalist")
        player.inventory.append(RareWeed())
        encoded = serialize_player_state(player)
        restored = Player("RestoredHerbalist")
        restore_player_state(restored, encoded, blingmud.World())
        self.assertEqual(len(restored.inventory), 1)
        self.assertIsInstance(restored.inventory[0], RareWeed)


if __name__ == "__main__":
    unittest.main()
