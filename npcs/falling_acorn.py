import random
import time
import math

from core import NPC, NPCAction, NPCBehavior


class FallingAcornBehavior(NPCBehavior):
    """A bounded local heartbeat for the Green's comic acorn hazard."""

    mode = NPCBehavior.MODE_SIMPLE_RANDOM

    def __init__(
        self,
        village_state,
        interval=45.0,
        random_source=None,
        time_source=None
    ):
        NPCBehavior.__init__(self)

        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
        ):
            raise TypeError("falling-acorn interval must be a number")

        if interval <= 0 or not math.isfinite(interval):
            raise ValueError("falling-acorn interval must be positive")

        self.village_state = village_state
        self.interval = float(interval)
        self.random_source = random_source or random
        self.time_source = time_source or time.time
        self.next_action_time = self.time_source() + self.interval

    def tick(self):
        now = self.time_source()

        if now < self.next_action_time:
            return None

        self.next_action_time = now + self.interval
        npc = self.npc

        if npc is None or npc.room is None:
            return None

        room = npc.room

        with room.lock:
            if npc.room is not room or not room.players:
                return None

            players = tuple(room.players)

        if self.village_state.tree_snapshot()["danger"] <= 0:
            return None

        target = self.random_source.choice(players)
        return NPCAction.emote(
            "drops a giant acorn squarely onto {0}'s head. Bonk.".format(
                target.name
            )
        )


class FallingAcornHazard(NPC):
    def __init__(self, village_state, **behavior_settings):
        NPC.__init__(
            self,
            "the Hanging Tree",
            "The invisible weight of the Hanging Tree looms overhead.",
            behavior=FallingAcornBehavior(
                village_state,
                **behavior_settings
            )
        )
        self.flags.add("hidden")
