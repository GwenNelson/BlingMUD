import math
import unittest

import blingmud
from core import COMMANDS, Player
from items.giant_acorn import GiantAcorn
from npcs.falling_acorn import FallingAcornBehavior
from rooms.hanging_tree import HangingTreeCanopy
from rooms.village_green import VillageGreen
from village_state import VillageState


class FakeClock(object):
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class FixedRandom(object):
    def choice(self, choices):
        return choices[0]

    def uniform(self, minimum, maximum):
        return minimum

    def random(self):
        return 0.0


class RecordingSession(object):
    def __init__(self, player):
        self.player = player
        self.messages = []
        player.session = self

    def send(self, message):
        self.messages.append(message)

    def damage_player(self, amount, cause):
        return self.player.take_damage(amount)


class VillageGreenContentTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(100.0)
        self.random = FixedRandom()
        self.state = VillageState()
        self.is_night = True
        self.green = VillageGreen(
            self.state,
            time_source=self.clock,
            night_source=lambda: self.is_night,
            hazard_settings={
                "interval": 5.0,
                "random_source": self.random,
                "time_source": self.clock
            }
        )
        self.canopy = HangingTreeCanopy(self.state)
        self.green.add_exit("up", self.canopy)
        self.canopy.add_exit("down", self.green)
        self.player = Player("Climber")
        self.session = RecordingSession(self.player)
        self.green.enter(self.player, announce=False)

    def tearDown(self):
        if self.player.room is not None:
            self.player.room.leave(self.player, announce=False)

        if self.green.wisp_mother.room is self.green:
            self.green.remove_npc(self.green.wisp_mother)

        if self.green.acorn_hazard.room is self.green:
            self.green.remove_npc(self.green.acorn_hazard)

    def test_world_connects_green_and_canopy_without_replacing_start(self):
        world = blingmud.WORLD
        green = world.rooms["village_green"]
        canopy = world.rooms["hanging_tree_canopy"]

        self.assertIsInstance(green, VillageGreen)
        self.assertIsInstance(canopy, HangingTreeCanopy)
        self.assertIs(green.village_state, world.village_state)
        self.assertIs(canopy.village_state, world.village_state)
        self.assertIs(world.rooms["town_square"].exits["west"], green)
        self.assertIs(green.exits["east"], world.rooms["town_square"])
        self.assertIs(green.exits["up"], canopy)
        self.assertIs(canopy.exits["down"], green)
        self.assertIs(world.starting_room, world.rooms["town_square"])
        self.assertIn("up", COMMANDS)
        self.assertIn("down", COMMANDS)

    def test_night_description_uses_wisps_and_hides_hazard_actor(self):
        self.green.describe_to(self.player)

        transcript = "\n".join(self.session.messages)
        people_lines = [
            message
            for message in self.session.messages
            if message.startswith("People here:")
        ]
        self.assertIn("living lanterns", transcript)
        self.assertIn("Wisp Mother", people_lines[0])
        self.assertNotIn("Hanging Tree", people_lines[0])

        self.is_night = False
        self.session.messages = []
        self.green.describe_to(self.player)
        self.assertIn("broad green commons", "\n".join(self.session.messages))

    def test_wisp_mother_is_wordless_but_examine_emits_warm_light(self):
        self.assertEqual(self.green.wisp_mother.behavior.speech, ())

        self.assertTrue(
            self.green.on_command(
                self.session,
                "examine",
                "wisp mother"
            )
        )

        transcript = "\n".join(self.session.messages)
        self.assertIn("gentle pulse", transcript)
        self.assertIn("says nothing", transcript)

    def test_protection_blocks_one_attack_then_harm_darkens_green(self):
        self.green.on_command(self.session, "protect", "wisp mother")
        self.assertTrue(self.state.wisp_snapshot()["warded"])

        self.green.on_command(self.session, "attack", "wisp mother")
        after_ward = self.state.wisp_snapshot()
        self.assertTrue(after_ward["present"])
        self.assertFalse(after_ward["warded"])
        self.assertEqual(after_ward["harmed_count"], 0)
        self.assertIs(self.green.wisp_mother.room, self.green)

        self.green.on_command(self.session, "hit", "wisp")
        after_harm = self.state.wisp_snapshot()
        self.assertFalse(after_harm["present"])
        self.assertEqual(after_harm["harmed_count"], 1)
        self.assertIsNone(self.green.wisp_mother.room)

        self.session.messages = []
        self.green.describe_to(self.player)
        transcript = "\n".join(self.session.messages)
        self.assertIn("unnaturally dark", transcript)
        self.assertNotIn(
            self.green.wisp_mother,
            self.green.npcs
        )

        self.clock.now += VillageState.WISP_DARK_SECONDS
        self.session.messages = []
        self.green.describe_to(self.player)
        self.assertTrue(self.state.wisp_snapshot()["present"])
        self.assertIs(self.green.wisp_mother.room, self.green)

    def test_harvest_and_gather_produce_bounded_acorns_and_reduce_danger(self):
        self.canopy.enter(self.player, announce=False)

        self.assertTrue(
            self.canopy.on_command(self.session, "harvest", "acorn")
        )
        self.assertEqual(self.state.tree_snapshot()["danger"], 2)
        self.assertEqual(
            len([
                item
                for item in self.player.inventory
                if isinstance(item, GiantAcorn)
            ]),
            1
        )

        self.canopy.on_command(self.session, "gather", "giant acorn")
        self.assertEqual(self.state.tree_snapshot()["danger"], 2)
        self.assertIn("enough to carry", self.session.messages[-1])

        self.player.inventory = []
        self.canopy.on_command(self.session, "gather", "acorns")
        self.assertEqual(self.state.tree_snapshot()["danger"], 1)

    def test_acorn_supply_has_a_hard_runtime_bound(self):
        harvested = [
            self.state.harvest_acorn()
            for unused in range(VillageState.INITIAL_ACORN_SUPPLY)
        ]

        self.assertNotIn(None, harvested)
        self.assertIsNone(self.state.harvest_acorn())
        self.assertEqual(
            self.state.tree_snapshot(),
            {
                "danger": 0,
                "supply": 0,
                "harvested": VillageState.INITIAL_ACORN_SUPPLY
            }
        )

    def test_low_harvest_hazard_bonks_only_until_green_is_safe(self):
        starting_health = self.player.health
        self.clock.now = 105.0
        self.green.acorn_hazard.tick()
        self.assertTrue(
            any("Bonk" in message for message in self.session.messages)
        )
        self.assertEqual(self.player.health, starting_health - 1)

        self.state.harvest_acorn()
        self.state.harvest_acorn()
        self.state.harvest_acorn()
        messages_before = list(self.session.messages)
        self.clock.now = 110.0
        self.green.acorn_hazard.tick()
        self.assertEqual(self.session.messages, messages_before)

    def test_unknown_room_commands_remain_unhandled(self):
        self.assertFalse(
            self.green.on_command(self.session, "definitely_unknown", "")
        )
        self.assertFalse(
            self.canopy.on_command(self.session, "definitely_unknown", "")
        )

    def test_new_green_respects_an_existing_wisp_absence(self):
        state = VillageState()
        state.attack_wisp(self.clock.now)
        green = VillageGreen(
            state,
            time_source=self.clock,
            night_source=lambda: True,
            hazard_settings={
                "interval": 5.0,
                "random_source": self.random,
                "time_source": self.clock
            }
        )

        try:
            self.assertIsNone(green.wisp_mother.room)
            self.assertNotIn(green.wisp_mother, green.npcs)
            self.assertIn("unnaturally dark", green.description_for(None))
        finally:
            green.remove_npc(green.acorn_hazard)

    def test_invalid_hazard_intervals_are_rejected(self):
        for value in (True, "fast"):
            with self.assertRaises(TypeError):
                FallingAcornBehavior(self.state, interval=value)

        for value in (0, -1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                FallingAcornBehavior(self.state, interval=value)


if __name__ == "__main__":
    unittest.main()
