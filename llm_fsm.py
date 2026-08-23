"""Optional advisory wrapper: local NPC behaviour remains authoritative."""

from core import NPCBehavior
from core import NPCAction
from collections import deque
import threading


class AdvisoryFSMBehavior(NPCBehavior):
    """Observe bounded local decisions without allowing remote control.

    The wrapped behaviour performs the real state transition first.  The
    advisor observes a bounded frame and may queue a validated conversational
    reply for a later actor tick, but it cannot directly mutate game state.
    """

    _LOCAL = frozenset((
        "fallback", "advisor", "advisory_failures", "advisory_calls",
        "npc", "_advisory_lock", "local_only", "_pending_replies"
    ))

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
        self._advisory_lock = threading.RLock()
        self.local_only = False
        self._pending_replies = deque(maxlen=4)

    @property
    def mode(self):
        ready = False
        if self.advisor is not None:
            readiness = getattr(self.advisor, "is_ready", None)
            if readiness is not None and self.npc is not None:
                ready = readiness(self.npc.name)
            else:
                ready = getattr(self.advisor, "llm_ready", False)
        if (
            not self.local_only
            and self.advisor is not None
            and ready
        ):
            return NPCBehavior.MODE_LLM_FSM
        return NPCBehavior.MODE_FSM

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
        reset_snapshot = getattr(
            self.fallback, "reset_advisory_candidate_snapshot", None
        )
        if reset_snapshot is not None:
            reset_snapshot()
        result = getattr(self.fallback, method)(*arguments)
        if method == "tick":
            with self._advisory_lock:
                reply = self._pending_replies.popleft() if self._pending_replies else None
            if reply is not None and self._active():
                existing = () if result is None else (
                    tuple(result) if isinstance(result, (tuple, list)) else (result,)
                )
                result = existing + (NPCAction.say(reply),)
        if self.local_only or self.advisor is None or not self._active():
            return result
        if method not in ("on_say", "on_emote", "on_player_enter"):
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
        candidate_snapshot = getattr(
            self.fallback, "advisory_candidate_snapshot", lambda: None
        )()
        if isinstance(candidate_snapshot, dict):
            candidate_id = candidate_snapshot.get("id")
            candidate_actions = candidate_snapshot.get("actions", ())
        else:
            candidate_id = "local"
            candidate_actions = actions
        if (
            getattr(self.advisor, "supports_callbacks", False)
            and not candidate_actions
        ):
            return result
        candidates = []
        for index, action in enumerate(tuple(candidate_actions)[:8]):
            normalized = (
                {"type": action["type"], "text": action["text"][:1000]}
                if isinstance(action, dict) else
                {"type": action.action_type, "text": action.text[:1000]}
            )
            candidates.append({
                "id": str(candidate_id)[:80],
                "actions": [normalized]
            })
        frame = {
            "event": method,
            "npc": npc.name[:80],
            "state": getattr(self.fallback, "current_state", None),
            "room": room.room_id[:80],
            "occupancy": snapshot["occupancy"],
            "visits": min(snapshot["visits"], 1000000),
            "interactions": min(snapshot["interactions"], 1000000),
            "candidates": candidates
        }
        if method in ("on_say", "on_emote") and len(arguments) >= 2:
            frame["input"] = str(arguments[1])[:500]
        try:
            if getattr(self.advisor, "supports_callbacks", False):
                self.advisor.observe(frame, self._store_hint)
            else:
                self.advisor.observe(frame)
            self.advisory_calls += 1
        except Exception:
            self.advisory_failures += 1
        return result

    def set_local_only(self, enabled=True):
        """Force the wrapped FSM to remain local without changing its state."""
        self.local_only = bool(enabled)
        return self.local_only

    def _store_hint(self, choice, frame, reply=None):
        if not self._active():
            return
        candidate = frame.get("candidates", ())
        if not candidate:
            return
        candidate_id = candidate[0].get("id")
        setter = getattr(self.fallback, "set_advisory_hint", None)
        if setter is None and not reply:
            return
        with self._advisory_lock:
            if setter is not None:
                setter(frame.get("state"), candidate_id, choice)
            if frame.get("event") == "on_say" and reply:
                self._pending_replies.append(reply)

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
