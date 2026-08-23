"""Optional advisory wrapper: local NPC behaviour remains authoritative."""

from core import NPCBehavior
from core import NPCAction
from collections import deque
import threading
import time


LLM_SPEECH_FALLBACK_SECONDS = 5.0


class AdvisoryFSMBehavior(NPCBehavior):
    """Observe bounded local decisions without allowing remote control.

    The wrapped behaviour performs the real state transition first.  The
    advisor observes a bounded frame and may queue a validated conversational
    reply for a later actor tick, but it cannot directly mutate game state.
    """

    _LOCAL = frozenset((
        "fallback", "advisor", "advisory_failures", "advisory_calls",
        "npc", "_advisory_lock", "local_only", "_pending_outputs",
        "_pending_speech", "_next_request_id", "_time_source",
        "_conversation"
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
        self._pending_outputs = deque(maxlen=8)
        self._pending_speech = {}
        self._next_request_id = 0
        self._time_source = getattr(advisor, "time_source", time.monotonic)
        self._conversation = deque(maxlen=3)

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
        live_speech = (
            method == "on_say"
            and self.mode == NPCBehavior.MODE_LLM_FSM
        )
        reset_snapshot = getattr(
            self.fallback, "reset_advisory_candidate_snapshot", None
        )
        if reset_snapshot is not None:
            reset_snapshot()
        result = getattr(self.fallback, method)(*arguments)
        if method == "tick":
            with self._advisory_lock:
                now = self._time_source()
                release_all = self.mode != NPCBehavior.MODE_LLM_FSM
                expired = [
                    request_id
                    for request_id, pending in self._pending_speech.items()
                    if release_all or pending["deadline"] <= now
                ]
                for request_id in expired:
                    pending = self._pending_speech.pop(request_id)
                    self._pending_outputs.append(pending["fallback"])
                outputs = tuple(self._pending_outputs)
                self._pending_outputs.clear()
            if outputs and self._active():
                existing = () if result is None else (
                    tuple(result) if isinstance(result, (tuple, list)) else (result,)
                )
                result = existing + tuple(
                    action for output in outputs for action in output
                )
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
            frame["speaker"] = str(
                getattr(arguments[0], "name", "traveller")
            )[:80]
        if method == "on_say":
            with self._advisory_lock:
                history = tuple(dict(item) for item in self._conversation)
            if history:
                frame["history"] = history
        request_id = None
        if live_speech:
            with self._advisory_lock:
                if len(self._pending_speech) >= 4:
                    return result
                self._next_request_id += 1
                request_id = self._next_request_id
                frame["request_id"] = request_id
                self._pending_speech[request_id] = {
                    "deadline": self._time_source()
                    + LLM_SPEECH_FALLBACK_SECONDS,
                    "fallback": actions
                }
        try:
            if getattr(self.advisor, "supports_callbacks", False):
                admitted = self.advisor.observe(frame, self._store_hint)
            else:
                admitted = self.advisor.observe(frame)
            self.advisory_calls += 1
        except Exception:
            self.advisory_failures += 1
            if request_id is not None:
                with self._advisory_lock:
                    self._pending_speech.pop(request_id, None)
            return result
        if admitted is False:
            if request_id is not None:
                with self._advisory_lock:
                    self._pending_speech.pop(request_id, None)
            return result
        if live_speech:
            return ()
        return result

    def set_local_only(self, enabled=True):
        """Force the wrapped FSM to remain local without changing its state."""
        self.local_only = bool(enabled)
        return self.local_only

    def _store_hint(self, choice, frame, reply=None):
        request_id = frame.get("request_id")
        if not self._active():
            if request_id is not None:
                with self._advisory_lock:
                    self._pending_speech.pop(request_id, None)
            return False
        if choice is None:
            if request_id is not None:
                with self._advisory_lock:
                    pending = self._pending_speech.pop(request_id, None)
                    if pending is not None:
                        self._pending_outputs.append(pending["fallback"])
            return True
        candidate = frame.get("candidates", ())
        if not candidate:
            return False
        candidate_id = candidate[0].get("id")
        setter = getattr(self.fallback, "set_advisory_hint", None)
        if setter is None and not reply:
            return False
        with self._advisory_lock:
            if request_id is not None:
                pending = self._pending_speech.pop(request_id, None)
                if pending is None:
                    return False
            if setter is not None:
                setter(frame.get("state"), candidate_id, choice)
            if frame.get("event") == "on_say" and reply:
                self._pending_outputs.append((NPCAction.say(reply),))
                self._conversation.append({
                    "speaker": str(frame.get("speaker", "traveller"))[:80],
                    "input": str(frame.get("input", ""))[:500],
                    "reply": reply[:240]
                })
        return True

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
