import re
import unittest

import blingmud
from core import COMMANDS, Player, find_command_spec
from items.drinks import AcornGoblet, HornBornSpecial
from items.food import AcornMash
from items.pimp_hat import PimpHat
from items.possum_token import RoyalPossumBottleCap
from player_state import restore_player_state, serialize_player_state


ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


class RecordingRequest(object):
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def shutdown(self, how):
        pass

    def close(self):
        pass


class WorldUserExpectationTests(unittest.TestCase):
    def setUp(self):
        self.world = blingmud.World()
        self.request = RecordingRequest()
        self.session = blingmud.Session(
            self.request,
            ("127.0.0.1", 0),
            self.world
        )
        self.player = Player("WorldAuditor")
        self.player.session = self.session
        self.session.player = self.player

    def tearDown(self):
        if self.player.room is not None:
            self.player.room.leave(self.player, announce=False)
        for room in self.world.rooms.values():
            for npc in list(room.npcs):
                room.remove_npc(npc)

    def enter(self, room):
        if self.player.room is not None:
            self.player.room.leave(self.player, announce=False)
        room.enter(self.player, announce=False)
        self.request.sent = []

    def transcript(self):
        encoded = b"".join(self.request.sent).decode("utf-8", "replace")
        return ANSI_ESCAPE.sub("", encoded)

    def run_command(self, command, arguments=""):
        line = "/" + command
        if arguments:
            line += " " + arguments
        self.request.sent = []
        self.session.handle_command(line)
        return self.transcript()

    def test_every_room_is_reachable_and_every_exit_round_trips(self):
        reached = {self.world.starting_room}
        pending = [self.world.starting_room]
        while pending:
            room = pending.pop()
            for destination in room.exits.values():
                if destination not in reached:
                    reached.add(destination)
                    pending.append(destination)

        self.assertEqual(reached, set(self.world.rooms.values()))

        for room in self.world.rooms.values():
            for direction, destination in room.exits.items():
                with self.subTest(room=room.room_id, direction=direction):
                    self.assertIn(direction, COMMANDS)
                    self.assertTrue(any(
                        return_room is room
                        for return_room in destination.exits.values()
                    ))
                    self.enter(room)
                    transcript = self.run_command(direction)
                    self.assertIs(self.player.room, destination)
                    self.assertNotIn("Unknown command", transcript)

    def test_bare_look_and_alias_show_every_room_and_exit(self):
        for room in self.world.rooms.values():
            self.enter(room)
            for command in ("look", "l"):
                with self.subTest(room=room.room_id, command=command):
                    transcript = self.run_command(command)
                    self.assertIn(room.name, transcript)
                    if room.exits:
                        self.assertIn("Exits:", transcript)
                        for direction in room.exits:
                            self.assertIn(direction, transcript)
                    else:
                        self.assertIn("There are no obvious exits.", transcript)

    def test_every_advertised_room_name_and_alias_is_claimed(self):
        for room in self.world.rooms.values():
            self.enter(room)
            for spec in room.command_specs:
                for command in spec.names:
                    with self.subTest(room=room.room_id, command=command):
                        resolved = find_command_spec(self.session, command)
                        self.assertIsNotNone(resolved)
                        self.assertEqual(resolved.name, spec.name)
                        transcript = self.run_command(command)
                        self.assertTrue(transcript.strip())
                        self.assertNotIn("Unknown command", transcript)

    def test_representative_valid_form_of_every_room_feature_dispatches(self):
        cases = {
            "ceridwens_cottage": (
                ("examine", "pot", "cottage contains"),
                ("buy", "salve", "rare weed"),
                ("give", "weed", "needs a rare weed"),
            ),
            "corbels_turnery": (
                ("trade", "acorn", "need a giant acorn"),
                ("craft", "goblet", "need a giant acorn"),
                ("buy", "mash", "enough coins"),
                ("examine", "corbel", "Master Corbel"),
            ),
            "hanging_tree_canopy": (
                ("harvest", "acorn", "wrestle a giant acorn"),
            ),
            "overgrown_herb_garden": (
                ("examine", "garden", "disorienting"),
                ("harvest", "weed", "harvest one rare weed"),
            ),
            "smithereens": (
                ("browse", "scrap", "scrap rack"),
                ("examine", "hammer", "Tackdriver"),
                ("listen", "hammer", "means of production"),
                ("talk", "hammer", "who owns the forge"),
            ),
            "suspicious_alley": (
                ("search", "bin", "demands tribute"),
                ("offer", "hat to possum", "not carrying"),
                ("pet", "possum", "Tribute first"),
            ),
            "temple_of_self": (
                ("examine", "mirror", "health"),
                ("look", "mirror", "health"),
                ("sit", "", "recover"),
                ("meditate", "", "recover"),
                ("read", "book", "Tome of Indulgence"),
                ("reforge", "self", "not yet unlocked"),
                ("alter", "stats", "not yet unlocked"),
            ),
            "vals_hella_holler": (
                ("order", "mead", "On the house"),
                ("joke", "val", "Val"),
                ("talk", "val", "Asgard"),
                ("flirt", "val", "application"),
                ("call", "val", "efficient staffing"),
                ("examine", "horn", "measurable tavern item"),
                ("attack", "val", "cats enforce"),
            ),
            "village_green": (
                ("examine", "wisp mother", "says nothing"),
                ("protect", "wisp mother", "ward"),
                ("attack", "wisp mother", "survives"),
            ),
        }

        advertised = {
            (room_id, spec.name)
            for room_id, room in self.world.rooms.items()
            for spec in room.command_specs
        }
        covered = {
            (room_id, command)
            for room_id, commands in cases.items()
            for command, unused_arguments, unused_expected in commands
        }
        self.assertEqual(covered, advertised)

        for room_id, commands in cases.items():
            self.enter(self.world.rooms[room_id])
            for command, arguments, expected in commands:
                with self.subTest(room=room_id, command=command):
                    transcript = self.run_command(command, arguments)
                    self.assertNotIn("Unknown command", transcript)
                    self.assertIn(expected.lower(), transcript.lower())

    def test_possum_journey_accepts_equipped_tribute_and_awards_once(self):
        self.enter(self.world.starting_room)
        self.run_command("east")
        self.assertIn("demands tribute", self.run_command("search", "bin"))
        self.run_command("bling")
        self.run_command("take", "pimp hat")
        self.run_command("equip", "pimp hat")
        self.assertEqual(self.player.fabulousness, 10)

        transcript = self.run_command("offer", "pimp hat to possum")

        self.assertIn("accepts your tribute", transcript)
        self.assertEqual(self.player.fabulousness, 0)
        self.assertFalse(any(
            isinstance(item, PimpHat) for item in self.player.inventory
        ))
        self.assertEqual(self.player.equipment, {})

        self.run_command("pet", "possum")
        second_pet = self.run_command("stroke", "the possum")
        rewards = [
            item for item in self.player.inventory
            if isinstance(item, RoyalPossumBottleCap)
        ]
        self.assertEqual(len(rewards), 1)
        self.assertIn("only once", second_pet)

    def test_ceridwen_journey_harvests_unlocks_buys_and_consumes(self):
        self.enter(self.world.starting_room)
        self.player.coins = 3
        for command in ("west", "northeast", "east"):
            self.run_command(command)

        self.assertIn("harvest one rare weed", self.run_command(
            "harvest", "weed"
        ).lower())
        self.run_command("west")
        self.assertIn("unlocks", self.run_command("give", "weed"))
        self.assertIn("sells", self.run_command("buy", "experimental"))
        self.assertEqual(self.player.coins, 0)
        self.assertEqual(len(self.player.inventory), 1)
        self.assertIsInstance(self.player.inventory[0], HornBornSpecial)

        transcript = self.run_command("drink", "horn-born special")

        self.assertIn("adds 8 intoxication", transcript)
        self.assertEqual(self.player.intoxication, 8)
        self.assertEqual(self.player.inventory, [])

    def test_acorn_economy_journey_reaches_val_and_survives_restore(self):
        self.enter(self.world.starting_room)
        self.run_command("west")

        for unused in range(2):
            self.run_command("up")
            self.assertIn("wrestle a giant acorn", self.run_command(
                "harvest", "acorn"
            ))
            self.run_command("down")
            self.run_command("west")
            self.assertIn("receive 5 coins", self.run_command(
                "trade", "acorn"
            ))
            self.run_command("east")

        self.run_command("west")
        self.assertIn("buy acorn goblet", self.run_command(
            "buy", "goblet"
        ))
        self.assertIn("buy acorn mash", self.run_command("buy", "mash"))
        self.assertEqual(self.player.coins, 0)
        self.run_command("east")
        self.run_command("north")

        self.assertIn("acorn goblet", self.run_command("order", "mead"))
        drink_result = self.run_command("drink", "acorn goblet")
        self.assertIn("honey", drink_result)
        self.assertIn("Intoxication rises by 20", drink_result)
        goblet = next(
            item for item in self.player.inventory
            if isinstance(item, AcornGoblet)
        )
        self.assertIsNone(goblet.held_drink)

        self.player.health = 90
        self.assertIn("restores 8 health", self.run_command(
            "eat", "acorn mash"
        ))
        self.assertEqual(self.player.health, 98)
        self.assertFalse(any(
            isinstance(item, AcornMash) for item in self.player.inventory
        ))

        restored = Player("RestoredEconomist")
        restored_room = restore_player_state(
            restored,
            serialize_player_state(self.player),
            self.world,
            time_source=lambda: self.player.last_status_update
        )
        self.assertIs(restored_room, self.player.room)
        self.assertEqual(restored.coins, 0)
        self.assertEqual(restored.intoxication, 20)
        self.assertEqual(len(restored.inventory), 1)
        self.assertIsInstance(restored.inventory[0], AcornGoblet)
        self.assertIsNone(restored.inventory[0].held_drink)

    def test_wisp_consequence_collapse_and_temple_recovery_journey(self):
        self.enter(self.world.starting_room)
        self.run_command("west")
        self.assertIn("ward", self.run_command("protect", "wisp mother"))
        self.assertIn("survives", self.run_command("attack", "wisp mother"))
        self.assertIn("remember", self.run_command("attack", "wisp mother"))
        self.assertIn("unnaturally dark", self.run_command("look"))

        self.player.health = 3
        self.run_command("north")
        self.assertIn("harmed the Wisp Mother", self.transcript())
        collapse = self.run_command("attack", "val")
        self.assertIn("You collapse", collapse)
        self.assertIs(self.player.room, self.world.starting_room)
        self.assertEqual(self.player.health, 1)
        self.assertTrue(self.player.recently_respawned)

        self.run_command("west")
        self.run_command("south")
        self.assertIn("recover 5 health", self.run_command("meditate"))
        reflection = self.run_command("look", "mirror")
        self.assertIn("health 6/100", reflection)
        self.assertEqual(self.player.health, 6)


if __name__ == "__main__":
    unittest.main()
