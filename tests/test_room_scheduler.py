import unittest

from core import NPC, NPCBehavior, NPCManager, Player, Room


class FakeClock(object):
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class RecordingBehavior(NPCBehavior):
    def __init__(self):
        NPCBehavior.__init__(self)
        self.events = []

    def on_player_enter(self, player):
        self.events.append(("enter", player))

    def on_player_leave(self, player):
        self.events.append(("leave", player, player.room))

    def on_say(self, player, text):
        self.events.append(("say", player, text))

    def on_emote(self, player, action):
        self.events.append(("emote", player, action))

    def tick(self):
        self.events.append(("tick",))


class RoomActivityTests(unittest.TestCase):
    def test_room_lifecycle_is_idempotent_and_records_activity(self):
        clock = FakeClock(1.0)
        room = Room("activity", "Activity", "A test room.", clock)
        behavior = RecordingBehavior()
        npc = NPC("Observer", behavior=behavior)
        player = Player("Visitor")
        room.add_npc(npc)

        try:
            self.assertTrue(room.enter(player, announce=False))
            self.assertFalse(room.enter(player, announce=False))

            clock.now = 2.0
            self.assertTrue(room.notify_player_said(player, "Hello"))
            clock.now = 3.0
            self.assertTrue(room.notify_player_emoted(player, "waves"))
            clock.now = 4.0
            self.assertTrue(room.leave(player, announce=False))
            self.assertFalse(room.leave(player, announce=False))

            self.assertIsNone(player.room)
            self.assertEqual(
                behavior.events,
                [
                    ("enter", player),
                    ("say", player, "Hello"),
                    ("emote", player, "waves"),
                    ("leave", player, room)
                ]
            )
            self.assertEqual(
                room.activity_snapshot(),
                {
                    "room_id": "activity",
                    "active": False,
                    "occupancy": 0,
                    "visits": 1,
                    "interactions": 2,
                    "last_activity_at": 4.0
                }
            )
        finally:
            room.remove_npc(npc)

    def test_stale_player_events_do_not_wake_room_npcs(self):
        room = Room("stale", "Stale", "A test room.")
        behavior = RecordingBehavior()
        npc = NPC("Observer", behavior=behavior)
        stale_player = Player("Gone")
        room.add_npc(npc)

        try:
            self.assertFalse(
                room.notify_player_said(stale_player, "I am not here")
            )
            self.assertFalse(
                room.notify_player_emoted(stale_player, "waves remotely")
            )
            self.assertEqual(behavior.events, [])
            self.assertEqual(room.interaction_count, 0)
        finally:
            room.remove_npc(npc)

    def test_enter_transfers_player_out_of_a_previous_room(self):
        first_room = Room("first", "First", "The first room.")
        second_room = Room("second", "Second", "The second room.")
        player = Player("Traveller")
        first_room.enter(player, announce=False)

        self.assertTrue(second_room.enter(player, announce=False))

        self.assertNotIn(player, first_room.players)
        self.assertIn(player, second_room.players)
        self.assertIs(player.room, second_room)
        self.assertEqual(first_room.visit_count, 1)
        self.assertEqual(second_room.visit_count, 1)

        second_room.leave(player, announce=False)


class RoomAwareSchedulerTests(unittest.TestCase):
    def test_manager_ticks_only_npcs_in_rooms_with_players(self):
        manager = NPCManager()
        hot_room = Room("hot", "Hot", "A populated room.")
        cold_room = Room("cold", "Cold", "An empty room.")
        hot_behavior = RecordingBehavior()
        cold_behavior = RecordingBehavior()
        detached_behavior = RecordingBehavior()
        hot_npc = NPC("Hot NPC", behavior=hot_behavior)
        cold_npc = NPC("Cold NPC", behavior=cold_behavior)
        detached_npc = NPC("Detached NPC", behavior=detached_behavior)
        hot_room.players.append(Player("Visitor"))
        hot_room.add_npc(hot_npc)
        cold_room.add_npc(cold_npc)
        manager.register(hot_npc)
        manager.register(cold_npc)
        manager.register(detached_npc)

        try:
            self.assertEqual(manager.active_npcs_snapshot(), (hot_npc,))

            manager.tick()

            self.assertEqual(hot_behavior.events, [("tick",)])
            self.assertEqual(cold_behavior.events, [])
            self.assertEqual(detached_behavior.events, [])

            hot_room.players = []
            manager.tick()
            self.assertEqual(hot_behavior.events, [("tick",)])
        finally:
            hot_room.remove_npc(hot_npc)
            cold_room.remove_npc(cold_npc)

    def test_ticker_can_restart_only_after_previous_thread_stops(self):
        manager = NPCManager()

        try:
            self.assertTrue(manager.start())
            self.assertFalse(manager.start())
            manager.stop(timeout=0.5)
            self.assertFalse(manager.running)
            self.assertFalse(manager._ticker_thread.is_alive())

            self.assertTrue(manager.start())
            manager.stop(timeout=0.5)
            self.assertFalse(manager._ticker_thread.is_alive())
        finally:
            manager.stop(timeout=0.5)

    def test_ticker_refuses_replacement_for_a_still_live_thread(self):
        class StuckThread(object):
            def is_alive(self):
                return True

        manager = NPCManager()
        manager._ticker_thread = StuckThread()
        manager._stop_event.set()

        self.assertFalse(manager.start())
        self.assertTrue(manager._stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
