import unittest
import hashlib
import io
import os
import stat
import sys
import tempfile
from unittest import mock

import blingmud
import run_tests
from core import (
    Item,
    FSMBehavior,
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


class InputRequest(DummyRequest):
    def __init__(self, incoming):
        DummyRequest.__init__(self)
        self.incoming = bytearray(incoming)

    def recv(self, size):
        if not self.incoming:
            return b""

        data = bytes(self.incoming[:size])
        del self.incoming[:size]
        return data


class TestRunnerRegressionTests(unittest.TestCase):
    def test_runner_refuses_symlinked_temp_directory(self):
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            with mock.patch.object(
                run_tests.os.path,
                "islink",
                return_value=True
            ), mock.patch.object(run_tests.os, "makedirs") as makedirs:
                result = run_tests.main()

            message = sys.stderr.getvalue()
        finally:
            sys.stderr = original_stderr

        self.assertEqual(result, 2)
        self.assertIn("symlinked", message)
        makedirs.assert_not_called()

    def test_runner_returns_child_status_and_uses_finite_timeout(self):
        completed = mock.Mock(returncode=7)

        with mock.patch.object(
            run_tests.subprocess,
            "run",
            return_value=completed
        ) as run:
            result = run_tests.main()

        self.assertEqual(result, 7)
        run.assert_called_once()
        arguments, settings = run.call_args
        self.assertEqual(arguments, (run_tests.TEST_COMMAND,))
        self.assertEqual(settings["cwd"], run_tests.REPOSITORY_ROOT)
        self.assertEqual(
            settings["timeout"],
            run_tests.TEST_TIMEOUT_SECONDS
        )
        self.assertEqual(
            settings["env"]["TMPDIR"],
            run_tests.TEST_TEMP_ROOT
        )

        for unsafe_setting in (
            "PYTHONHOME",
            "PYTHONINSPECT",
            "PYTHONPATH",
            "PYTHONSTARTUP"
        ):
            self.assertNotIn(unsafe_setting, settings["env"])

    def test_runner_reports_and_returns_timeout_status(self):
        timeout = run_tests.subprocess.TimeoutExpired(
            run_tests.TEST_COMMAND,
            run_tests.TEST_TIMEOUT_SECONDS
        )
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            with mock.patch.object(
                run_tests.subprocess,
                "run",
                side_effect=timeout
            ):
                result = run_tests.main()

            message = sys.stderr.getvalue()
        finally:
            sys.stderr = original_stderr

        self.assertEqual(result, 124)
        self.assertIn("was terminated", message)


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
    def test_login_warns_about_plaintext_telnet_before_reading_name(self):
        request = DummyRequest()
        session = blingmud.Session(
            request,
            ("127.0.0.1", 0),
            blingmud.WORLD
        )

        self.assertFalse(session.login())

        output = b"".join(request.sent).decode("utf-8", "replace")
        self.assertIn("PLAINTEXT TELNET WARNING", output)

        for warning_line in blingmud.PLAINTEXT_TELNET_WARNING:
            self.assertIn(warning_line, output)

        self.assertLess(output.index("PLAINTEXT TELNET WARNING"), output.index("Name: "))

    def test_hidden_input_is_never_echoed_or_redrawn(self):
        request = InputRequest(b"secret password\r\x00")
        session = blingmud.Session(
            request,
            ("127.0.0.1", 0),
            blingmud.WORLD
        )

        session.prompt("Password: ")
        password = session.read_line(hidden=True)

        self.assertEqual(password, "secret password")
        self.assertNotIn(b"secret password", b"".join(request.sent))

        session.prompt_text = "Password: "
        session.current_input = "another secret"
        session.input_active = True
        session.input_hidden = True
        session.send("An asynchronous notice.")

        self.assertNotIn(b"another secret", b"".join(request.sent))

    def test_direct_session_input_decodes_unicode_before_backspace(self):
        request = InputRequest(
            "café".encode("utf-8") + b"\x08e\r\x00"
        )
        session = blingmud.Session(
            request,
            ("127.0.0.1", 0),
            blingmud.WORLD
        )

        self.assertEqual(session.read_line(), "cafe")
        self.assertNotIn(b"\xef\xbf\xbd", b"".join(request.sent))

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

    def test_excessive_password_hash_cost_is_rejected_before_hashing(self):
        stored_hash = "{0}${1}${2}${3}".format(
            blingmud.PASSWORD_HASH_SCHEME,
            blingmud.PASSWORD_HASH_MAX_ITERATIONS + 1,
            "00" * blingmud.PASSWORD_SALT_BYTES,
            "00" * blingmud.PASSWORD_DIGEST_BYTES
        )

        with mock.patch.object(
            blingmud.hashlib,
            "pbkdf2_hmac"
        ) as derive_key:
            self.assertFalse(
                blingmud.verify_password("safe password", stored_hash)
            )

        derive_key.assert_not_called()

    def test_password_hash_rejects_unbounded_input(self):
        password = "x" * (blingmud.MAX_PASSWORD_LENGTH + 1)

        with self.assertRaises(ValueError):
            blingmud.password_hash(password)

    def test_admin_password_read_detects_overlength_input(self):
        original_hash = blingmud.ADMIN_PASSWORD_HASH
        session = mock.Mock()
        session.player = Player("WouldBeAdmin")
        session.read_line.return_value = (
            "x" * (blingmud.MAX_PASSWORD_LENGTH + 1)
        )
        blingmud.ADMIN_PASSWORD_HASH = "configured-but-not-used"

        try:
            blingmud.COMMANDS["admin"].execute(session, "")
        finally:
            blingmud.ADMIN_PASSWORD_HASH = original_hash

        session.read_line.assert_called_once_with(
            hidden=True,
            maximum_length=blingmud.MAX_PASSWORD_LENGTH + 1
        )
        self.assertFalse(session.player.is_admin)

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
            session.read_line = lambda hidden=False, maximum_length=None: next(
                answers
            )

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

    def test_manager_stop_uses_a_finite_join_and_tolerates_no_start(self):
        manager = NPCManager()
        manager.stop()

        class FakeTickerThread(object):
            def __init__(self):
                self.alive = True
                self.join_timeout = None

            def is_alive(self):
                return self.alive

            def join(self, timeout):
                self.join_timeout = timeout
                self.alive = False

        fake_thread = FakeTickerThread()
        manager._ticker_thread = fake_thread
        manager.running = True

        manager.stop(timeout=0.25)

        self.assertFalse(manager.running)
        self.assertEqual(fake_thread.join_timeout, 0.25)


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
        room.players.append(player)
        player.room = room

        try:
            room.notify_player_said(player, "Hello")
        finally:
            room.players.remove(player)
            player.room = None
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
        room = Room("manager_failure", "Manager Failure", "A test room.")
        broken_npc = NPC("Broken", behavior=FailingBehavior())
        working_npc = NPC("Working", behavior=recording_behavior)
        room.players.append(Player("Observer"))
        room.add_npc(broken_npc)
        room.add_npc(working_npc)
        manager.register(broken_npc)
        manager.register(working_npc)
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            manager.tick()
        finally:
            sys.stderr = original_stderr
            room.remove_npc(broken_npc)
            room.remove_npc(working_npc)

        self.assertEqual(recording_behavior.events, [("tick",)])


class NPCActionTests(unittest.TestCase):
    def test_action_validation_rejects_unsupported_or_unsafe_output(self):
        with self.assertRaises(ValueError):
            NPCAction("invent_item", "a diamond")

        with self.assertRaises(ValueError):
            NPCAction.say("")

        with self.assertRaises(ValueError):
            NPCAction.say("first line\nsecond line")

        with self.assertRaises(ValueError):
            NPCAction.say("terminal\u009bcontrol")

        with self.assertRaises(ValueError):
            NPCAction.say("right-to-left\u202eoverride")

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

    def test_unbound_behavior_tick_is_inert(self):
        clock = FakeClock(5.0)
        behavior = self._make_behavior(clock, speech=("Hello.",))
        npc = NPC("Local", behavior=behavior)

        behavior.unbind(npc)

        self.assertIsNone(behavior.tick())


class FSMBehaviorTests(unittest.TestCase):
    def _make_states(self):
        return {
            "idle": {
                "on_enter": NPCAction.say("Standing by."),
                "on_exit": NPCAction.emote("stands to attention."),
                "events": {
                    "player_enter": {
                        "target": "greeting",
                        "actions": NPCAction.emote("notices a visitor.")
                    }
                }
            },
            "greeting": {
                "on_enter": NPCAction.say("Welcome, traveller."),
                "timeout": {
                    "after": 5.0,
                    "target": "idle",
                    "actions": NPCAction.emote("returns to their post.")
                }
            }
        }

    def _make_npc(self, clock, states=None, initial_state="idle"):
        behavior = FSMBehavior(
            states or self._make_states(),
            initial_state,
            time_source=clock
        )
        npc = NPC("Guard", behavior=behavior)
        output = []
        npc.speak = lambda text: output.append(("say", text))
        npc.emote = lambda text: output.append(("emote", text))
        return npc, behavior, output

    def test_event_transition_orders_exit_transition_and_entry_actions(self):
        clock = FakeClock(10.0)
        npc, behavior, output = self._make_npc(clock)

        npc.on_player_enter(Player("Visitor"))

        self.assertEqual(behavior.current_state, "greeting")
        self.assertEqual(behavior.next_transition_time, 15.0)
        self.assertEqual(
            output,
            [
                ("say", "Standing by."),
                ("emote", "stands to attention."),
                ("emote", "notices a visitor."),
                ("say", "Welcome, traveller.")
            ]
        )

    def test_timeout_waits_for_active_room_then_transitions(self):
        clock = FakeClock(10.0)
        npc, behavior, output = self._make_npc(
            clock,
            initial_state="greeting"
        )
        room = Room("fsm_test", "FSM Test", "A test room.")
        room.add_npc(npc)

        try:
            clock.now = 15.0
            npc.tick()
            self.assertEqual(behavior.current_state, "greeting")
            self.assertEqual(output, [])

            room.players.append(Player("Visitor"))
            npc.tick()

            self.assertEqual(behavior.current_state, "idle")
            self.assertEqual(
                output,
                [
                    ("say", "Welcome, traveller."),
                    ("emote", "returns to their post."),
                    ("say", "Standing by.")
                ]
            )
        finally:
            room.remove_npc(npc)

    def test_conditions_select_first_matching_transition(self):
        clock = FakeClock()
        states = {
            "listening": {
                "events": {
                    "say": (
                        {
                            "condition": lambda behavior, event: (
                                "hello" in event["text"].lower()
                            ),
                            "actions": NPCAction.say("Hello to you too.")
                        },
                        {
                            "actions": NPCAction.say("I heard you.")
                        }
                    )
                }
            }
        }
        npc, behavior, output = self._make_npc(
            clock,
            states=states,
            initial_state="listening"
        )
        player = Player("Visitor")

        npc.on_say(player, "HELLO there")
        npc.on_say(player, "Something else")

        self.assertEqual(behavior.current_state, "listening")
        self.assertEqual(
            output,
            [
                ("say", "Hello to you too."),
                ("say", "I heard you.")
            ]
        )

    def test_state_snapshot_contains_serializable_timing_state(self):
        clock = FakeClock(42.0)
        npc, behavior, output = self._make_npc(clock)

        self.assertEqual(
            behavior.state_snapshot(),
            {
                "state": "idle",
                "entered_state_at": 42.0,
                "next_transition_time": None
            }
        )

    def test_trusted_handler_can_produce_actions(self):
        clock = FakeClock()
        states = {
            "idle": {
                "events": {
                    "say": {
                        "handler": lambda behavior, event: NPCAction.say(
                            "You said: {0}".format(event["text"])
                        )
                    }
                }
            }
        }
        npc, behavior, output = self._make_npc(
            clock,
            states=states,
            initial_state="idle"
        )

        npc.on_say(Player("Visitor"), "hello")

        self.assertEqual(output, [("say", "You said: hello")])

    def test_controlled_state_selection_can_queue_entry_actions(self):
        clock = FakeClock(5.0)
        npc, behavior, output = self._make_npc(clock)

        behavior.set_state("greeting", queue_entry_actions=True)
        npc.on_say(Player("Visitor"), "hello")

        self.assertEqual(behavior.current_state, "greeting")
        self.assertEqual(output, [("say", "Welcome, traveller.")])

    def test_unbound_behavior_tick_is_inert(self):
        clock = FakeClock(5.0)
        npc, behavior, output = self._make_npc(clock)

        behavior.unbind(npc)

        self.assertIsNone(behavior.tick())
        self.assertEqual(output, [])

    def test_invalid_fsm_definitions_are_rejected(self):
        with self.assertRaises(ValueError):
            FSMBehavior({}, "idle")

        with self.assertRaises(ValueError):
            FSMBehavior({"idle": {}}, "missing")

        with self.assertRaises(ValueError):
            FSMBehavior(
                {
                    "idle": {
                        "events": {
                            "say": {"target": "missing"}
                        }
                    }
                },
                "idle"
            )

        with self.assertRaises(ValueError):
            FSMBehavior(
                {
                    "idle": {
                        "events": {
                            "unsupported": {"actions": ()}
                        }
                    }
                },
                "idle"
            )

        with self.assertRaises(TypeError):
            FSMBehavior(
                {
                    "idle": {
                        "events": {
                            "say": {"condition": "text == hello"}
                        }
                    }
                },
                "idle"
            )

        with self.assertRaises(TypeError):
            FSMBehavior(
                {
                    "idle": {
                        "events": {
                            "say": {"handler": "run arbitrary code"}
                        }
                    }
                },
                "idle"
            )

        with self.assertRaises(ValueError):
            FSMBehavior(
                {
                    "idle": {
                        "timeout": {
                            "after": float("inf"),
                            "target": "idle"
                        }
                    }
                },
                "idle"
            )


class BraveSirKnightCompatibilityTests(unittest.TestCase):
    def test_patrol_arrival_output_and_state_are_preserved(self):
        knight = BraveSirKnight()
        room = Room("knight_test", "Knight Test", "A test room.")
        request = DummyRequest()
        session = blingmud.Session(
            request,
            ("127.0.0.1", 0),
            blingmud.WORLD
        )
        player = Player("Observer")
        player.session = session
        session.player = player
        room.players.append(player)
        room.add_npc(knight)
        knight.state = knight.STATE_PATROL
        knight._patrol_step = "arrive"
        knight.next_action_time = 0

        try:
            knight.tick()
            transcript = b"".join(request.sent).decode("utf-8")

            self.assertIn(
                "takes up his watch beside the north road.",
                transcript
            )
            self.assertEqual(knight.state, knight.STATE_PATROL)
            self.assertEqual(knight._patrol_step, "observe")
        finally:
            room.remove_npc(knight)

    def test_player_arrival_still_interrupts_patrol_for_greeting(self):
        knight = BraveSirKnight()
        player = Player("Traveller")
        previous_action_time = knight.next_action_time

        knight.on_player_enter(player)

        self.assertEqual(knight.state, knight.STATE_GREET)
        self.assertEqual(knight._greeting_resume_state, knight.STATE_PATROL)
        self.assertEqual(len(knight._greeting_queue), 1)
        self.assertLess(knight.next_action_time, previous_action_time)
        self.assertEqual(knight.known_travellers["traveller"]["visits"], 1)


if __name__ == "__main__":
    unittest.main()
