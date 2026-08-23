import unittest

import blingmud
from commands.core import DrinkCommand, EatCommand
from core import FSMBehavior, PLAYER_INVENTORY_LIMIT, Player
from items.drinks import AcornGoblet, ValkyrieMead
from items.food import AcornMash
from items.giant_acorn import GiantAcorn
from items.pimp_hat import PimpHat
from rooms.corbels_turnery import CorbelsTurnery
from rooms.vals_hella_holler import ValsHellaHoller


class RecordingSession(object):
    def __init__(self, player):
        self.player = player
        self.messages = []
        player.session = self

    def send(self, message):
        self.messages.append(message)

    def damage_player(self, amount, cause):
        return self.player.take_damage(amount)


class CorbelsTurneryTests(unittest.TestCase):
    def setUp(self):
        self.turnery = CorbelsTurnery()
        self.player = Player("Harvester")
        self.session = RecordingSession(self.player)
        self.turnery.enter(self.player, announce=False)
        self.session.messages = []

    def tearDown(self):
        if self.player.room is not None:
            self.player.room.leave(self.player, announce=False)
        if self.turnery.corbel.room is self.turnery:
            self.turnery.remove_npc(self.turnery.corbel)

    def transcript(self):
        return "\n".join(self.session.messages)

    def test_world_connects_turnery_and_uses_local_fsm_corbel(self):
        green = blingmud.WORLD.rooms["village_green"]
        turnery = blingmud.WORLD.rooms["corbels_turnery"]

        self.assertIsInstance(turnery, CorbelsTurnery)
        self.assertIs(green.exits["west"], turnery)
        self.assertIs(turnery.exits["east"], green)
        self.assertIsInstance(turnery.corbel.behavior, FSMBehavior)

    def test_trade_and_craft_complete_the_acorn_loop_without_duplication(self):
        self.player.inventory.append(GiantAcorn())
        self.assertTrue(self.turnery.on_command(self.session, "trade", "acorn"))
        self.assertEqual(self.player.coins, 5)
        self.assertFalse(any(
            isinstance(item, GiantAcorn) for item in self.player.inventory
        ))

        self.player.inventory.append(GiantAcorn())
        self.assertTrue(self.turnery.on_command(self.session, "craft", "goblet"))
        self.assertEqual(len(self.player.inventory), 1)
        self.assertIsInstance(self.player.inventory[0], AcornGoblet)
        self.assertIn("Val can fill it", self.transcript())

    def test_buy_is_atomic_at_inventory_and_coin_limits(self):
        self.player.coins = 8
        self.assertTrue(self.turnery.on_command(self.session, "buy", "goblet"))
        self.assertEqual(self.player.coins, 0)
        self.assertIsInstance(self.player.inventory[-1], AcornGoblet)

        self.player.inventory = [
            PimpHat() for unused in range(PLAYER_INVENTORY_LIMIT)
        ]
        self.player.coins = 2
        self.turnery.on_command(self.session, "buy", "mash")
        self.assertEqual(self.player.coins, 2)
        self.assertEqual(len(self.player.inventory), PLAYER_INVENTORY_LIMIT)

        self.player.inventory = []
        self.player.coins = 1
        self.turnery.on_command(self.session, "buy", "mash")
        self.assertEqual(self.player.coins, 1)
        self.assertEqual(self.player.inventory, [])

    def test_trade_preserves_an_acorn_when_the_wallet_cannot_hold_full_value(self):
        self.player.coins = 99999
        acorn = GiantAcorn()
        self.player.inventory = [acorn]

        self.turnery.on_command(self.session, "trade", "acorn")

        self.assertEqual(self.player.coins, 99999)
        self.assertEqual(self.player.inventory, [acorn])

    def test_val_fills_a_goblet_without_creating_another_inventory_item(self):
        tavern = ValsHellaHoller(blingmud.WORLD.village_state)
        goblet = AcornGoblet()
        self.player.inventory = [goblet]
        self.turnery.leave(self.player, announce=False)
        tavern.enter(self.player, announce=False)
        self.session.messages = []

        try:
            tavern.on_command(self.session, "order", "mead")
            self.assertEqual(self.player.inventory, [goblet])
            self.assertIsInstance(goblet.held_drink, ValkyrieMead)
            self.assertIn("your acorn goblet", self.transcript())
        finally:
            if self.player.room is tavern:
                tavern.leave(self.player, announce=False)
            if tavern.val.room is tavern:
                tavern.remove_npc(tavern.val)

    def test_goblet_drinking_preserves_the_contained_drinks_real_feedback(self):
        goblet = AcornGoblet(ValkyrieMead())
        self.player.inventory = [goblet]

        DrinkCommand().execute(self.session, "acorn goblet")

        self.assertEqual(self.player.intoxication, 20)
        self.assertIsNone(goblet.held_drink)
        self.assertEqual(self.player.inventory, [goblet])
        self.assertIn("mead tastes of honey", self.transcript())
        self.assertIn("Intoxication rises by 20", self.transcript())

    def test_mash_is_a_real_bounded_food(self):
        mash = AcornMash()
        self.player.inventory = [mash]
        self.player.health = 90

        EatCommand().execute(self.session, "acorn mash")

        self.assertEqual(self.player.health, 98)
        self.assertNotIn(mash, self.player.inventory)
        self.assertIn("restores 8 health", self.transcript())


if __name__ == "__main__":
    unittest.main()
