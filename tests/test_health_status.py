import unittest

import blingmud
from core import Item, Player, Room
from status_runtime import StatusCoordinator


class FakeClock(object):
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class RecordingRequest(object):
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def shutdown(self, how):
        pass

    def close(self):
        pass


class SmallWorld(object):
    def __init__(self):
        self.starting_room = Room("town_square", "Town Square", "Safe.")
        self.danger_room = Room("danger", "Danger", "Dangerous.")
        self.rooms = {
            self.starting_room.room_id: self.starting_room,
            self.danger_room.room_id: self.danger_room
        }


class HealthAndStatusTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.world = SmallWorld()
        self.request = RecordingRequest()
        self.session = blingmud.Session(
            self.request,
            ("127.0.0.1", 1),
            self.world,
            monotonic_source=self.clock
        )
        self.player = Player("Tester")
        self.player.session = self.session
        self.session.player = self.player
        self.world.danger_room.enter(self.player, announce=False)

    def tearDown(self):
        if self.player.room is not None:
            self.player.room.leave(self.player, announce=False)

    def test_damage_healing_and_intoxication_changes_are_bounded(self):
        self.assertEqual(self.player.take_damage(60), 60)
        self.assertTrue(self.player.is_injured)
        self.assertEqual(self.player.heal(10), 10)
        self.assertTrue(self.player.is_injured)
        self.assertEqual(self.player.heal(1), 1)
        self.assertFalse(self.player.is_injured)
        self.assertEqual(self.player.add_intoxication(500), 100)

        for invalid in (True, 1.5, "1"):
            with self.assertRaises(TypeError):
                self.player.take_damage(invalid)

        with self.assertRaises(ValueError):
            self.player.heal(-1)

        self.player.intoxication = 0
        old_intoxication = self.player.intoxication

        with self.assertRaises(ValueError):
            self.player.add_intoxication(1, now=float("nan"))

        self.assertEqual(self.player.intoxication, old_intoxication)

    def test_collapse_is_non_destructive_and_returns_to_town_square(self):
        keepsake = Item("keepsake", wearable=True, worn_where="Head")
        self.player.inventory.append(keepsake)
        self.player.equipment["Head"] = keepsake
        self.player.fabulousness = 23
        self.player.intoxication = 72
        self.player.health = 3

        damage = self.session.damage_player(5, "a test hazard")

        self.assertEqual(damage, 3)
        self.assertEqual(self.player.health, 1)
        self.assertEqual(self.player.intoxication, 0)
        self.assertTrue(self.player.recently_respawned)
        self.assertEqual(self.player.inventory, [keepsake])
        self.assertIs(self.player.equipment["Head"], keepsake)
        self.assertEqual(self.player.fabulousness, 23)
        self.assertIs(self.player.room, self.world.starting_room)

        with self.assertRaises(ValueError):
            self.session.damage_player(1, "unsafe\033[31m")

    def test_online_intoxication_decays_one_point_per_whole_minute(self):
        self.player.intoxication = 5
        coordinator = StatusCoordinator(lambda: [self.session])

        coordinator.tick(now=59.9)
        self.assertEqual(self.player.intoxication, 5)

        coordinator.tick(now=60.0)
        self.assertEqual(self.player.intoxication, 4)

        coordinator.tick(now=180.0)
        self.assertEqual(self.player.intoxication, 2)

        coordinator.tick(now=30.0)
        self.assertEqual(self.player.intoxication, 2)

        coordinator.tick(now=300.0)
        self.assertEqual(self.player.intoxication, 0)


if __name__ == "__main__":
    unittest.main()
