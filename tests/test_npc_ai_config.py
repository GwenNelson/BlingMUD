import unittest

import blingmud
from core import NPCBehavior, Player
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
            self.assertEqual(world.rooms["crossroads"].knight.behavior_mode, NPCBehavior.MODE_FSM)
            self.assertEqual(world.rooms["vals_hella_holler"].val.behavior_mode, NPCBehavior.MODE_FSM)
        finally:
            runtime.shutdown()

    def test_world_build_and_local_npcs_work_without_provider_configuration(self):
        world = blingmud.World()
        self.assertIsNone(configure_world_ai(world, {}))
        self.assertIn("village_green", world.rooms)
        self.assertIn("smithereens", world.rooms)
        self.assertIn("temple_of_self", world.rooms)

    def test_wrapped_knight_fallback_remains_bound_and_replies(self):
        class Session(object):
            def __init__(self): self.messages = []
            def send(self, message): self.messages.append(message)
        world = blingmud.World()
        runtime = configure_world_ai(
            world,
            {"BLINGMUD_OPENROUTER_ENABLED": "1"},
            provider=Provider()
        )
        try:
            player = Player("Visitor")
            player.session = Session()
            room = world.rooms["crossroads"]
            room.enter(player, announce=False)
            room.notify_player_said(player, "Hello Knight")
            self.assertTrue(player.session.messages)
            self.assertTrue(any(
                phrase in player.session.messages[-1]
                for phrase in ("Greetings", "Well met", "Hail and welcome")
            ))
        finally:
            runtime.shutdown()


if __name__ == "__main__": unittest.main()
