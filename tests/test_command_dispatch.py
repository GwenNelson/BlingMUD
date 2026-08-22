import unittest

import blingmud
from core import (
    COMMANDS,
    Command,
    CommandSpec,
    Player,
    RESERVED_GLOBAL_COMMANDS,
    Room,
    find_command_spec,
    register_command
)


class RecordingRequest(object):
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def shutdown(self, how):
        pass

    def close(self):
        pass


class OverrideRoom(Room):
    command_specs = (
        CommandSpec(
            "look",
            "/look",
            "Use the room-specific look implementation.",
            aliases=("l",)
        ),
    )

    def __init__(self):
        Room.__init__(self, "override", "Override", "Global description.")
        self.calls = []

    def on_command(self, session, command, arguments):
        self.calls.append((command, arguments))

        if command in ("look", "l"):
            session.send("Room-specific look.")
            return True

        # A malicious or mistaken room may try to claim these even though it
        # cannot declare them in command_specs. Dispatch must still bypass it.
        if command in RESERVED_GLOBAL_COMMANDS:
            session.send("Room improperly claimed reserved command.")
            return True

        return False


class CommandDispatchTests(unittest.TestCase):
    def setUp(self):
        self.room = OverrideRoom()
        self.request = RecordingRequest()
        self.session = blingmud.Session(
            self.request,
            ("127.0.0.1", 0),
            blingmud.WORLD
        )
        self.player = Player("Dispatcher")
        self.player.session = self.session
        self.session.player = self.player
        self.room.enter(self.player, announce=False)

    def tearDown(self):
        if self.player.room is self.room:
            self.room.leave(self.player, announce=False)

        for name in ("new_duplicate_test",):
            COMMANDS.pop(name, None)

    def transcript(self):
        return b"".join(self.request.sent).decode("utf-8", "replace")

    def test_room_primary_and_alias_override_global_commands(self):
        self.session.handle_command("/look")
        self.session.handle_command("/l target")

        self.assertEqual(
            self.room.calls,
            [("look", ""), ("l", "target")]
        )
        self.assertEqual(self.transcript().count("Room-specific look."), 2)
        self.assertNotIn("Global description", self.transcript())

    def test_reserved_unknown_command_bypasses_room(self):
        self.session.handle_command("/shutdown 30 maintenance")

        self.assertEqual(self.room.calls, [])
        self.assertIn("Unknown command: /shutdown", self.transcript())
        self.assertNotIn("improperly claimed", self.transcript())

    def test_reserved_global_alias_bypasses_room_and_executes_global(self):
        self.session.handle_command("/exit")

        self.assertEqual(self.room.calls, [])
        self.assertFalse(self.session.running)
        self.assertIn("Goodbye!", self.transcript())

    def test_room_help_spec_takes_precedence_over_global_spec(self):
        spec = find_command_spec(self.session, "look")

        self.assertEqual(
            spec.summary,
            "Use the room-specific look implementation."
        )

        COMMANDS["help"].execute(self.session, "look")
        self.assertIn("room-specific look", self.transcript())

    def test_duplicate_primary_name_is_rejected_without_mutation(self):
        original = COMMANDS["look"]

        class DuplicateLook(Command):
            name = "look"
            usage = "/look"
            summary = "A duplicate."

            def execute(self, session, arguments):
                pass

        with self.assertRaises(ValueError):
            register_command(DuplicateLook)

        self.assertIs(COMMANDS["look"], original)

    def test_duplicate_alias_is_rejected_atomically(self):
        class DuplicateAlias(Command):
            name = "new_duplicate_test"
            aliases = ("look",)
            usage = "/new_duplicate_test"
            summary = "A duplicate alias."

            def execute(self, session, arguments):
                pass

        with self.assertRaises(ValueError):
            register_command(DuplicateAlias)

        self.assertNotIn("new_duplicate_test", COMMANDS)

    def test_room_cannot_declare_reserved_command_or_alias(self):
        class UnsafeRoom(Room):
            command_specs = (
                CommandSpec(
                    "local",
                    "/local",
                    "Unsafe alias.",
                    aliases=("kick",)
                ),
            )

        with self.assertRaises(ValueError):
            UnsafeRoom("unsafe", "Unsafe", "Unsafe room.")


if __name__ == "__main__":
    unittest.main()
