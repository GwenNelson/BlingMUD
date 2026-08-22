import unittest
import hashlib
import io
import os
import stat
import sys
import tempfile

import blingmud
from core import (
    Item,
    NPC,
    NPCAction,
    NPCBehavior,
    NPCManager,
    Player,
    Room,
    SimpleRandomBehavior
)
from npcs.brave_sir_knight import BraveSirKnight


class DummyRequest(object):
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, size):
        return b""


class HandleCommandRegressionTests(unittest.TestCase):
    def setUp(self):
        self.request = DummyRequest()
        self.session = blingmud.Session(self.request, ("127.0.0.1", 0), blingmud.WORLD)
        self.session.player = blingmud.Player("Tester")
        self.session.player.session = self.session
        self.session.player.is_admin = True

    def tearDown(self):
        blingmud.COMMANDS.pop("regression_test", None)

    def test_admin_command_dispatch_uses_session_instance(self):
        calls = []

        class RegressionCommand(blingmud.Command):
            name = "regression_test"
            admin_only = True

            def execute(self, session, arguments):
                calls.append((session, arguments))

        blingmud.COMMANDS["regression_test"] = RegressionCommand()

        self.session.handle_command("/regression_test hello")

        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], self.session)
        self.assertEqual(calls[0][1], "hello")


class ItemRegressionTests(unittest.TestCase):
    def test_worn_where_is_preserved(self):
        item = Item("ring", wearable=True, worn_where="Finger")

        self.assertTrue(item.wearable)
        self.assertEqual(item.worn_where, "Finger")


class PasswordRegressionTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifiable(self):
        first = blingmud.password_hash("correct horse battery staple")
        second = blingmud.password_hash("correct horse battery staple")

        self.assertNotEqual(first, second)
        self.assertTrue(
            first.startswith(blingmud.PASSWORD_HASH_SCHEME + "$")
        )
        self.assertTrue(
            blingmud.verify_password("correct horse battery staple", first)
        )
        self.assertFalse(blingmud.verify_password("wrong password", first))

    def test_legacy_sha256_hash_can_be_verified_for_migration(self):
        legacy = hashlib.sha256(b"old password").hexdigest()

        self.assertTrue(blingmud.verify_password("old password", legacy))
        self.assertTrue(blingmud.password_hash_needs_upgrade(legacy))

    def test_malformed_password_hash_is_rejected(self):
        self.assertFalse(
            blingmud.verify_password("password", "pbkdf2_sha256$bad$data")
        )
        self.assertFalse(blingmud.verify_password(None, "stored hash"))

    def test_admin_hash_file_is_owner_only(self):
        descriptor, path = tempfile.mkstemp()
        os.close(descriptor)

        try:
            blingmud.write_admin_password_hash("stored hash", path)
            mode = stat.S_IMODE(os.stat(path).st_mode)

            self.assertEqual(mode, 0o600)
            with open(path, "r") as handle:
                self.assertEqual(handle.read(), "stored hash")
        finally:
            os.unlink(path)

    def test_successful_login_upgrades_legacy_user_hash(self):
        descriptor, path = tempfile.mkstemp()
        os.close(descriptor)
        original_database = blingmud.USERS_DB
        key = "legacyuser"

        try:
            blingmud.USERS_DB = path
            blingmud.init_user_database()
            blingmud.create_user("LegacyUser", "old password")
            legacy = hashlib.sha256(b"old password").hexdigest()
            blingmud.update_user_password_hash("LegacyUser", legacy)

            session = blingmud.Session(
                DummyRequest(),
                ("127.0.0.1", 0),
                blingmud.WORLD
            )
            answers = iter(("LegacyUser", "old password"))
            session.prompt = lambda prompt: None
            session.read_line = lambda hidden=False: next(answers)

            self.assertTrue(session.login())

            upgraded = blingmud.load_user("LegacyUser")["password"]
            self.assertTrue(
                upgraded.startswith(blingmud.PASSWORD_HASH_SCHEME + "$")
            )
            self.assertTrue(blingmud.verify_password("old password", upgraded))
        finally:
            with blingmud.SESSIONS_LOCK:
                blingmud.SESSIONS.pop(key, None)
            blingmud.USERS_DB = original_database
            os.unlink(path)


class NPCManagerRegressionTests(unittest.TestCase):
    def test_removing_npc_unregisters_it_from_manager(self):
        manager = NPCManager.instance()
        room = Room("test_room", "Test Room", "A test room.")
        npc = NPC("Test NPC")

        room.add_npc(npc)
        self.assertIn(npc, manager.npcs)

        room.remove_npc(npc)

        self.assertNotIn(npc, room.npcs)
        self.assertNotIn(npc, manager.npcs)
        self.assertIsNone(npc.room)


class RecordingBehavior(NPCBehavior):
    mode = NPCBehavior.MODE_FSM

    def __init__(self):
        NPCBehavior.__init__(self)
        self.events = []

    def on_player_enter(self, player):
        self.events.append(("enter", player))

    def on_player_leave(self, player):
        self.events.append(("leave", player))

    def on_say(self, player, text):
        self.events.append(("say", player, text))

    def on_emote(self, player, action):
        self.events.append(("emote", player, action))

    def tick(self):
        self.events.append(("tick",))


