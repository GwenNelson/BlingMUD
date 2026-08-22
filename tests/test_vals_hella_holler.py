import unittest

import blingmud
from core import COMMANDS, FSMBehavior, MAX_INTOXICATION, Player
from items.drinks import HornBornSpecial, ValHealingPotion, ValkyrieMead
from rooms.vals_hella_holler import ValsHellaHoller
from village_state import VillageState


class FixedRandom(object):
    def choice(self, choices):
        return choices[0]


class RecordingSession(object):
    def __init__(self, player):
        self.player = player
        self.messages = []
        player.session = self

    def send(self, message):
        self.messages.append(message)

    def damage_player(self, amount, cause):
        damage = self.player.take_damage(amount)

        if self.player.health == 0:
            self.player.health = 1
            self.player.intoxication = 0
            self.player.recently_respawned = True

        return damage


class ValsHellaHollerTests(unittest.TestCase):
    def setUp(self):
        self.state = VillageState()
        self.room = ValsHellaHoller(
            self.state,
            random_source=FixedRandom()
        )
        self.player = Player("Adventurer")
        self.session = RecordingSession(self.player)
        self.room.enter(self.player, announce=False)
        self.session.messages = []

    def tearDown(self):
        for player in list(self.room.players):
            self.room.leave(player, announce=False)

        if self.room.val.room is self.room:
            self.room.remove_npc(self.room.val)

    def transcript(self):
        return "\n".join(self.session.messages)

    def test_world_connects_holler_to_green_without_replacing_start(self):
        world = blingmud.WORLD
        green = world.rooms["village_green"]
        tavern = world.rooms["vals_hella_holler"]

        self.assertIsInstance(tavern, ValsHellaHoller)
        self.assertIs(tavern.village_state, world.village_state)
        self.assertIs(green.exits["north"], tavern)
        self.assertIs(tavern.exits["south"], green)
        self.assertIs(world.starting_room, world.rooms["town_square"])

    def test_description_preserves_the_brainstormed_tavern_identity(self):
        self.room.describe_to(self.player)
        transcript = self.transcript().lower()

        for detail in (
            "river-rock",
            "tiled roof",
            "fireplaces",
            "candles",
            "private wall booths",
            "bard platform",
            "tree-trunk bar",
            "exotic bottles",
            "cats",
            "cow horn"
        ):
            self.assertIn(detail, transcript)

    def test_val_is_a_local_fsm_and_reacts_to_conversation(self):
        self.assertIsInstance(self.room.val.behavior, FSMBehavior)
        self.assertEqual(
            self.room.val.behavior_mode,
            FSMBehavior.MODE_FSM
        )

        self.room.notify_player_said(self.player, "Hello, Val")
        self.assertIn("Val is short for Valkyrie", self.transcript())

        self.session.messages = []
        self.room.notify_player_said(self.player, "May I order mead?")
        self.assertIn("/order", self.transcript())

    def test_ordering_creates_bounded_concrete_drinks_with_two_actions(self):
        cases = (
            ("healing potion", ValHealingPotion),
            ("mead", ValkyrieMead),
            ("moonlight with a bad attitude", HornBornSpecial)
        )

        for concept, expected_type in cases:
            self.session.messages = []

            self.assertTrue(
                self.room.on_command(self.session, "order", concept)
            )
            self.assertIsInstance(self.player.inventory[-1], expected_type)
            transcript = self.transcript()
            self.assertIn("impossible colours", transcript)
            self.assertIn("On the house", transcript)
            self.assertIn("/drink", transcript)

    def test_order_rejects_empty_overlong_and_full_inventory_requests(self):
        self.room.on_command(self.session, "order", "")
        self.assertIn("Order what", self.session.messages[-1])

        self.room.on_command(self.session, "order", "x" * 81)
        self.assertIn("eighty", self.session.messages[-1])
        self.assertEqual(self.player.inventory, [])

        self.player.inventory = [
            ValHealingPotion()
            for unused in range(100)
        ]
        self.room.on_command(self.session, "order", "mead")
        self.assertEqual(len(self.player.inventory), 100)
        self.assertIn("cannot carry", self.session.messages[-1])

    def test_drinking_applies_real_clamped_effects_and_consumes_items(self):
        potion = ValHealingPotion()
        mead = ValkyrieMead()
        special = HornBornSpecial()
        self.player.inventory = [potion, mead, special]
        self.player.health = 50

        COMMANDS["drink"].execute(self.session, potion.name)
        self.assertEqual(self.player.health, 85)
        self.assertNotIn(potion, self.player.inventory)

        COMMANDS["drink"].execute(self.session, mead.name)
        self.assertEqual(self.player.intoxication, 20)
        self.assertNotIn(mead, self.player.inventory)

        COMMANDS["drink"].execute(self.session, special.name)
        self.assertEqual(self.player.health, 95)
        self.assertEqual(self.player.intoxication, 28)
        self.assertNotIn(special, self.player.inventory)

    def test_intoxication_refusal_preserves_alcohol_but_not_medicine(self):
        mead = ValkyrieMead()
        potion = ValHealingPotion()
        self.player.inventory = [mead, potion]
        self.player.intoxication = MAX_INTOXICATION
        self.player.health = 10

        COMMANDS["drink"].execute(self.session, mead.name)
        self.assertIn(mead, self.player.inventory)
        self.assertEqual(self.player.intoxication, MAX_INTOXICATION)
        self.assertIn("too intoxicated", self.session.messages[-1])

        COMMANDS["drink"].execute(self.session, potion.name)
        self.assertNotIn(potion, self.player.inventory)
        self.assertEqual(self.player.health, 45)

    def test_val_notices_health_intoxication_and_shared_wisp_harm(self):
        injured = Player("Injured")
        injured_session = RecordingSession(injured)
        injured.health = 50
        self.room.enter(injured, announce=False)
        self.assertIn("half-dead", "\n".join(injured_session.messages))

        tipsy = Player("Tipsy")
        tipsy_session = RecordingSession(tipsy)
        tipsy.intoxication = 60
        self.room.enter(tipsy, announce=False)
        self.assertIn("Water and a chair", "\n".join(tipsy_session.messages))

        self.state.attack_wisp(100.0)
        witness = Player("Witness")
        witness_session = RecordingSession(witness)
        self.room.enter(witness, announce=False)
        transcript = "\n".join(witness_session.messages)
        self.assertIn("harmed the Wisp Mother", transcript)
        self.assertIn("every tavern cat goes still", transcript)

    def test_room_commands_cover_joke_lore_flirt_call_and_examination(self):
        commands = (
            ("joke", "val", "murderous management"),
            ("talk", "val", "fled Asgard"),
            ("flirt", "val", "review your application"),
            ("call", "val", "efficient staffing"),
            ("examine", "horn", "measurable tavern item"),
            ("inspect", "cats", "watching your hands"),
            ("examine", "bar", "immense fallen limb")
        )

        for command, arguments, expected in commands:
            self.session.messages = []
            self.assertTrue(
                self.room.on_command(self.session, command, arguments)
            )
            self.assertIn(expected, self.transcript())

    def test_attacking_val_triggers_cats_and_shared_collapse_rule(self):
        self.player.health = 3

        self.assertTrue(
            self.room.on_command(self.session, "attack", "val")
        )

        self.assertEqual(self.player.health, 1)
        self.assertTrue(self.player.recently_respawned)
        self.assertIn("Every tavern cat", self.transcript())
        self.assertIn("for 3 health", self.transcript())

        self.session.messages = []
        self.player.health = 0
        self.room.on_command(self.session, "hit", "val")
        self.assertEqual(self.player.health, 1)
        self.assertIn("for 0 health", self.transcript())

    def test_val_recognizes_and_consumes_recent_collapse_status(self):
        self.player.recently_respawned = True
        self.room.val.on_player_enter(self.player)
        self.assertIn("freshly-collapsed", self.transcript())
        self.assertFalse(self.player.recently_respawned)

    def test_unknown_room_command_remains_unhandled(self):
        self.assertFalse(
            self.room.on_command(self.session, "definitely_unknown", "")
        )


if __name__ == "__main__":
    unittest.main()
