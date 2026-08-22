import unittest

import blingmud
from core import Item, NPCManager, Player
from items.pimp_hat import PimpHat
from items.possum_token import RoyalPossumBottleCap
from npcs.bin_possum import BinPossumBehavior
from rooms.suspicious_alley import SuspiciousAlley


class RecordingSession(object):
    def __init__(self, player):
        self.player = player
        self.messages = []
        player.session = self

    def send(self, message):
        self.messages.append(message)


class SuspiciousAlleyTests(unittest.TestCase):
    def setUp(self):
        self.room = SuspiciousAlley()
        self.player = Player("Searcher")
        self.session = RecordingSession(self.player)
        self.room.enter(self.player, announce=False)

    def tearDown(self):
        if self.player in self.room.players:
            self.room.leave(self.player, announce=False)

        if self.room.possum.room is self.room:
            self.room.remove_npc(self.room.possum)

    def reveal_possum(self):
        self.assertTrue(
            self.room.on_command(self.session, "search", "bin")
        )

    def make_possum_friendly(self):
        self.reveal_possum()
        hat = PimpHat()
        self.player.inventory.append(hat)
        self.assertTrue(
            self.room.on_command(self.session, "offer", "pimp hat")
        )
        return hat

    def test_world_uses_stateful_suspicious_alley(self):
        alley = blingmud.WORLD.rooms["suspicious_alley"]

        self.assertIsInstance(alley, SuspiciousAlley)
        self.assertIs(blingmud.WORLD.rooms["town_square"].exits["east"], alley)
        self.assertIs(alley.exits["west"], blingmud.WORLD.rooms["town_square"])

    def test_description_hints_at_search_without_revealing_npc(self):
        self.room.describe_to(self.player)

        self.assertFalse(self.room.possum_revealed)
        self.assertNotIn(self.room.possum, self.room.npcs)
        self.assertIn("/search", self.session.messages[-1])

    def test_search_reveals_and_registers_possum_only_once(self):
        manager = NPCManager.instance()

        self.reveal_possum()

        self.assertTrue(self.room.possum_revealed)
        self.assertIn(self.room.possum, self.room.npcs)
        self.assertIn(self.room.possum, manager.npcs)
        self.assertEqual(self.room.npcs.count(self.room.possum), 1)
        self.assertEqual(self.room.possum.behavior.current_state, "wary")

        self.room.on_command(self.session, "rummage", "the bin")

        self.assertEqual(self.room.npcs.count(self.room.possum), 1)
        self.assertIn("profound disapproval", self.session.messages[-1])

    def test_searching_other_targets_does_not_reveal_possum(self):
        self.room.on_command(self.session, "search", "gutter")

        self.assertFalse(self.room.possum_revealed)
        self.assertNotIn(self.room.possum, self.room.npcs)
        self.assertIn("bin-shaped", self.session.messages[-1])

    def test_offer_rejects_missing_and_insufficiently_fabulous_items(self):
        self.reveal_possum()

        self.room.on_command(self.session, "offer", "pimp hat")
        self.assertIn("not carrying", self.session.messages[-1])

        ordinary_item = Item("ordinary pebble")
        self.player.inventory.append(ordinary_item)
        self.room.on_command(self.session, "offer", "ordinary pebble")

        self.assertIn(ordinary_item, self.player.inventory)
        self.assertNotIn(ordinary_item, self.room.possum.inventory)
        self.assertEqual(
            self.room.possum.behavior.current_state,
            BinPossumBehavior.STATE_WARY
        )
        self.assertIn("standards", self.session.messages[-1])

    def test_offering_equipped_hat_removes_effect_and_befriends_possum(self):
        self.reveal_possum()
        hat = PimpHat()
        self.player.inventory.append(hat)
        self.player.equipment[hat.worn_where] = hat
        hat.on_equip(self.player)
        self.assertEqual(self.player.fabulousness, 10)

        self.room.on_command(
            self.session,
            "offer",
            "pimp hat to the possum"
        )

        self.assertNotIn(hat, self.player.inventory)
        self.assertNotIn(hat, self.player.equipment.values())
        self.assertEqual(self.player.fabulousness, 0)
        self.assertIn(hat, self.room.possum.inventory)
        self.assertEqual(
            self.room.possum.behavior.current_state,
            BinPossumBehavior.STATE_FRIENDLY
        )
        self.assertIn("pimp hat", self.room.possum.look(self.player))

    def test_target_first_offer_grammar_befriends_possum(self):
        self.reveal_possum()
        hat = PimpHat()
        self.player.inventory.append(hat)

        self.room.on_command(
            self.session,
            "offer",
            "possum pimp hat"
        )

        self.assertNotIn(hat, self.player.inventory)
        self.assertIn(hat, self.room.possum.inventory)
        self.assertEqual(
            self.room.possum.behavior.current_state,
            BinPossumBehavior.STATE_FRIENDLY
        )

    def test_offer_parser_accepts_implicit_item_first_and_both_orders(self):
        cases = {
            "pimp hat": "pimp hat",
            "pimp hat to possum": "pimp hat",
            "pimp hat to the possum": "pimp hat",
            "possum pimp hat": "pimp hat",
            "bin possum pimp hat": "pimp hat",
            "the possum pimp hat": "pimp hat",
            "the bin possum pimp hat": "pimp hat",
            "possum": ""
        }

        for arguments, expected in cases.items():
            self.assertEqual(
                self.room._offered_item_name(arguments),
                expected
            )

    def test_get_possum_recognizes_visible_npc_as_not_takeable(self):
        self.reveal_possum()
        self.session.messages = []

        blingmud.COMMANDS["get"].execute(self.session, "possum")

        self.assertIn("cannot pick up bin possum", self.session.messages[-1])
        self.assertNotIn("There is no", self.session.messages[-1])

    def test_friendly_possum_declines_additional_items_without_taking_them(self):
        self.make_possum_friendly()
        spare_hat = PimpHat()
        self.player.inventory.append(spare_hat)

        self.room.on_command(self.session, "offer", "pimp hat")

        self.assertIn(spare_hat, self.player.inventory)
        self.assertNotIn(spare_hat, self.room.possum.inventory)
        self.assertIn("declines", self.session.messages[-1])

    def test_pet_requires_reveal_and_friendship(self):
        self.room.on_command(self.session, "pet", "possum")
        self.assertIn("slaps your hand", self.session.messages[-1])

        self.reveal_possum()
        inventory_before = list(self.player.inventory)
        self.room.on_command(self.session, "pet", "possum")

        self.assertEqual(self.player.inventory, inventory_before)
        self.assertTrue(
            any("Tribute first" in message for message in self.session.messages)
        )

    def test_friendly_pet_awards_one_bottle_cap_per_player(self):
        self.make_possum_friendly()

        self.room.on_command(self.session, "pet", "bin possum")
        self.room.on_command(self.session, "stroke", "the possum")

        tokens = [
            item
            for item in self.player.inventory
            if isinstance(item, RoyalPossumBottleCap)
        ]
        self.assertEqual(len(tokens), 1)
        self.assertIn("only once", self.session.messages[-1])

    def test_possum_fsm_reacts_to_speech_in_both_states(self):
        self.reveal_possum()
        self.session.messages = []

        self.room.notify_player_said(
            self.player,
            "That is a fabulous hat-loving possum"
        )
        self.assertTrue(
            any("bright eyes" in message for message in self.session.messages)
        )

        self.make_possum_friendly()
        self.session.messages = []
        self.room.notify_player_said(self.player, "Hello, possum friend")
        self.assertTrue(
            any("alliance" in message for message in self.session.messages)
        )

    def test_unknown_room_command_remains_unhandled(self):
        self.assertFalse(
            self.room.on_command(self.session, "definitely_unknown", "")
        )


if __name__ == "__main__":
    unittest.main()
