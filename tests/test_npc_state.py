import json
import unittest

import blingmud
from npc_state import (
    NPCStateError,
    restore_npc_state,
    serialize_npc_state,
    validate_npc_state_json
)


class NPCStateTests(unittest.TestCase):
    def test_knight_snapshot_round_trips_with_presence_cleared(self):
        knight = blingmud.World().rooms["crossroads"].knight
        knight.known_travellers["alice"] = {
            "name": "Alice",
            "visits": 3,
            "present": True,
            "last_entered": 10.0,
            "last_left": 9.0
        }
        encoded = serialize_npc_state("brave_sir_knight", knight.behavior)
        restored = blingmud.World().rooms["crossroads"].knight
        restore_npc_state(restored.behavior, encoded)
        self.assertFalse(restored.known_travellers["alice"]["present"])
        self.assertEqual(restored.known_travellers["alice"]["visits"], 3)

    def test_rejects_unknown_keys_and_oversized_documents(self):
        document = {
            "version": 1,
            "npc_id": "val",
            "state": "hosting",
            "resources": {"last_wisp_harm_seen": 0},
            "memory": {}
        }
        document["unexpected"] = True
        with self.assertRaises(NPCStateError):
            validate_npc_state_json(json.dumps(document))
        with self.assertRaises(NPCStateError):
            validate_npc_state_json("x" * 16385)

    def test_invalid_restore_does_not_change_val(self):
        val = blingmud.World().rooms["vals_hella_holler"].val
        before = val.behavior.last_wisp_harm_seen
        with self.assertRaises(NPCStateError):
            restore_npc_state(val.behavior, "{}")
        self.assertEqual(val.behavior.last_wisp_harm_seen, before)


if __name__ == "__main__":
    unittest.main()
