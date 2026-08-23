"""Optional advisory wrapper: local NPC behaviour remains authoritative."""

from core import NPCBehavior


class AdvisoryFSMBehavior(NPCBehavior):
    """Observe bounded local decisions without allowing remote control.

    The wrapped behaviour performs the real state transition first.  An
    advisor may observe a bounded frame for future selection policies, but
    its result is deliberately ignored unless a later explicit candidate
    protocol is introduced and validated.
    """

    mode = NPCBehavior.MODE_LLM_FSM
    _LOCAL = frozenset(("fallback", "advisor", "advisory_failures", "advisory_calls", "npc"))

    def __getattr__(self, name):
        fallback = self.__dict__.get("fallback")
        if fallback is not None:
            return getattr(fallback, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        fallback = self.__dict__.get("fallback")
        if fallback is not None and name not in self._LOCAL and hasattr(fallback, name):
            setattr(fallback, name, value)
            return
        object.__setattr__(self, name, value)

    def __init__(self, fallback, advisor=None):
        if not isinstance(fallback, NPCBehavior):
            raise TypeError("LLM fallback must be an NPCBehavior")
        NPCBehavior.__init__(self)
        self.fallback = fallback
        self.advisor = advisor
        self.advisory_failures = 0
        self.advisory_calls = 0

    def bind(self, npc):
        NPCBehavior.bind(self, npc)
        self.fallback.bind(npc)

    def unbind(self, npc):
        self.fallback.unbind(npc)
        NPCBehavior.unbind(self, npc)

    def _active(self):
        npc = self.npc
        room = None if npc is None else npc.room
        if room is None:
            return False
        with room.lock:
            return npc.room is room and bool(room.players)

    def _dispatch(self, method, *arguments):
        result = getattr(self.fallback, method)(*arguments)
        if self.advisor is None or not self._active():
            return result
        if result is None:
            actions = ()
        elif isinstance(result, (tuple, list)):
            actions = tuple(result)
        else:
            actions = (result,)
        npc = self.npc
        room = npc.room
        snapshot = room.activity_snapshot()
        frame = {
            "event": method,
            "npc": npc.name[:80],
            "state": getattr(self.fallback, "current_state", None),
            "room": room.room_id[:80],
            "occupancy": snapshot["occupancy"],
            "visits": min(snapshot["visits"], 1000000),
            "interactions": min(snapshot["interactions"], 1000000),
            "candidates": [{
                "choice": 0,
                "actions": [
                    {"type": action.action_type, "text": action.text[:1000]}
                    for action in actions[:8]
                ]
            }]
        }
        try:
            self.advisor.observe(frame)
            self.advisory_calls += 1
        except Exception:
            self.advisory_failures += 1
        return result

    def on_player_enter(self, player):
        return self._dispatch("on_player_enter", player)

    def on_player_leave(self, player):
        return self._dispatch("on_player_leave", player)

    def on_say(self, player, text):
        return self._dispatch("on_say", player, text)

    def on_emote(self, player, action):
        return self._dispatch("on_emote", player, action)

    def tick(self):
        return self._dispatch("tick")
