import unittest

from core import NPC, NPCAction, NPCBehavior, Player, Room
from llm_fsm import AdvisoryFSMBehavior


class Fallback(NPCBehavior):
    def on_say(self, player, text):
        return NPCAction.say("local reply")


class Advisor(object):
    def __init__(self): self.frames = []
    def observe(self, frame): self.frames.append(frame)


class CallbackAdvisor(object):
    supports_callbacks = True

    def __init__(self): self.frames = []

    def observe(self, frame, callback):
        self.frames.append(frame)
        callback(1, frame)


class ReplyAdvisor(CallbackAdvisor):
    llm_ready = True
    def observe(self, frame, callback):
        self.frames.append(frame)
        callback(0, frame, "A remote but bounded reply.")


class CandidateFallback(Fallback):
    def __init__(self):
        super().__init__()
        self.hint = None
        self.snapshot = None

    def reset_advisory_candidate_snapshot(self):
        self.snapshot = None

    def advisory_candidate_snapshot(self):
        return self.snapshot

    def set_advisory_hint(self, state, candidate_id, choice):
        self.hint = (candidate_id, choice)

    def on_say(self, player, text):
        choice = 0 if self.hint is None else self.hint[1]
        self.hint = None
        self.snapshot = {
            "id": "candidate",
            "actions": (
                {"type": "say", "text": "local reply"},
                {"type": "say", "text": "advised reply"}
            )
        }
        return NPCAction.say(("local reply", "advised reply")[choice])


class AdvisoryFSMTests(unittest.TestCase):
    def test_local_result_is_unchanged_and_cold_rooms_make_no_advisory_call(self):
        advisor = Advisor()
        behavior = AdvisoryFSMBehavior(Fallback(), advisor)
        npc = NPC("Test", "test", behavior=behavior)
        room = Room("test", "Test", "test")
        room.add_npc(npc)
        player = Player("Player")
        self.assertEqual(behavior.on_say(player, "hello").text, "local reply")
        self.assertEqual(advisor.frames, [])
        room.enter(player, announce=False)
        self.assertEqual(len(advisor.frames), 1)
        self.assertEqual(behavior.on_say(player, "hello").text, "local reply")
        self.assertEqual(len(advisor.frames), 2)
        room.leave(player, announce=False)
        room.remove_npc(npc)

    def test_valid_choice_is_consumed_only_by_a_later_local_decision(self):
        advisor = CallbackAdvisor()
        behavior = AdvisoryFSMBehavior(CandidateFallback(), advisor)
        npc = NPC("Test", "test", behavior=behavior)
        room = Room("test", "Test", "test")
        room.add_npc(npc)
        player = Player("Player")
        room.enter(player, announce=False)

        self.assertEqual(behavior.on_say(player, "hello").text, "local reply")
        self.assertEqual(behavior.on_say(player, "hello").text, "advised reply")
        self.assertEqual(len(advisor.frames), 2)
        room.leave(player, announce=False)
        room.remove_npc(npc)

    def test_valid_remote_reply_is_emitted_on_a_later_tick(self):
        behavior = AdvisoryFSMBehavior(CandidateFallback(), ReplyAdvisor())
        npc = NPC("Test", "test", behavior=behavior)
        room = Room("test", "Test", "test")
        room.add_npc(npc)
        player = Player("Player")
        room.enter(player, announce=False)
        behavior.on_say(player, "hello")
        actions = behavior.tick()
        self.assertEqual(actions[-1].text, "A remote but bounded reply.")
        self.assertEqual(behavior.mode, NPCBehavior.MODE_LLM_FSM)
        room.leave(player, announce=False)
        room.remove_npc(npc)

    def test_speech_frame_includes_speaker_and_bounded_recent_conversation(self):
        advisor = ReplyAdvisor()
        behavior = AdvisoryFSMBehavior(CandidateFallback(), advisor)
        npc = NPC("Test", "test", behavior=behavior)
        room = Room("test", "Test", "test")
        room.add_npc(npc)
        player = Player("Gwen")
        room.enter(player, announce=False)
        behavior.on_say(player, "goodbye")
        behavior.on_say(player, "I am leaving now")
        self.assertEqual(advisor.frames[0]["speaker"], "Gwen")
        self.assertNotIn("history", advisor.frames[0])
        self.assertEqual(
            advisor.frames[1]["history"][0],
            {
                "speaker": "Gwen",
                "input": "goodbye",
                "reply": "A remote but bounded reply."
            }
        )
        room.leave(player, announce=False)
        room.remove_npc(npc)


if __name__ == "__main__":
    unittest.main()
