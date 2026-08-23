import unittest
import threading

from core import FSMBehavior, NPCBehavior, NPCManager, Player, Room
import npcs.brave_sir_knight as knight_module
from npcs.brave_sir_knight import BraveSirKnight


class ControlledRandom(object):
    def __init__(self):
        self.random_values = []
        self.choice_values = []
        self.uniform_values = []
        self.randint_values = []

    def random(self):
        if self.random_values:
            return self.random_values.pop(0)
        return 0.99

    def choice(self, choices):
        if self.choice_values:
            selected = self.choice_values.pop(0)

            if isinstance(selected, int):
                return choices[selected]

            return selected

        return choices[0]

    def uniform(self, minimum, maximum):
        if self.uniform_values:
            return self.uniform_values.pop(0)
        return minimum

    def randint(self, minimum, maximum):
        if self.randint_values:
            return self.randint_values.pop(0)
        return minimum


class BraveSirKnightCharacterizationTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.random = ControlledRandom()
        self.original_time = knight_module.time.time
        self.original_random = knight_module.random.random
        self.original_choice = knight_module.random.choice
        self.original_uniform = knight_module.random.uniform
        self.original_randint = knight_module.random.randint
        knight_module.time.time = lambda: self.now
        knight_module.random.random = self.random.random
        knight_module.random.choice = self.random.choice
        knight_module.random.uniform = self.random.uniform
        knight_module.random.randint = self.random.randint

        self.knight = BraveSirKnight()
        self.room = Room("knight_characterization", "Crossroads", "A crossroads.")
        self.player = Player("Observer")
        self.room.players.append(self.player)
        self.room.add_npc(self.knight)
        self.output = []
        self.knight.speak = lambda text: self.output.append(("say", text))
        self.knight.emote = lambda text: self.output.append(("emote", text))
        self.knight._last_fire_update = self.now

    def tearDown(self):
        self.room.remove_npc(self.knight)
        knight_module.time.time = self.original_time
        knight_module.random.random = self.original_random
        knight_module.random.choice = self.original_choice
        knight_module.random.uniform = self.original_uniform
        knight_module.random.randint = self.original_randint

    def tick_now(self):
        self.knight.next_action_time = self.now
        return self.knight.tick()

    def set_state(self, state):
        self.knight.state = state
        self.knight._last_fire_update = self.now

    def test_initial_identity_resources_and_behavior_mode(self):
        self.assertEqual(self.knight.name, "Brave Sir Knight")
        self.assertEqual(self.knight.behavior_mode, NPCBehavior.MODE_FSM)
        self.assertIsInstance(self.knight.behavior, FSMBehavior)
        self.assertEqual(
            set(self.knight.behavior.states),
            {
                self.knight.STATE_PATROL,
                self.knight.STATE_GREET,
                self.knight.STATE_GET_WATER,
                self.knight.STATE_TEND_FIRE,
                self.knight.STATE_GATHER_WOOD
            }
        )
        self.assertNotIn("known_travellers", self.knight.__dict__)
        self.assertIs(
            self.knight.known_travellers,
            self.knight.behavior.known_travellers
        )
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)
        self.assertEqual(self.knight._patrol_step, "arrive")
        self.assertEqual(self.knight._patrol_direction_index, 0)
        self.assertEqual(self.knight._last_patrol_direction, "north")
        self.assertEqual(self.knight.fire_strength, 75.0)
        self.assertEqual(self.knight.firewood, 7)
        self.assertFalse(self.knight.waterskin_full)
        self.assertTrue(self.knight.has_axe)
        self.assertEqual(self.knight.known_travellers, {})

    def test_tick_gates_fire_decay_empty_rooms_and_unknown_state_recovery(self):
        self.now += 10.0
        self.knight.next_action_time = self.now + 1.0
        self.knight.tick()
        self.assertAlmostEqual(self.knight.fire_strength, 74.75)
        self.assertEqual(self.output, [])

        self.room.players.remove(self.player)
        self.tick_now()
        self.assertEqual(self.knight.next_action_time, self.now + 2.0)
        self.assertEqual(self.output, [])

        self.room.players.append(self.player)
        self.knight.state = "invalid"
        self.tick_now()
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)
        self.assertEqual(self.knight._patrol_step, "arrive")
        self.assertEqual(self.knight.next_action_time, self.now + 1.0)

        self.room.remove_npc(self.knight)
        fire_strength = self.knight.fire_strength
        self.knight.tick()
        self.assertEqual(self.knight.fire_strength, fire_strength)
        self.room.add_npc(self.knight)

    def test_fire_decay_clamps_at_zero(self):
        self.knight.fire_strength = 0.1
        self.knight._last_fire_update = self.now
        self.now += 100.0

        self.knight._update_fire()

        self.assertEqual(self.knight.fire_strength, 0)
        self.assertEqual(self.knight._last_fire_update, self.now)

        self.knight.fire_strength = 50.0
        self.now -= 200.0
        self.knight._update_fire()
        self.assertEqual(self.knight.fire_strength, 50.0)
        self.assertEqual(self.knight._last_fire_update, self.now)

    def test_chore_start_and_patrol_resume_reset_expected_steps(self):
        cases = (
            (self.knight.STATE_GET_WATER, "_water_step"),
            (self.knight.STATE_TEND_FIRE, "_fire_step"),
            (self.knight.STATE_GATHER_WOOD, "_wood_step")
        )

        for state, step_name in cases:
            with self.subTest(state=state):
                setattr(self.knight, step_name, 99)
                self.knight._wood_gathered = 9
                self.knight._begin_chore(state)
                self.assertEqual(self.knight.state, state)
                self.assertEqual(getattr(self.knight, step_name), 0)

                if state == self.knight.STATE_GATHER_WOOD:
                    self.assertEqual(self.knight._wood_gathered, 0)

        self.knight._resume_patrol()
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)
        self.assertEqual(self.knight.next_action_time, self.now + 1.5)

    def test_patrol_arrive_sing_march_and_invalid_step_cycle(self):
        self.set_state(self.knight.STATE_PATROL)
        self.knight._patrol_step = "arrive"
        self.tick_now()
        self.assertEqual(
            self.output[-1],
            ("emote", "takes up his watch beside the north road.")
        )
        self.assertEqual(self.knight._last_patrol_direction, "north")
        self.assertEqual(self.knight._patrol_step, "observe")

        self.knight._patrol_step = "sing"
        self.tick_now()
        self.assertEqual(self.output[-1], ("say", self.knight.marching_songs[0]))
        self.assertEqual(self.knight._patrol_step, "march")

        self.knight._patrol_direction_index = 3
        self.knight._patrol_step = "march"
        self.tick_now()
        self.assertIn("west road", self.output[-1][1])
        self.assertIn("north road", self.output[-1][1])
        self.assertEqual(self.knight._patrol_direction_index, 0)
        self.assertEqual(self.knight._patrol_step, "arrive")

        self.knight._patrol_step = "invalid"
        self.tick_now()
        self.assertEqual(self.knight._patrol_step, "arrive")
        self.assertEqual(self.knight.next_action_time, self.now + 1.0)

    def _prepare_observation(self, fire_strength=75.0, firewood=7):
        self.set_state(self.knight.STATE_PATROL)
        self.knight._patrol_step = "observe"
        self.knight.fire_strength = fire_strength
        self.knight.firewood = firewood
        self.output = []

    def test_patrol_observation_prioritizes_resource_chores(self):
        self._prepare_observation(firewood=1)
        self.random.random_values = [0.69]
        self.tick_now()
        self.assertEqual(self.knight.state, self.knight.STATE_GATHER_WOOD)

        self._prepare_observation(fire_strength=25, firewood=1)
        self.random.random_values = [0.90]
        self.tick_now()
        self.assertEqual(self.knight.state, self.knight.STATE_TEND_FIRE)

        self._prepare_observation(fire_strength=25, firewood=0)
        self.random.random_values = [0.90]
        self.tick_now()
        self.assertEqual(self.knight.state, self.knight.STATE_GATHER_WOOD)

        self._prepare_observation(fire_strength=50, firewood=7)
        self.random.random_values = [0.34]
        self.tick_now()
        self.assertEqual(self.knight.state, self.knight.STATE_TEND_FIRE)

        self._prepare_observation(fire_strength=75, firewood=3)
        self.random.random_values = [0.17]
        self.tick_now()
        self.assertEqual(self.knight.state, self.knight.STATE_GATHER_WOOD)

        self._prepare_observation()
        self.random.random_values = [0.04]
        self.tick_now()
        self.assertEqual(self.knight.state, self.knight.STATE_GET_WATER)

    def test_patrol_observation_random_output_branches(self):
        cases = (
            (0.10, "emote", lambda: self.knight.armour_emotes[0], "march"),
            (0.20, "emote", lambda: "hums a few bars of an old marching song.", "sing"),
            (0.30, "say", lambda: self.knight.north_observations[0], "march"),
            (0.50, "say", lambda: self.knight.life_advice[0], "march"),
            (0.80, "emote", lambda: self.knight.general_observations[0], "march")
        )

        for roll, output_type, expected_text, expected_step in cases:
            with self.subTest(roll=roll):
                self._prepare_observation()
                self.random.random_values = [0.50, roll]
                self.tick_now()
                self.assertEqual(self.output[-1], (output_type, expected_text()))
                self.assertEqual(self.knight._patrol_step, expected_step)

    def test_each_direction_uses_its_own_observation_pool(self):
        pools = (
            ("east", self.knight.east_observations),
            ("west", self.knight.west_observations),
            ("north", self.knight.north_observations),
            ("south", self.knight.south_observations)
        )

        for direction, pool in pools:
            with self.subTest(direction=direction):
                self.output = []
                self.knight._make_direction_observation(direction)
                self.assertEqual(self.output, [("say", pool[0])])

        self.output = []
        self.knight._make_direction_observation("somewhere")
        self.assertEqual(
            self.output,
            [("emote", self.knight.general_observations[0])]
        )

    def test_random_speech_and_emotes_do_not_repeat_immediately(self):
        self.knight._last_speech = self.knight.life_advice[0]
        self.random.choice_values = [0, 0]
        self.knight._say_random(self.knight.life_advice)
        self.assertEqual(self.output[-1], ("say", self.knight.life_advice[1]))
        self.assertEqual(self.knight._last_speech, self.knight.life_advice[1])

        self.knight._last_emote = self.knight.general_observations[0]
        self.random.choice_values = [0, 0]
        self.knight._emote_random(self.knight.general_observations)
        self.assertEqual(
            self.output[-1],
            ("emote", self.knight.general_observations[1])
        )
        self.assertEqual(
            self.knight._last_emote,
            self.knight.general_observations[1]
        )

    def test_non_repeating_choice_is_bounded_for_degenerate_randomness(self):
        previous = self.knight.life_advice[0]
        self.random.choice_values = [0, 0]

        selected = self.knight._choose_not_last(
            self.knight.life_advice,
            previous
        )

        self.assertEqual(selected, self.knight.life_advice[1])
        self.assertEqual(self.random.choice_values, [])
        self.assertEqual(
            self.knight._choose_not_last((previous,), previous),
            previous
        )

    def _queue_greeting(self, name, returning=False, is_gwen=False, advice=False):
        self.knight._greeting_queue.append({
            "name": name,
            "returning": returning,
            "visits": 2 if returning else 1,
            "is_gwen": is_gwen,
            "give_advice": advice
        })
        self.knight.state = self.knight.STATE_GREET
        self.knight._greeting_resume_state = self.knight.STATE_PATROL

    def test_first_and_returning_greeting_sequences_and_resume(self):
        self._queue_greeting("Alice")
        self.tick_now()
        self.tick_now()
        self.assertEqual(
            self.output,
            [
                ("emote", "turns from his watch to greet Alice."),
                ("say", self.knight.first_greetings[0].format("Alice"))
            ]
        )
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

        self.output = []
        self._queue_greeting("Alice", returning=True, advice=True)
        self.tick_now()
        self.tick_now()
        self.tick_now()
        self.assertEqual(
            self.output,
            [
                ("emote", "recognises Alice and smiles warmly."),
                ("say", self.knight.return_greetings[0].format("Alice")),
                ("say", self.knight.life_advice[0])
            ]
        )
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

    def test_lady_gwen_greeting_with_advice_preserves_all_steps(self):
        self._queue_greeting("Gwen", is_gwen=True, advice=True)

        for unused in range(4):
            self.tick_now()

        self.assertEqual(
            self.output,
            [
                ("emote", "immediately straightens and stands to attention."),
                ("emote", "bows deeply and respectfully before Lady Gwen."),
                ("say", self.knight.gwen_greetings[0]),
                (
                    "say",
                    "If I may offer one thought, my Lady: {0}".format(
                        self.knight.life_advice[0]
                    )
                )
            ]
        )
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

        self.output = []
        self._queue_greeting("Gwen", is_gwen=True, advice=False)
        self.random.choice_values = [1]

        for unused in range(3):
            self.tick_now()

        self.assertEqual(len(self.output), 3)
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

        self.output = []
        self._queue_greeting("Alice")
        self.knight._current_greeting = self.knight._greeting_queue.pop(0)
        self.knight._greeting_step = 99
        self.tick_now()
        self.assertEqual(self.output, [])
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

    def test_greeting_queue_and_empty_greeting_state_resume_correctly(self):
        self._queue_greeting("Alice")
        self._queue_greeting("Bob")
        self.tick_now()
        self.tick_now()
        self.assertEqual(self.knight.state, self.knight.STATE_GREET)
        self.assertEqual(len(self.knight._greeting_queue), 1)
        self.assertIsNone(self.knight._current_greeting)

        self.tick_now()
        self.assertEqual(
            self.output[-1],
            ("emote", "turns from his watch to greet Bob.")
        )

        self.knight._greeting_queue = []
        self.knight._current_greeting = None
        self.tick_now()
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

    def test_water_fetching_complete_drinking_and_non_drinking_paths(self):
        self.set_state(self.knight.STATE_GET_WATER)
        self.random.random_values = [0.50]

        for unused in range(10):
            self.tick_now()

        self.assertEqual(
            self.output,
            [
                (
                    "emote",
                    "leaves his patrol route and turns towards the old stone well."
                ),
                (
                    "emote",
                    "walks across the centre of the crossroads towards the well."
                ),
                (
                    "emote",
                    "reaches the well and sets his leather waterskin upon its edge."
                ),
                (
                    "emote",
                    "lowers the bucket carefully into the clear water below."
                ),
                (
                    "emote",
                    "hauls the bucket back up and fills his waterskin."
                ),
                ("say", self.knight.thirsty_speech[0]),
                (
                    "emote",
                    "raises the waterskin and takes a long, grateful drink."
                ),
                (
                    "emote",
                    "fastens the waterskin securely and turns back towards "
                    "the north road."
                ),
                (
                    "emote",
                    "walks back from the well towards his place upon the "
                    "north road."
                ),
                (
                    "emote",
                    "resumes his watch as though he had never left it."
                )
            ]
        )
        self.assertFalse(self.knight.waterskin_full)
        self.assertEqual(self.knight._water_step, 0)
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

        self.output = []
        self.set_state(self.knight.STATE_GET_WATER)
        self.knight._water_step = 4
        self.random.random_values = [0.90]

        for unused in range(4):
            self.tick_now()

        self.assertEqual(len(self.output), 4)
        self.assertNotIn(("say", self.knight.thirsty_speech[0]), self.output)
        self.assertTrue(self.knight.waterskin_full)
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

        self.set_state(self.knight.STATE_GET_WATER)
        self.knight._water_step = 99
        self.tick_now()
        self.assertEqual(self.knight._water_step, 0)
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

    def test_fire_tending_complete_no_wood_and_clamping_paths(self):
        self.set_state(self.knight.STATE_TEND_FIRE)
        self.knight.fire_strength = 20.0
        self.knight.firewood = 2

        for unused in range(8):
            self.tick_now()

        self.assertEqual(self.knight.firewood, 1)
        self.assertEqual(self.knight.fire_strength, 50.0)
        self.assertEqual(
            self.output,
            [
                (
                    "emote",
                    "glances towards the campfire and frowns at the weakening flames."
                ),
                (
                    "emote",
                    "walks from his patrol route towards the campfire."
                ),
                (
                    "emote",
                    "kneels beside the fire and studies the glowing embers."
                ),
                (
                    "emote",
                    "takes a dry log from the woodpile and lays it carefully "
                    "across the embers."
                ),
                (
                    "emote",
                    "uses a sturdy branch to stir the embers until sparks "
                    "rise into the air."
                ),
                ("say", self.knight.fire_speech[0]),
                (
                    "emote",
                    "rises from beside the renewed fire and returns towards "
                    "the north road."
                ),
                (
                    "emote",
                    "resumes his patient patrol of the crossroads."
                )
            ]
        )
        self.assertEqual(self.knight._fire_step, 0)
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

        self.output = []
        self.set_state(self.knight.STATE_TEND_FIRE)
        self.knight._fire_step = 2
        self.knight.firewood = 0
        self.tick_now()
        self.tick_now()
        self.assertEqual(self.knight.state, self.knight.STATE_GATHER_WOOD)
        self.assertIn("firewood is spent", self.output[-1][1].lower())

        self.set_state(self.knight.STATE_TEND_FIRE)
        self.knight._fire_step = 4
        self.knight.fire_strength = 90.0
        self.tick_now()
        self.assertEqual(self.knight.fire_strength, 100)

        self.set_state(self.knight.STATE_TEND_FIRE)
        self.knight._fire_step = 99
        self.tick_now()
        self.assertEqual(self.knight._fire_step, 0)
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

    def test_wood_gathering_complete_missing_axe_and_weak_fire_paths(self):
        self.set_state(self.knight.STATE_GATHER_WOOD)
        self.knight.firewood = 2
        self.knight.fire_strength = 75
        self.random.randint_values = [6]

        for unused in range(12):
            self.tick_now()

        self.assertEqual(self.knight.firewood, 8)
        self.assertEqual(self.knight._wood_gathered, 0)
        self.assertEqual(
            self.output,
            [
                ("emote", "looks over the dwindling pile of firewood."),
                ("emote", "takes up his small woodcutting axe."),
                (
                    "emote",
                    "walks towards the hedgerow in search of fallen wood."
                ),
                (
                    "emote",
                    "finds a fallen branch and tests the timber with one boot."
                ),
                (
                    "emote",
                    "swings his axe into the fallen branch with a solid crack."
                ),
                (
                    "emote",
                    "chops the branch into lengths suitable for the fire."
                ),
                ("say", self.knight.wood_speech[0]),
                (
                    "emote",
                    "binds the cut wood into a bundle and lifts it onto one shoulder."
                ),
                (
                    "emote",
                    "returns from the hedgerow carrying the bundle of logs."
                ),
                (
                    "emote",
                    "adds the newly cut wood to the neat pile beside the fire."
                ),
                (
                    "emote",
                    "wipes the axe blade clean and returns it to its place."
                ),
                (
                    "emote",
                    "returns to his interrupted watch upon the north road."
                )
            ]
        )
        self.assertEqual(self.knight._wood_step, 0)
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

        self.output = []
        self.set_state(self.knight.STATE_GATHER_WOOD)
        self.knight._wood_step = 1
        self.knight.has_axe = False
        self.tick_now()
        self.assertTrue(self.knight.has_axe)
        self.assertIn("finds his woodcutting axe", self.output[-1][1])

        self.set_state(self.knight.STATE_GATHER_WOOD)
        self.knight._wood_step = 11
        self.knight.fire_strength = 35
        self.tick_now()
        self.assertEqual(self.knight._wood_step, 0)
        self.assertEqual(self.knight.state, self.knight.STATE_TEND_FIRE)

        self.set_state(self.knight.STATE_GATHER_WOOD)
        self.knight._wood_step = 99
        self.tick_now()
        self.assertEqual(self.knight._wood_step, 0)
        self.assertEqual(self.knight.state, self.knight.STATE_PATROL)

    def test_arrival_memory_returning_status_queue_and_special_name_detection(self):
        self.random.random_values = [0.50]
        traveller = Player("Alice")
        self.knight.on_player_enter(traveller)
        memory = self.knight.known_travellers["alice"]
        self.assertEqual(memory["visits"], 1)
        self.assertTrue(memory["present"])
        self.assertEqual(memory["last_entered"], self.now)
        self.assertFalse(self.knight._greeting_queue[0]["returning"])
        self.assertEqual(self.knight.state, self.knight.STATE_GREET)

        self.now += 20
        self.random.random_values = [0.10]
        returning = Player("ALICE")
        self.knight.on_player_enter(returning)
        memory = self.knight.known_travellers["alice"]
        self.assertEqual(memory["name"], "ALICE")
        self.assertEqual(memory["visits"], 2)
        self.assertEqual(memory["last_entered"], self.now)
        self.assertTrue(self.knight._greeting_queue[-1]["returning"])
        self.assertTrue(self.knight._greeting_queue[-1]["give_advice"])

        for name in (
            "Gwen",
            "gwen nelson",
            "Gwen Willow Eve Nelson",
            "Lady Gwen"
        ):
            self.assertTrue(self.knight._is_lady_gwen(name))

        self.assertFalse(self.knight._is_lady_gwen("Gwendolyn"))

    def test_departure_memory_and_farewell_branches(self):
        traveller = Player("Alice")
        self.random.random_values = [0.50]
        self.knight.on_player_enter(traveller)
        self.output = []
        self.now += 10
        self.random.random_values = [0.59]
        self.knight.on_player_leave(traveller)
        memory = self.knight.known_travellers["alice"]
        self.assertFalse(memory["present"])
        self.assertEqual(memory["last_left"], self.now)
        self.assertEqual(
            self.output,
            [("say", self.knight.departure_greetings[0].format("Alice"))]
        )

        self.output = []
        self.random.random_values = [0.60]
        self.knight.on_player_leave(Player("Silent"))
        self.assertEqual(self.output, [])
        self.assertEqual(self.knight.known_travellers["silent"]["visits"], 1)

        self.output = []
        self.knight.on_player_leave(Player("Lady Gwen"))
        self.assertEqual(
            self.output,
            [
                ("emote", "bows respectfully as Lady Gwen departs."),
                (
                    "say",
                    "Lady Gwen departs. May the roads be gentle beneath "
                    "thy feet, my Lady."
                )
            ]
        )

    def test_traveller_memory_has_a_finite_deterministic_bound(self):
        for index in range(self.knight.MAX_TRAVELLERS + 4):
            self.now += 1
            self.knight.on_player_leave(Player("traveller{0}".format(index)))
        self.assertEqual(
            len(self.knight.known_travellers),
            self.knight.MAX_TRAVELLERS
        )
        self.assertNotIn("traveller0", self.knight.known_travellers)
        snapshot = self.knight.behavior.memory_snapshot()
        self.assertEqual(len(snapshot), self.knight.MAX_TRAVELLERS)

    def test_speech_and_emote_observation_remain_no_ops(self):
        before = dict(self.knight.known_travellers)

        actions = self.knight.on_say(self.player, "Hello")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_type, "say")
        self.assertEqual(self.knight.on_emote(self.player, "waves"), ())
        self.assertEqual(len(self.output), 1)
        self.assertEqual(self.output[0][0], "say")
        self.assertEqual(self.knight.known_travellers, before)

    def test_concurrent_decisions_keep_their_action_buffers_separate(self):
        behavior = self.knight.behavior
        barrier = threading.Barrier(2, timeout=1.0)
        results = {}
        errors = []

        def decide(label):
            try:
                behavior._begin_decision()
                behavior.speak(label)
                barrier.wait()
                results[label] = behavior._finish_decision()
            except BaseException as error:
                errors.append(error)

        first = threading.Thread(target=decide, args=("first",))
        second = threading.Thread(target=decide, args=("second",))
        first.start()
        second.start()
        first.join(2.0)
        second.join(2.0)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results["first"][0].text, "first")
        self.assertEqual(results["second"][0].text, "second")
        self.assertEqual(len(results["first"]), 1)
        self.assertEqual(len(results["second"]), 1)


if __name__ == "__main__":
    unittest.main()
