import unittest

import blingmud
from core import COMMANDS, Item, PLAYER_INVENTORY_LIMIT, Player, ROOM_ITEM_LIMIT, Room
from items.pimp_hat import PimpHat
from items.possum_token import RoyalPossumBottleCap
from rooms.hanging_tree import HangingTreeCanopy
from rooms.suspicious_alley import SuspiciousAlley
from village_state import VillageState


class RecordingSession(object):
    def __init__(self, player):
        self.player = player
        self.messages = []
        player.session = self

    def send(self, message):
        self.messages.append(message)


class ItemLimitRegressionTests(unittest.TestCase):
    def setUp(self):
        self.room = Room("limits", "Limits", "A bounded test room.")
        self.player = Player("Carrier")
        self.session = RecordingSession(self.player)
        self.room.enter(self.player, announce=False)

    def tearDown(self):
        if self.player.room is not None:
            self.player.room.leave(self.player, announce=False)

    def test_take_preserves_room_item_when_inventory_is_full(self):
        target = PimpHat()
        self.room.add_item(target)
        self.player.inventory = [
            PimpHat()
            for unused in range(PLAYER_INVENTORY_LIMIT)
        ]

        COMMANDS["take"].execute(self.session, target.name)

        self.assertIn(target, self.room.items)
        self.assertEqual(
            len(self.player.inventory),
            PLAYER_INVENTORY_LIMIT
        )
        self.assertIn("cannot carry", self.session.messages[-1])

    def test_drop_preserves_inventory_and_equipment_when_room_is_full(self):
        hat = PimpHat()
        self.player.inventory.append(hat)
        self.player.equipment[hat.worn_where] = hat
        self.player.fabulousness = 10

        for index in range(ROOM_ITEM_LIMIT):
            self.assertTrue(self.room.add_item(Item("marker {0}".format(index))))

        COMMANDS["drop"].execute(self.session, hat.name)

        self.assertIn(hat, self.player.inventory)
        self.assertIs(self.player.equipment[hat.worn_where], hat)
        self.assertEqual(self.player.fabulousness, 10)
        self.assertEqual(len(self.room.items), ROOM_ITEM_LIMIT)
        self.assertIn("no safe place", self.session.messages[-1])

    def test_room_add_item_and_bling_enforce_the_same_hard_limit(self):
        for index in range(ROOM_ITEM_LIMIT):
            self.assertTrue(self.room.add_item(Item("marker {0}".format(index))))

        self.assertFalse(self.room.add_item(Item("overflow")))
        COMMANDS["bling"].execute(self.session, "")

        self.assertEqual(len(self.room.items), ROOM_ITEM_LIMIT)
        self.assertIn("no safe place", self.session.messages[-1])

    def test_full_inventory_does_not_consume_possum_reward_entitlement(self):
        alley = SuspiciousAlley()
        alley.enter(self.player, announce=False)

        try:
            alley.on_command(self.session, "search", "bin")
            hat = PimpHat()
            self.player.inventory.append(hat)
            alley.on_command(self.session, "offer", "pimp hat")
            self.player.inventory = [
                PimpHat()
                for unused in range(PLAYER_INVENTORY_LIMIT)
            ]

            alley.on_command(self.session, "pet", "possum")
            self.assertNotIn(self.player.name.lower(), alley.rewarded_players)
            self.assertFalse(any(
                isinstance(item, RoyalPossumBottleCap)
                for item in self.player.inventory
            ))

            self.player.inventory.pop()
            alley.on_command(self.session, "pet", "possum")
            self.assertIn(self.player.name.lower(), alley.rewarded_players)
            self.assertTrue(any(
                isinstance(item, RoyalPossumBottleCap)
                for item in self.player.inventory
            ))
        finally:
            if alley.possum.room is alley:
                alley.remove_npc(alley.possum)

    def test_full_inventory_does_not_deplete_shared_acorn_supply(self):
        state = VillageState()
        canopy = HangingTreeCanopy(state)
        canopy.enter(self.player, announce=False)
        self.player.inventory = [
            PimpHat()
            for unused in range(PLAYER_INVENTORY_LIMIT)
        ]
        before = state.tree_snapshot()

        canopy.on_command(self.session, "harvest", "acorn")

        self.assertEqual(state.tree_snapshot(), before)
        self.assertEqual(
            len(self.player.inventory),
            PLAYER_INVENTORY_LIMIT
        )


if __name__ == "__main__":
    unittest.main()
