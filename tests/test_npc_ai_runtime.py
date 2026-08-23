import threading
import unittest

from npc_ai_runtime import NPCAdvisorRuntime


class Provider(object):
    def __init__(self): self.calls = 0
    def complete(self, messages, max_tokens=8): self.calls += 1; return None


class BlockingProvider(object):
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def complete(self, messages, max_tokens=8):
        self.started.set()
        self.release.wait(1.0)
        return None


class RuntimeTests(unittest.TestCase):
    def test_runtime_is_bounded_and_stops(self):
        provider = Provider()
        runtime = NPCAdvisorRuntime(provider, queued=1)
        self.assertTrue(runtime.observe({"event": "tick"}))
        runtime.observe({"event": "tick"})
        self.assertTrue(runtime.shutdown())
        self.assertTrue(runtime.status_snapshot()["closed"])

    def test_interactive_popular_rooms_score_above_ambient_ticks(self):
        ambient = {"event": "tick", "occupancy": 1, "visits": 1, "interactions": 0}
        interactive = {"event": "on_say", "occupancy": 3, "visits": 40, "interactions": 9}
        self.assertGreater(
            NPCAdvisorRuntime.priority_score(interactive),
            NPCAdvisorRuntime.priority_score(ambient)
        )

    def test_interactive_work_evicts_queued_ambient_work(self):
        provider = BlockingProvider()
        runtime = NPCAdvisorRuntime(provider, workers=1, queued=1)
        try:
            self.assertTrue(runtime.observe({"event": "tick"}))
            self.assertTrue(provider.started.wait(1.0))
            self.assertTrue(runtime.observe({"event": "tick", "occupancy": 1}))
            self.assertTrue(runtime.observe({"event": "on_say", "occupancy": 1}))
            self.assertGreaterEqual(runtime.status_snapshot()["dropped"], 1)
        finally:
            provider.release.set()
            self.assertTrue(runtime.shutdown())


if __name__ == "__main__": unittest.main()
