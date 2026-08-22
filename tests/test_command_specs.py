import unittest

import blingmud
from core import (
    COMMANDS,
    Command,
    CommandSpec,
    Player,
    command_specs_for_session,
    complete_command_text,
    find_command_spec
)
from rooms.suspicious_alley import SuspiciousAlley


class RecordingSession(object):
    def __init__(self, player):
        self.player = player
        self.messages = []
        player.session = self

    def send(self, message):
        self.messages.append(message)


class CommandSpecTests(unittest.TestCase):
    def setUp(self):
        self.room = SuspiciousAlley()
        self.player = Player("Helper")
        self.session = RecordingSession(self.player)
        self.room.enter(self.player, announce=False)

    def tearDown(self):
        if self.player.room is self.room:
            self.room.leave(self.player, announce=False)

        for name in ("secret_test", "st"):
            COMMANDS.pop(name, None)

    def test_every_registered_global_command_has_real_metadata(self):
        specs = command_specs_for_session(self.session, include_room=False)
        unique_commands = set(id(command) for command in COMMANDS.values())

        self.assertEqual(len(specs), len(unique_commands))

        for spec in specs:
            self.assertIsInstance(spec, CommandSpec)
            self.assertTrue(spec.usage.startswith("/"))
            self.assertNotEqual(spec.summary, "No description is available.")

    def test_help_is_generated_from_global_and_current_room_specs(self):
        COMMANDS["help"].execute(self.session, "")
        transcript = "\n".join(self.session.messages)

        self.assertIn("/look [object or person]", transcript)
        self.assertIn("/search <thing>", transcript)
        self.assertIn("/offer [possum] <item>", transcript)

    def test_help_lookup_accepts_alias_and_reports_aliases(self):
        COMMANDS["help"].execute(self.session, "get")
        transcript = "\n".join(self.session.messages)

        self.assertIn("/take <object>", transcript)
        self.assertIn("Aliases: /get", transcript)

    def test_room_specs_are_validated_objects(self):
        for spec in self.room.command_specs:
            self.assertIsInstance(spec, CommandSpec)

        self.assertEqual(find_command_spec(self.session, "rummage").name, "search")

    def test_command_spec_rejects_unsafe_or_incomplete_metadata(self):
        with self.assertRaises(ValueError):
            CommandSpec("Bad Name", "/bad", "Bad command")

        with self.assertRaises(ValueError):
            CommandSpec("bad", "bad", "Missing slash")

        class UndocumentedCommand(Command):
            name = "undocumented"

        with self.assertRaises(ValueError):
            UndocumentedCommand().command_spec()

    def test_non_admin_help_and_completion_hide_admin_only_commands(self):
        class SecretCommand(Command):
            name = "secret_test"
            aliases = ("st",)
            usage = "/secret_test"
            summary = "A hidden test command."
            admin_only = True

            def execute(self, session, arguments):
                pass

        secret = SecretCommand()
        COMMANDS["secret_test"] = secret
        COMMANDS["st"] = secret

        self.assertIsNone(find_command_spec(self.session, "secret_test"))
        self.assertEqual(
            complete_command_text(self.session, "/secret"),
            (None, ())
        )

        self.player.is_admin = True
        self.assertEqual(
            complete_command_text(self.session, "/secret"),
            ("/secret_test ", ("secret_test",))
        )

    def test_completion_canonicalizes_exact_alias_and_unique_prefix(self):
        self.assertEqual(
            complete_command_text(self.session, "/inv"),
            ("/inventory ", ("inventory",))
        )
        self.assertEqual(
            complete_command_text(self.session, "/off"),
            ("/offer ", ("offer",))
        )

    def test_completion_reports_bounded_ambiguous_candidates(self):
        replacement, candidates = complete_command_text(self.session, "/")

        self.assertIsNone(replacement)
        self.assertIn("west", candidates)
        self.assertIn("who", candidates)
        self.assertIn("worship", candidates)
        self.assertLessEqual(len(candidates), len(COMMANDS) + len(self.room.command_specs))

    def test_completion_only_operates_on_command_token(self):
        self.assertEqual(
            complete_command_text(self.session, "ordinary speech"),
            (None, ())
        )
        self.assertEqual(
            complete_command_text(self.session, "/look poss"),
            (None, ())
        )


if __name__ == "__main__":
    unittest.main()
