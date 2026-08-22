import json
import os
import tempfile
import unittest

import blingmud
from persistence_runtime import PersistenceWriter, WorldSaveCoordinator
from rooms.village_green import VillageGreen
from village_state import VillageState
from world_state import (
    MAX_WORLD_STATE_BYTES,
    WORLD_STATE_VERSION,
    WorldStateError,
    new_world_state_json,
    restore_world_state,
    serialize_world_state
)


class WorldStateTests(unittest.TestCase):
    def test_round_trip_preserves_only_bounded_shared_village_state(self):
        state = VillageState()
        state.harvest_acorn()
        state.harvest_acorn()
        state.protect_wisp()

        encoded = serialize_world_state(state)
        restored = VillageState()
        restore_world_state(restored, encoded)

        self.assertEqual(restored.persistence_snapshot(), state.persistence_snapshot())
        self.assertEqual(json.loads(encoded)["version"], WORLD_STATE_VERSION)

    def test_wisp_absence_and_harm_count_survive_round_trip(self):
        state = VillageState()
        self.assertEqual(state.attack_wisp(100.0), "removed")
        restored = VillageState()
        restore_world_state(restored, serialize_world_state(state))
        self.assertEqual(restored.wisp_snapshot()["absent_until"], 1900.0)
        self.assertEqual(restored.wisp_snapshot()["harmed_count"], 1)

    def test_invalid_state_is_rejected_without_partial_mutation(self):
        state = VillageState()
        state.harvest_acorn()
        baseline = state.persistence_snapshot()
        document = json.loads(serialize_world_state(state))
        document["village"]["acorn_danger"] = 3

        with self.assertRaises(WorldStateError):
            restore_world_state(state, json.dumps(document))

        document = json.loads(new_world_state_json())
        document["version"] = True

        with self.assertRaises(WorldStateError):
            restore_world_state(state, json.dumps(document))

        self.assertEqual(state.persistence_snapshot(), baseline)

        document = json.loads(new_world_state_json())
        document["unexpected"] = True

        with self.assertRaises(WorldStateError):
            restore_world_state(state, json.dumps(document))

        with self.assertRaises(WorldStateError):
            restore_world_state(state, " " * (MAX_WORLD_STATE_BYTES + 1))

    def test_room_reconciles_wisp_actor_with_restored_absence(self):
        state = VillageState()
        green = VillageGreen(state, night_source=lambda: True)

        try:
            self.assertIs(green.wisp_mother.room, green)
            absent = VillageState()
            absent.attack_wisp(100.0)
            restore_world_state(state, serialize_world_state(absent))
            green.synchronize_persisted_state()
            self.assertIsNone(green.wisp_mother.room)
            self.assertNotIn(green.wisp_mother, green.npcs)
        finally:
            if green.wisp_mother.room is green:
                green.remove_npc(green.wisp_mother)

            if green.acorn_hazard.room is green:
                green.remove_npc(green.acorn_hazard)


class WorldStateDatabaseTests(unittest.TestCase):
    def setUp(self):
        descriptor, self.database_path = tempfile.mkstemp()
        os.close(descriptor)
        self.original_database = blingmud.USERS_DB
        blingmud.USERS_DB = self.database_path
        blingmud.init_user_database()

    def tearDown(self):
        blingmud.USERS_DB = self.original_database
        os.unlink(self.database_path)

    def test_database_initializes_and_updates_the_single_known_state(self):
        initial = blingmud.load_world_state()
        restored = VillageState()
        restore_world_state(restored, initial)
        restored.harvest_acorn()
        changed = serialize_world_state(restored)
        blingmud.update_world_state("village", changed)
        self.assertEqual(blingmud.load_world_state(), changed)

        with self.assertRaises(WorldStateError):
            blingmud.update_world_state("unknown", changed)


class WorldSaveCoordinatorTests(unittest.TestCase):
    def test_dirty_state_is_saved_and_unchanged_state_is_skipped(self):
        state = VillageState()
        baseline = serialize_world_state(state)
        writes = []
        writer = PersistenceWriter(
            lambda key, encoded: writes.append((key, encoded)),
            pending_key_limit=1
        )
        writer.start()
        coordinator = WorldSaveCoordinator(
            state,
            writer,
            persisted_state=baseline
        )

        try:
            self.assertEqual(coordinator.save_if_changed(), "unchanged")
            state.harvest_acorn()
            self.assertEqual(
                coordinator.save_if_changed(wait=True, timeout=1.0),
                "saved"
            )
            self.assertEqual(writes[0][0], "village")
            self.assertEqual(coordinator.save_if_changed(), "unchanged")
        finally:
            writer.shutdown(1.0)

    def test_immediate_writer_rejection_is_visible_and_retryable(self):
        state = VillageState()
        state.harvest_acorn()
        callbacks = []
        writer = PersistenceWriter(lambda key, encoded: None)
        receipt = writer.submit(
            "village",
            serialize_world_state(state),
            completion=lambda success, error, encoded: callbacks.append(
                (success, error, encoded)
            )
        )
        self.assertTrue(receipt.event.is_set())
        self.assertFalse(receipt.success)
        self.assertEqual(len(callbacks), 1)

        coordinator = WorldSaveCoordinator(state, writer)
        self.assertEqual(coordinator.save_if_changed(), "failed")
        writer.start()

        try:
            self.assertEqual(
                coordinator.save_if_changed(wait=True, timeout=1.0),
                "saved"
            )
        finally:
            writer.shutdown(1.0)


if __name__ == "__main__":
    unittest.main()
