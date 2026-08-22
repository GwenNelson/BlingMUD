import io
import sys
import threading
import time
import unittest

from core import (
    NPC,
    NPCActorUnavailable,
    NPCBehavior,
    NPCManager,
    Player,
    Room
)


class StuckTickBehavior(NPCBehavior):
    def __init__(self, started, release):
        NPCBehavior.__init__(self)
        self.started = started
        self.release = release

    def tick(self):
        self.started.set()
        self.release.wait(1.0)


class RecordingBehavior(NPCBehavior):
    def __init__(self):
        NPCBehavior.__init__(self)
        self.events = []

    def tick(self):
        self.events.append("tick")


class FirstCallBlocksBehavior(NPCBehavior):
    def __init__(self, started, release):
        NPCBehavior.__init__(self)
        self.started = started
        self.release = release
        self.calls = 0

    def on_say(self, player, text):
        self.calls += 1

        if self.calls == 1:
            self.started.set()
            self.release.wait(1.0)


class NPCActorIsolationTests(unittest.TestCase):
    def test_non_returning_callback_cannot_block_later_npcs(self):
        manager = NPCManager()
        room = Room("actor_isolation", "Actor Isolation", "A room.")
        room.players.append(Player("Observer"))
        started = threading.Event()
        release = threading.Event()
        stuck = NPC(
            "Stuck",
            behavior=StuckTickBehavior(started, release),
            actor_settings={"callback_timeout": 0.05}
        )
        working_behavior = RecordingBehavior()
        working = NPC(
            "Working",
            behavior=working_behavior,
            actor_settings={"callback_timeout": 0.05}
        )
        room.add_npc(stuck)
        room.add_npc(working)
        manager.register(stuck)
        manager.register(working)
        original_stderr = sys.stderr
        sys.stderr = io.StringIO()

        try:
            before = time.monotonic()
            manager.tick()
            elapsed = time.monotonic() - before
            self.assertTrue(started.is_set())
            self.assertLess(elapsed, 0.5)
            self.assertEqual(working_behavior.events, ["tick"])
            status = stuck.actor_status_snapshot()
            self.assertTrue(status["unresponsive"])
            self.assertEqual(status["fallback_mode"], "inert")
            old_thread = stuck.actor.thread

            with self.assertRaises(NPCActorUnavailable):
                stuck.tick()

            self.assertIs(stuck.actor.thread, old_thread)
        finally:
            release.set()
            manager.unregister(stuck)
            manager.unregister(working)
            room.remove_npc(stuck)
            room.remove_npc(working)
            sys.stderr = original_stderr

        self.assertFalse(stuck.actor.thread.is_alive())
        self.assertFalse(working.actor.thread.is_alive())

    def test_mailbox_is_finite_and_rejected_work_is_reported(self):
        room = Room("actor_mailbox", "Actor Mailbox", "A room.")
        started = threading.Event()
        release = threading.Event()
        behavior = FirstCallBlocksBehavior(started, release)
        npc = NPC(
            "Bounded",
            behavior=behavior,
            actor_settings={
                "mailbox_limit": 2,
                "callback_timeout": 0.5
            }
        )
        player = Player("Speaker")
        room.add_npc(npc)

        try:
            first = npc.schedule_behavior("on_say", player, "one")
            self.assertTrue(started.wait(0.5))
            second = npc.schedule_behavior("on_say", player, "two")
            third = npc.schedule_behavior("on_say", player, "three")

            with self.assertRaises(NPCActorUnavailable):
                npc.schedule_behavior("on_say", player, "four")

            release.set()
            self.assertEqual(npc.await_behavior(first, 0.5), ())
            self.assertEqual(npc.await_behavior(second, 0.5), ())
            self.assertEqual(npc.await_behavior(third, 0.5), ())
            status = npc.actor_status_snapshot()
            self.assertEqual(status["rejected"], 1)
            self.assertEqual(status["mailbox_depth"], 0)
        finally:
            release.set()
            room.remove_npc(npc)

        self.assertFalse(npc.actor.thread.is_alive())


if __name__ == "__main__":
    unittest.main()
