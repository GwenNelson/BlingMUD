import unittest

import blingmud
from core import NPCBehavior
from npc_ai_config import configure_world_ai


class Provider(object):
    status = "disabled_by_config"
    def refresh_models(self): return ()
    def complete(self, messages, max_tokens=8): return None


class AIConfigTests(unittest.TestCase):
    def test_disabled_configuration_creates_no_runtime_or_wrappers(self):
        self.assertIsNone(configure_world_ai(blingmud.World(), {}))

    def test_enabled_configuration_wraps_knight_and_val_with_local_fallbacks(self):
        world = blingmud.World()
        runtime = configure_world_ai(world, {"BLINGMUD_OPENROUTER_ENABLED": "1"}, provider=Provider())
        try:
            self.assertEqual(world.rooms["crossroads"].knight.behavior_mode, NPCBehavior.MODE_LLM_FSM)
            self.assertEqual(world.rooms["vals_hella_holler"].val.behavior_mode, NPCBehavior.MODE_LLM_FSM)
        finally:
            runtime.shutdown()


if __name__ == "__main__": unittest.main()