class FailingBehavior(NPCBehavior):
    def on_say(self, player, text):
        raise RuntimeError("broken speech handler")

    def tick(self):
        raise RuntimeError("broken tick handler")


class MultipleActionBehavior(NPCBehavior):
    def on_say(self, player, text):
        return (
            NPCAction.emote("considers the question."),
            NPCAction.say("I have an answer.")
        )


class FixedRandom(object):
    def uniform(self, minimum, maximum):
        return minimum

    def choice(self, choices):
        return choices[0]

    def random(self):
        return 0.0


class FakeClock(object):
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class NPCBehaviorTests(unittest.TestCase):
    def test_npc_delegates_every_event_to_its_behavior(self):
        behavior = RecordingBehavior()
        npc = NPC("Listener", behavior=behavior)
        player = Player("Traveller")

        npc.on_player_enter(player)
        npc.on_player_leave(player)
        npc.on_say(player, "Hello")
        npc.on_emote(player, "waves")
        npc.tick()

        self.assertIs(behavior.npc, npc)
        self.assertEqual(npc.behavior_mode, NPCBehavior.MODE_FSM)
        self.assertEqual(
            behavior.events,
            [
                ("enter", player),
                ("leave", player),
                ("say", player, "Hello"),
                ("emote", player, "waves"),
                ("tick",)
            ]
        )

    def test_failed_behavior_replacement_preserves_current_behavior(self):
        current_behavior = RecordingBehavior()
        occupied_behavior = RecordingBehavior()
        npc = NPC("Listener", behavior=current_behavior)
        other_npc = NPC("Other", behavior=occupied_behavior)

        with self.assertRaises(ValueError):
            npc.set_behavior(occupied_behavior)

        self.assertIs(npc.behavior, current_behavior)
        self.assertIs(current_behavior.npc, npc)
        self.assertIs(occupied_behavior.npc, other_npc)

    def test_room_routes_speech_and_emotes_to_npc_behavior(self):
        behavior = RecordingBehavior()
        npc = NPC("Listener", behavior=behavior)
        room = Room("event_test", "Event Test", "A test room.")
        request = DummyRequest()
        session = blingmud.Session(
            request,
            ("127.0.0.1", 0),
            blingmud.WORLD
        )
        player = Player("Speaker")
        player.session = session
        session.player = player

        room.add_npc(npc)

        try:
            room.enter(player, announce=False)
            session.handle_chat("Good evening")
            blingmud.COMMANDS["me"].execute(session, "waves")
            room.leave(player, announce=False)

            self.assertEqual(
                behavior.events,
                [
                    ("enter", player),
                    ("say", player, "Good evening"),
                    ("emote", player, "waves"),
                    ("leave", player)
                ]
            )
        finally:
            room.remove_npc(npc)

    def test_brave_sir_knight_uses_fsm_behavior_contract(self):
        knight = BraveSirKnight()
        player = Player("Traveller")

        knight.on_player_enter(player)

        self.assertEqual(knight.behavior_mode, NPCBehavior.MODE_FSM)
        self.assertIs(knight.behavior.npc, knight)
        self.assertEqual(knight.known_travellers["traveller"]["visits"], 1)

    def test_broken_behavior_does_not_block_other_npc_events(self):
        room = Room("failure_test", "Failure Test", "A test room.")
        failing_npc = NPC("Broken", behavior=FailingBehavior())
        recording_behavior = RecordingBehavior()
        working_npc = NPC("Working", behavior=recording_behavior)
        player = Player("Speaker")
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()

        room.add_npc(failing_npc)
        room.add_npc(working_npc)

        try:
            room.notify_player_said(player, "Hello")
        finally:
            room.remove_npc(failing_npc)
            room.remove_npc(working_npc)
            sys.stderr = original_stderr

        self.assertEqual(
            recording_behavior.events,
            [("say", player, "Hello")]
        )

    def test_broken_behavior_does_not_stop_manager_tick(self):
        manager = NPCManager()
        recording_behavior = RecordingBehavior()
        manager.register(NPC("Broken", behavior=FailingBehavior()))
        manager.register(NPC("Working", behavior=recording_behavior))
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            manager.tick()
        finally:
            sys.stderr = original_stderr

        self.assertEqual(recording_behavior.events, [("tick",)])


