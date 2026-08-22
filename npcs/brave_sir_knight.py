from core import NPC, NPCBehavior
import random
import time
import threading


class BraveSirKnightBehavior(NPCBehavior):
    """Compatibility behavior for the knight's hand-authored FSM."""

    mode = NPCBehavior.MODE_FSM

    def tick(self):
        return self.npc._behavior_tick()

    def on_player_enter(self, player):
        return self.npc._behavior_on_player_enter(player)

    def on_player_leave(self, player):
        return self.npc._behavior_on_player_leave(player)


class BraveSirKnight(NPC):

    STATE_PATROL = "patrol"
    STATE_GREET = "greet"
    STATE_GET_WATER = "get_water"
    STATE_TEND_FIRE = "tend_fire"
    STATE_GATHER_WOOD = "gather_wood"

    PATROL_DIRECTIONS = (
        "north",
        "east",
        "south",
        "west"
    )

    def __init__(self):
        NPC.__init__(
            self,
            "Brave Sir Knight",
            "A weary but honourable knight keeps watch over the crossroads.",
            behavior=BraveSirKnightBehavior()
        )

        self._state_lock = threading.RLock()

        self.state = self.STATE_PATROL
        self.next_action_time = time.time() + random.uniform(2.0, 4.0)

        # Patrol state.
        self._patrol_direction_index = 0
        self._patrol_step = "arrive"
        self._last_patrol_direction = "north"

        # A greeting temporarily interrupts whatever else he was doing.
        self._greeting_resume_state = self.STATE_PATROL
        self._greeting_queue = []
        self._current_greeting = None
        self._greeting_step = 0

        # Water-fetching state.
        self._water_step = 0
        self._water_should_drink = False
        self.waterskin_full = False

        # Fire-tending state.
        #
        # These belong to the knight for now. Later they can be moved into
        # the Crossroads room or into separate fire and log-pile entities.
        self.fire_strength = 75.0
        self.firewood = 7
        self._last_fire_update = time.time()
        self._fire_step = 0

        # Wood-gathering state.
        self._wood_step = 0
        self._wood_gathered = 0
        self.has_axe = True

        # Player memory survives players leaving and reconnecting, but not a
        # server restart. It can later be made persistent if desired.
        #
        # username_lower: {
        #     "name": display name,
        #     "visits": number of arrivals,
        #     "present": whether currently in the room,
        #     "last_entered": timestamp,
        #     "last_left": timestamp
        # }
        self.known_travellers = {}

        self._last_emote = ""
        self._last_speech = ""

        self.general_observations = (
            "looks along the road for signs of approaching travellers.",
            "studies a set of wheel tracks pressed into the earth.",
            "rests one hand upon the pommel of his sword.",
            "checks that the crossroads remain peaceful.",
            "shades his eyes and studies the distant horizon.",
            "listens carefully to the birds in the hedgerow.",
            "examines the road for anything out of place.",
            "stands silently for a moment, alert and watchful."
        )

        self.armour_emotes = (
            "tightens one of the leather straps upon his breastplate.",
            "adjusts his sword belt until it sits comfortably.",
            "checks the fastening upon his shield.",
            "brushes a layer of road dust from his tabard.",
            "works a stiff shoulder beneath the weight of his armour.",
            "tests the buckle holding one of his greaves in place.",
            "removes a small stone from the sole of his boot.",
            "polishes a dull patch upon his breastplate with his sleeve."
        )

        self.marching_songs = (
            "Oh, the road is long and the daylight brief, "
            "but a stout heart carries a traveller.",

            "Four roads meet and four roads part; "
            "keep good steel and a kinder heart.",

            "Boot upon stone and shield upon back; "
            "follow the road and never look back.",

            "Through rain and wind, through dark and dawn, "
            "the watch is kept and the road goes on."
        )

        self.life_advice = (
            "Keep thy blade sharp, but thy judgement sharper.",
            "A difficult road is more easily walked one step at a time.",
            "Courage is not the absence of fear, but the decision to continue.",
            "Treat kindly those whom the road has made weary.",
            "Never mistake cruelty for strength.",
            "Rest when thou must. Even the strongest horse cannot gallop forever.",
            "Listen twice before speaking once.",
            "A traveller who asks for help is no less brave for asking.",
            "Carry water, mend thy boots, and do not ignore an ominous rattle.",
            "An honourable retreat is wiser than a glorious and pointless death."
        )

        self.first_greetings = (
            "Welcome, {0}. Rest here if thou art weary.",
            "Well met, {0}. Thou art welcome at these crossroads.",
            "Greetings, traveller. I am Brave Sir Knight, keeper of this crossing.",
            "Peace upon thy journey, {0}. The fire and well are freely shared.",
            "Welcome, {0}. What news dost thou bring from the road?"
        )

        self.return_greetings = (
            "Welcome back, {0}. The crossroads remember thee.",
            "Ah, {0}! It is good to see a familiar face upon the road.",
            "Well met once again, {0}. I trust the road has treated thee kindly.",
            "{0} returns! Thou art welcome here as ever.",
            "Welcome back, old traveller. The fire still burns for thee.",
            "The road brings {0} to us once more. I am glad of it."
        )

        self.gwen_greetings = (
            "My Lady Gwen. Thou honour'st these crossroads with thy presence.",
            "Lady Gwen, welcome. The roads have remained peaceful in thy absence.",
            "My Lady returns. It gladdens me greatly to see thee.",
            "Lady Gwen. I remain, as ever, faithfully at my post.",
            "My Lady Gwen, the crossroads are brighter for thy arrival."
        )

        self.departure_greetings = (
            "Safe travels, {0}.",
            "May the road be gentle beneath thy feet, {0}.",
            "Farewell, {0}. Return whenever thou hast need of rest.",
            "Go safely, traveller.",
            "Until the roads bring us together again, {0}."
        )

        self.east_observations = (
            "The eastern road catches the first light of dawn.",
            "Perhaps I shall see the sun rise beyond the eastern hills.",
            "Morning always arrives first upon the eastern road.",
            "The east grows pale. Dawn cannot be too distant.",
            "There is hope in watching the light return from the east."
        )

        self.west_observations = (
            "The western road is finest when the sun begins to set.",
            "Perhaps the sunset shall paint the western sky tonight.",
            "Evening gathers first upon the western road.",
            "The west often looks peaceful beneath the last light of day.",
            "A traveller heading west may yet catch a beautiful sunset."
        )

        self.north_observations = (
            "The northern road has been quiet today.",
            "A cool wind often follows the northern road.",
            "There are old kingdoms beyond the northern hills.",
            "Few merchants have travelled from the north of late.",
            "The northern road carries every distant sound clearly."
        )

        self.south_observations = (
            "The southern road usually brings the most travellers.",
            "Merchants favour the southern road when the weather is fair.",
            "The air from the south carries the scent of distant fields.",
            "Someone has passed along the southern road quite recently.",
            "The southern road looks peaceful, though appearances can deceive."
        )

        self.thirsty_speech = (
            "Standing watch is thirsty work.",
            "A little water keeps both the mind and sword arm steady.",
            "Fresh water is a blessing too easily taken for granted.",
            "I had not realised how thirsty I had become.",
            "One should drink before thirst becomes exhaustion.",
            "Even honourable knights must occasionally stop for water."
        )

        self.fire_speech = (
            "A warm fire can save a weary traveller's life.",
            "No traveller should find this crossing cold and dark.",
            "A carefully tended fire asks little and gives much.",
            "These embers should last a while longer.",
            "There. That should keep the chill away."
        )

        self.wood_speech = (
            "The firewood pile will not replenish itself.",
            "A little honest labour keeps the cold at bay.",
            "Dead wood burns well and harms no living tree.",
            "One should gather fuel before it is urgently needed.",
            "A sharp axe and a patient arm accomplish much."
        )

    # ------------------------------------------------------------------
    # General helpers
    # ------------------------------------------------------------------

    def _delay(self, minimum, maximum=None):
        if maximum is None:
            maximum = minimum

        self.next_action_time = (
            time.time() + random.uniform(minimum, maximum)
        )

    def _choose_not_last(self, choices, previous):
        choice = random.choice(choices)

        while choice == previous:
            choice = random.choice(choices)

        return choice

    def _say_random(self, choices):
        text = self._choose_not_last(
            choices,
            self._last_speech
        )

        self._last_speech = text
        self.speak(text)

    def _emote_random(self, choices):
        text = self._choose_not_last(
            choices,
            self._last_emote
        )

        self._last_emote = text
        self.emote(text)

    def _is_lady_gwen(self, name):
        return name.strip().lower() in (
            "gwen",
            "gwen nelson",
            "gwen willow eve nelson",
            "lady gwen"
        )

    def _room_has_players(self):
        if self.room is None:
            return False

        with self.room.lock:
            return bool(self.room.players)

    def _current_patrol_direction(self):
        return self.PATROL_DIRECTIONS[
            self._patrol_direction_index
        ]

    def _next_patrol_direction(self):
        next_index = (
            self._patrol_direction_index + 1
        ) % len(self.PATROL_DIRECTIONS)

        return self.PATROL_DIRECTIONS[next_index]

    def _update_fire(self):
        now = time.time()
        elapsed = now - self._last_fire_update
        self._last_fire_update = now

        # At this rate, a completely unattended strong fire lasts for
        # roughly an hour of real time.
        self.fire_strength -= elapsed * 0.025

        if self.fire_strength < 0:
            self.fire_strength = 0

    def _begin_chore(self, state):
        self.state = state

        if state == self.STATE_GET_WATER:
            self._water_step = 0

        elif state == self.STATE_TEND_FIRE:
            self._fire_step = 0

        elif state == self.STATE_GATHER_WOOD:
            self._wood_step = 0
            self._wood_gathered = 0

        self._delay(1.0, 2.0)

    def _resume_patrol(self):
        self.state = self.STATE_PATROL
        self._delay(1.5, 3.0)

    # ------------------------------------------------------------------
    # Main dispatcher
    # ------------------------------------------------------------------

    def _behavior_tick(self):
        if not self.room:
            return

        self._update_fire()

        if time.time() < self.next_action_time:
            return

        if not self._room_has_players():
            self._delay(2.0, 4.0)
            return

        with self._state_lock:
            if self.state == self.STATE_PATROL:
                self._tick_patrol()

            elif self.state == self.STATE_GREET:
                self._tick_greet()

            elif self.state == self.STATE_GET_WATER:
                self._tick_get_water()

            elif self.state == self.STATE_TEND_FIRE:
                self._tick_tend_fire()

            elif self.state == self.STATE_GATHER_WOOD:
                self._tick_gather_wood()

            else:
                self.state = self.STATE_PATROL
                self._patrol_step = "arrive"
                self._delay(1.0, 2.0)

    # ------------------------------------------------------------------
    # Patrol state
    # ------------------------------------------------------------------

    def _tick_patrol(self):
        direction = self._current_patrol_direction()

        if self._patrol_step == "arrive":
            self._last_patrol_direction = direction

            self.emote(
                "takes up his watch beside the {0} road.".format(
                    direction
                )
            )

            self._patrol_step = "observe"
            self._delay(3.0, 6.0)
            return

        if self._patrol_step == "observe":
            # Necessary work takes priority over random diversions.
            if self.firewood <= 1:
                if random.random() < 0.70:
                    self._begin_chore(self.STATE_GATHER_WOOD)
                    return

            if self.fire_strength <= 30:
                if self.firewood > 0:
                    self._begin_chore(self.STATE_TEND_FIRE)
                else:
                    self._begin_chore(self.STATE_GATHER_WOOD)
                return

            if self.fire_strength <= 55:
                if self.firewood > 0 and random.random() < 0.35:
                    self._begin_chore(self.STATE_TEND_FIRE)
                    return

            if self.firewood <= 3:
                if random.random() < 0.18:
                    self._begin_chore(self.STATE_GATHER_WOOD)
                    return

            # Occasionally fetch water.
            if random.random() < 0.045:
                self._begin_chore(self.STATE_GET_WATER)
                return

            roll = random.random()

            if roll < 0.15:
                self._emote_random(self.armour_emotes)

            elif roll < 0.22:
                self.emote(
                    "hums a few bars of an old marching song."
                )
                self._delay(1.5, 2.5)

                self._patrol_step = "sing"
                return

            elif roll < 0.42:
                self._make_direction_observation(direction)

            elif roll < 0.54:
                self._say_random(self.life_advice)

            else:
                self._emote_random(self.general_observations)

            self._patrol_step = "march"
            self._delay(4.0, 8.0)
            return

        if self._patrol_step == "sing":
            self._say_random(self.marching_songs)
            self._patrol_step = "march"
            self._delay(4.0, 7.0)
            return

        if self._patrol_step == "march":
            next_direction = self._next_patrol_direction()

            marching_emotes = (
                "marches steadily from the {0} road towards the {1} road.",
                "turns from the {0} road and walks towards the {1} road.",
                "continues his circuit, heading from the {0} road to the {1} road.",
                "sets off at a measured pace towards the {1} road.",
                "leaves his position by the {0} road and marches towards the {1} road."
            )

            text = random.choice(marching_emotes).format(
                direction,
                next_direction
            )

            self.emote(text)

            self._patrol_direction_index = (
                self._patrol_direction_index + 1
            ) % len(self.PATROL_DIRECTIONS)

            self._patrol_step = "arrive"
            self._delay(3.0, 6.0)
            return

        self._patrol_step = "arrive"
        self._delay(1.0)

    def _make_direction_observation(self, direction):
        if direction == "east":
            self._say_random(self.east_observations)

        elif direction == "west":
            self._say_random(self.west_observations)

        elif direction == "north":
            self._say_random(self.north_observations)

        elif direction == "south":
            self._say_random(self.south_observations)

        else:
            self._emote_random(self.general_observations)

    # ------------------------------------------------------------------
    # Greeting state
    # ------------------------------------------------------------------

    def _tick_greet(self):
        if self._current_greeting is None:
            if not self._greeting_queue:
                self.state = self._greeting_resume_state
                self._delay(1.5, 3.0)
                return

            self._current_greeting = self._greeting_queue.pop(0)
            self._greeting_step = 0

        greeting = self._current_greeting
        name = greeting["name"]

        if greeting["is_gwen"]:
            self._tick_greet_gwen(greeting)
            return

        if self._greeting_step == 0:
            if greeting["returning"]:
                self.emote(
                    "recognises {0} and smiles warmly.".format(name)
                )
            else:
                self.emote(
                    "turns from his watch to greet {0}.".format(name)
                )

            self._greeting_step = 1
            self._delay(0.8, 1.5)
            return

        if self._greeting_step == 1:
            if greeting["returning"]:
                text = random.choice(
                    self.return_greetings
                ).format(name)
            else:
                text = random.choice(
                    self.first_greetings
                ).format(name)

            self.speak(text)

            if greeting["give_advice"]:
                self._greeting_step = 2
                self._delay(1.5, 3.0)
            else:
                self._finish_greeting()

            return

        if self._greeting_step == 2:
            self._say_random(self.life_advice)
            self._finish_greeting()
            return

        self._finish_greeting()

    def _tick_greet_gwen(self, greeting):
        if self._greeting_step == 0:
            self.emote(
                "immediately straightens and stands to attention."
            )

            self._greeting_step = 1
            self._delay(0.7, 1.2)
            return

        if self._greeting_step == 1:
            self.emote(
                "bows deeply and respectfully before Lady Gwen."
            )

            self._greeting_step = 2
            self._delay(0.8, 1.4)
            return

        if self._greeting_step == 2:
            self._say_random(self.gwen_greetings)

            if greeting["give_advice"]:
                self._greeting_step = 3
                self._delay(1.5, 2.5)
            else:
                self._finish_greeting()

            return

        if self._greeting_step == 3:
            self.speak(
                "If I may offer one thought, my Lady: {0}".format(
                    random.choice(self.life_advice)
                )
            )

            self._finish_greeting()
            return

        self._finish_greeting()

    def _finish_greeting(self):
        self._current_greeting = None
        self._greeting_step = 0

        if self._greeting_queue:
            self._delay(0.8, 1.5)
            return

        self.state = self._greeting_resume_state
        self._delay(1.5, 3.0)

    # ------------------------------------------------------------------
    # Water state
    # ------------------------------------------------------------------

    def _tick_get_water(self):
        if self._water_step == 0:
            self.emote(
                "leaves his patrol route and turns towards the old stone well."
            )

            self._water_step = 1
            self._delay(2.0, 4.0)
            return

        if self._water_step == 1:
            self.emote(
                "walks across the centre of the crossroads towards the well."
            )

            self._water_step = 2
            self._delay(2.0, 4.0)
            return

        if self._water_step == 2:
            self.emote(
                "reaches the well and sets his leather waterskin upon its edge."
            )

            self._water_step = 3
            self._delay(1.5, 3.0)
            return

        if self._water_step == 3:
            self.emote(
                "lowers the bucket carefully into the clear water below."
            )

            self._water_step = 4
            self._delay(2.5, 4.5)
            return

        if self._water_step == 4:
            self.emote(
                "hauls the bucket back up and fills his waterskin."
            )

            self.waterskin_full = True
            self._water_should_drink = random.random() < 0.65

            if self._water_should_drink:
                self._water_step = 5
            else:
                self._water_step = 7

            self._delay(1.5, 3.0)
            return

        if self._water_step == 5:
            self._say_random(self.thirsty_speech)
            self._water_step = 6
            self._delay(1.0, 2.0)
            return

        if self._water_step == 6:
            self.emote(
                "raises the waterskin and takes a long, grateful drink."
            )

            self.waterskin_full = False
            self._water_step = 7
            self._delay(2.0, 4.0)
            return

        if self._water_step == 7:
            self.emote(
                "fastens the waterskin securely and turns back towards "
                "the {0} road.".format(self._last_patrol_direction)
            )

            self._water_step = 8
            self._delay(2.0, 4.0)
            return

        if self._water_step == 8:
            self.emote(
                "walks back from the well towards his place upon the "
                "{0} road.".format(self._last_patrol_direction)
            )

            self._water_step = 9
            self._delay(2.0, 4.0)
            return

        if self._water_step == 9:
            self.emote(
                "resumes his watch as though he had never left it."
            )

            self._water_step = 0
            self._resume_patrol()
            return

        self._water_step = 0
        self._resume_patrol()

    # ------------------------------------------------------------------
    # Fire state
    # ------------------------------------------------------------------

    def _tick_tend_fire(self):
        if self._fire_step == 0:
            self.emote(
                "glances towards the campfire and frowns at the weakening flames."
            )

            self._fire_step = 1
            self._delay(1.5, 3.0)
            return

        if self._fire_step == 1:
            self.emote(
                "walks from his patrol route towards the campfire."
            )

            self._fire_step = 2
            self._delay(2.0, 4.0)
            return

        if self._fire_step == 2:
            self.emote(
                "kneels beside the fire and studies the glowing embers."
            )

            if self.firewood <= 0:
                self._fire_step = 6
            else:
                self._fire_step = 3

            self._delay(1.5, 3.0)
            return

        if self._fire_step == 3:
            self.emote(
                "takes a dry log from the woodpile and lays it carefully "
                "across the embers."
            )

            self.firewood -= 1
            self._fire_step = 4
            self._delay(2.0, 4.0)
            return

        if self._fire_step == 4:
            self.emote(
                "uses a sturdy branch to stir the embers until sparks "
                "rise into the air."
            )

            self.fire_strength += random.uniform(30.0, 42.0)

            if self.fire_strength > 100:
                self.fire_strength = 100

            self._fire_step = 5
            self._delay(2.0, 4.0)
            return

        if self._fire_step == 5:
            self._say_random(self.fire_speech)
            self._fire_step = 7
            self._delay(1.5, 3.0)
            return

        if self._fire_step == 6:
            self.speak(
                "The firewood is spent. I had best gather more before "
                "the embers die entirely."
            )

            self._fire_step = 0
            self._begin_chore(self.STATE_GATHER_WOOD)
            return

        if self._fire_step == 7:
            self.emote(
                "rises from beside the renewed fire and returns towards "
                "the {0} road.".format(self._last_patrol_direction)
            )

            self._fire_step = 8
            self._delay(2.0, 4.0)
            return

        if self._fire_step == 8:
            self.emote(
                "resumes his patient patrol of the crossroads."
            )

            self._fire_step = 0
            self._resume_patrol()
            return

        self._fire_step = 0
        self._resume_patrol()

    # ------------------------------------------------------------------
    # Wood-gathering state
    # ------------------------------------------------------------------

    def _tick_gather_wood(self):
        if self._wood_step == 0:
            self.emote(
                "looks over the dwindling pile of firewood."
            )

            self._wood_step = 1
            self._delay(1.5, 3.0)
            return

        if self._wood_step == 1:
            if self.has_axe:
                self.emote(
                    "takes up his small woodcutting axe."
                )
            else:
                self.emote(
                    "searches beside the fire until he finds his "
                    "woodcutting axe."
                )
                self.has_axe = True

            self._wood_step = 2
            self._delay(1.5, 3.0)
            return

        if self._wood_step == 2:
            self.emote(
                "walks towards the hedgerow in search of fallen wood."
            )

            self._wood_step = 3
            self._delay(3.0, 5.0)
            return

        if self._wood_step == 3:
            self.emote(
                "finds a fallen branch and tests the timber with one boot."
            )

            self._wood_step = 4
            self._delay(1.5, 3.0)
            return

        if self._wood_step == 4:
            self.emote(
                "swings his axe into the fallen branch with a solid crack."
            )

            self._wood_step = 5
            self._delay(2.0, 3.5)
            return

        if self._wood_step == 5:
            self.emote(
                "chops the branch into lengths suitable for the fire."
            )

            self._wood_gathered = random.randint(4, 7)
            self._wood_step = 6
            self._delay(2.5, 4.0)
            return

        if self._wood_step == 6:
            self._say_random(self.wood_speech)
            self._wood_step = 7
            self._delay(1.5, 3.0)
            return

        if self._wood_step == 7:
            self.emote(
                "binds the cut wood into a bundle and lifts it onto "
                "one shoulder."
            )

            self._wood_step = 8
            self._delay(2.0, 4.0)
            return

        if self._wood_step == 8:
            self.emote(
                "returns from the hedgerow carrying the bundle of logs."
            )

            self._wood_step = 9
            self._delay(3.0, 5.0)
            return

        if self._wood_step == 9:
            self.emote(
                "adds the newly cut wood to the neat pile beside the fire."
            )

            self.firewood += self._wood_gathered
            self._wood_gathered = 0
            self._wood_step = 10
            self._delay(1.5, 3.0)
            return

        if self._wood_step == 10:
            self.emote(
                "wipes the axe blade clean and returns it to its place."
            )

            self._wood_step = 11
            self._delay(1.5, 3.0)
            return

        if self._wood_step == 11:
            # If the fire became dangerously weak while he gathered wood,
            # tend it before returning to patrol.
            if self.fire_strength <= 35:
                self._wood_step = 0
                self._begin_chore(self.STATE_TEND_FIRE)
                return

            self.emote(
                "returns to his interrupted watch upon the "
                "{0} road.".format(self._last_patrol_direction)
            )

            self._wood_step = 0
            self._resume_patrol()
            return

        self._wood_step = 0
        self._resume_patrol()

    # ------------------------------------------------------------------
    # Player events
    # ------------------------------------------------------------------

    def _behavior_on_player_enter(self, player):
        key = player.name.lower()
        now = time.time()

        with self._state_lock:
            traveller = self.known_travellers.get(key)

            if traveller is None:
                traveller = {
                    "name": player.name,
                    "visits": 0,
                    "present": False,
                    "last_entered": None,
                    "last_left": None
                }

                self.known_travellers[key] = traveller

            returning = traveller["visits"] > 0

            traveller["name"] = player.name
            traveller["visits"] += 1
            traveller["present"] = True
            traveller["last_entered"] = now

            greeting = {
                "name": player.name,
                "returning": returning,
                "visits": traveller["visits"],
                "is_gwen": self._is_lady_gwen(player.name),
                "give_advice": random.random() < 0.28
            }

            self._greeting_queue.append(greeting)

            if self.state != self.STATE_GREET:
                self._greeting_resume_state = self.state
                self.state = self.STATE_GREET
                self._current_greeting = None
                self._greeting_step = 0

            # He notices arrivals promptly, but the delay still avoids doing
            # work inside the player's session thread.
            soon = now + random.uniform(0.4, 1.0)

            if self.next_action_time > soon:
                self.next_action_time = soon

    def _behavior_on_player_leave(self, player):
        key = player.name.lower()
        now = time.time()

        with self._state_lock:
            traveller = self.known_travellers.get(key)

            if traveller is None:
                traveller = {
                    "name": player.name,
                    "visits": 1,
                    "present": False,
                    "last_entered": None,
                    "last_left": now
                }

                self.known_travellers[key] = traveller
            else:
                traveller["present"] = False
                traveller["last_left"] = now

        # Departures are announced immediately because the room may have no
        # players left by the next NPC tick.
        if self._is_lady_gwen(player.name):
            self.emote(
                "bows respectfully as Lady Gwen departs."
            )
            self.speak(
                "Lady Gwen departs. May the roads be gentle beneath "
                "thy feet, my Lady."
            )

        elif random.random() < 0.60:
            farewell = random.choice(
                self.departure_greetings
            ).format(player.name)

            self.speak(farewell)
