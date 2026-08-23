import re
import unittest

import blingmud
from core import COMMANDS, Player, find_command_spec


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


if __name__ == "__main__":
    unittest.main()