class NPCActionTests(unittest.TestCase):
    def test_action_validation_rejects_unsupported_or_unsafe_output(self):
        with self.assertRaises(ValueError):
            NPCAction("invent_item", "a diamond")

        with self.assertRaises(ValueError):
            NPCAction.say("")

        with self.assertRaises(ValueError):
            NPCAction.say("first line\nsecond line")

        with self.assertRaises(TypeError):
            NPCAction.say(None)

    def test_npc_executes_validated_speech_and_emote_actions(self):
        npc = NPC("Performer")
        output = []
        npc.speak = lambda text: output.append(("say", text))
        npc.emote = lambda text: output.append(("emote", text))

        npc.perform_action(NPCAction.say("Hello."))
        npc.perform_action(NPCAction.emote("waves."))

        self.assertEqual(
            output,
            [("say", "Hello."), ("emote", "waves.")]
        )

    def test_mutated_action_is_validated_again_before_execution(self):
        npc = NPC("Performer")
        action = NPCAction.say("Safe text")
        action.text = "unsafe\ntext"

        with self.assertRaises(ValueError):
            npc.perform_action(action)

    def test_behavior_can_return_multiple_ordered_actions(self):
        npc = NPC("Performer", behavior=MultipleActionBehavior())
        output = []
        npc.speak = lambda text: output.append(("say", text))
        npc.emote = lambda text: output.append(("emote", text))

        actions = npc.on_say(Player("Visitor"), "Any thoughts?")

        self.assertEqual(len(actions), 2)
        self.assertEqual(
            output,
            [
                ("emote", "considers the question."),
                ("say", "I have an answer.")
            ]
        )


class SimpleRandomBehaviorTests(unittest.TestCase):
    def _make_behavior(self, clock, **settings):
        defaults = {
            "minimum_delay": 5.0,
            "maximum_delay": 5.0,
            "random_source": FixedRandom(),
            "time_source": clock
        }
        defaults.update(settings)
        return SimpleRandomBehavior(**defaults)

    def test_ambient_action_waits_for_due_time_and_player_presence(self):
        clock = FakeClock()
        behavior = self._make_behavior(
            clock,
            speech=("Lovely weather.",),
            emotes=("checks the sky.",)
        )
        npc = NPC("Local", behavior=behavior)
        room = Room("random_test", "Random Test", "A test room.")
        output = []
        npc.speak = lambda text: output.append(("say", text))
        npc.emote = lambda text: output.append(("emote", text))
        room.add_npc(npc)

        try:
            clock.now = 5.0
            npc.tick()
            self.assertEqual(output, [])

            player = Player("Visitor")
            room.players.append(player)
            npc.tick()

            self.assertEqual(output, [("say", "Lovely weather.")])
            self.assertEqual(behavior.next_action_time, 10.0)
        finally:
            room.remove_npc(npc)

    def test_optional_event_reactions_return_structured_actions(self):
        clock = FakeClock()
        behavior = self._make_behavior(
            clock,
            entry_speech=("Welcome!",),
            departure_speech=("Safe travels!",),
            speech_replies=("Indeed.",),
            emote_reactions=("nods in agreement.",)
        )
        npc = NPC("Local", behavior=behavior)
        player = Player("Visitor")
        output = []
        npc.speak = lambda text: output.append(("say", text))
        npc.emote = lambda text: output.append(("emote", text))

        npc.on_player_enter(player)
        npc.on_say(player, "Hello")
        npc.on_emote(player, "waves")
        npc.on_player_leave(player)

        self.assertEqual(
            output,
            [
                ("say", "Welcome!"),
                ("say", "Indeed."),
                ("emote", "nods in agreement."),
                ("say", "Safe travels!")
            ]
        )

    def test_departing_player_receives_random_behavior_farewell(self):
        clock = FakeClock()
        behavior = self._make_behavior(
            clock,
            departure_speech=("Safe travels!",)
        )
        npc = NPC("Local", behavior=behavior)
        room = Room("farewell_test", "Farewell Test", "A test room.")
        request = DummyRequest()
        session = blingmud.Session(
            request,
            ("127.0.0.1", 0),
            blingmud.WORLD
        )
        player = Player("Visitor")
        player.session = session
        session.player = player
        room.add_npc(npc)

        try:
            room.enter(player, announce=False)
            request.sent = []
            room.leave(player, announce=False)

            transcript = b"".join(request.sent).decode("utf-8")
            self.assertIn("Safe travels!", transcript)
        finally:
            room.remove_npc(npc)

    def test_empty_pools_and_invalid_configuration_are_safe(self):
        clock = FakeClock()
        behavior = self._make_behavior(clock)
        npc = NPC("Quiet", behavior=behavior)
        room = Room("quiet_test", "Quiet Test", "A test room.")
        room.players.append(Player("Visitor"))
        room.add_npc(npc)

        try:
            clock.now = 5.0
            self.assertEqual(npc.tick(), ())
            self.assertEqual(behavior.next_action_time, 10.0)
        finally:
            room.remove_npc(npc)

        with self.assertRaises(ValueError):
            SimpleRandomBehavior(minimum_delay=10.0, maximum_delay=5.0)

        with self.assertRaises(ValueError):
            SimpleRandomBehavior(speech_weight=-1.0)

    def test_single_string_is_treated_as_one_pool_entry(self):
        clock = FakeClock()
        behavior = self._make_behavior(clock, speech="A complete sentence.")

        self.assertEqual(behavior.speech, ("A complete sentence.",))


if __name__ == "__main__":
    unittest.main()
