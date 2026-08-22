import unittest

import blingmud
from core import COMMANDS, Item, Player, Room
from items.pimp_hat import PimpHat


class RecordingSession(object):
    def __init__(self, player):
        self.player = player
        self.messages = []
        player.session = self

    def send(self, message):
        self.messages.append(message)


class CountingWearable(Item):
    def __init__(self):
        Item.__init__(
            self,
            "counting boots",
            wearable=True,
            worn_where="Feet"
        )
        self.unequip_calls = 0

    def on_unequip(self, player):
        self.unequip_calls += 1


class UnequipCommandTests(unittest.TestCase):
    def setUp(self):
        self.room = Room("wardrobe", "Wardrobe", "A test wardrobe.")
        self.player = Player("Dresser")
        self.session = RecordingSession(self.player)
        self.room.enter(self.player, announce=False)

    def tearDown(self):
        if self.player.room is self.room:
            self.room.leave(self.player, announce=False)

    def equip_hat(self):
        hat = PimpHat()
        self.player.inventory.append(hat)
        self.player.equipment[hat.worn_where] = hat
        hat.on_equip(self.player)
        return hat

    def test_unequip_by_item_name_keeps_item_and_removes_effect(self):
        hat = self.equip_hat()
        self.assertEqual(self.player.fabulousness, 10)

        COMMANDS["unequip"].execute(self.session, "pimp hat")

        self.assertIn(hat, self.player.inventory)
        self.assertNotIn(hat, self.player.equipment.values())
        self.assertEqual(self.player.fabulousness, 0)
        self.assertIn("unequip", self.session.messages[-1])

    def test_unequip_by_slot_is_case_insensitive(self):
        hat = self.equip_hat()

        COMMANDS["unequip"].execute(self.session, "HEAD")

        self.assertNotIn("Head", self.player.equipment)
        self.assertIn(hat, self.player.inventory)

    def test_remove_alias_is_the_same_command(self):
        self.assertIs(COMMANDS["remove"], COMMANDS["unequip"])

        hat = self.equip_hat()
        COMMANDS["remove"].execute(self.session, "head")

        self.assertNotIn(hat, self.player.equipment.values())

    def test_unequip_callback_runs_exactly_once(self):
        boots = CountingWearable()
        self.player.inventory.append(boots)
        self.player.equipment[boots.worn_where] = boots

        COMMANDS["unequip"].execute(self.session, "feet")

        self.assertEqual(boots.unequip_calls, 1)
        self.assertNotIn("Feet", self.player.equipment)

    def test_missing_argument_or_item_does_not_mutate_equipment(self):
        hat = self.equip_hat()

        COMMANDS["unequip"].execute(self.session, "")
        self.assertIn("Unequip what", self.session.messages[-1])

        COMMANDS["unequip"].execute(self.session, "boots")
        self.assertIn("not wearing", self.session.messages[-1])
        self.assertIs(self.player.equipment["Head"], hat)

    def test_command_metadata_is_available_to_help_and_completion(self):
        spec = COMMANDS["unequip"].command_spec()

        self.assertEqual(spec.usage, "/unequip <item or slot>")
        self.assertIn("remove", spec.aliases)
        self.assertEqual(
            blingmud.complete_command_text(self.session, "/rem"),
            ("/unequip ", ("unequip",))
        )


if __name__ == "__main__":
    unittest.main()
