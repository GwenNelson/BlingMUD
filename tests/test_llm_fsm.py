import unittest

from core import NPC, NPCAction, NPCBehavior, Player, Room
from llm_fsm import AdvisoryFSMBehavior


class Fallback(NPCBehavior):
    def on_say(self, player, text):
        return NPCAction.say("local reply")


class Advisor(object):
    def __init__(self): self.frames = []
    def observe(self, frame): self.frames.append(frame)


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


if __name__ == "__main__":
    unittest.main()
