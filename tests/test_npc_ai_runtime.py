import threading
import unittest

from npc_ai_runtime import NPCAdvisorRuntime


class Provider(object):
    def __init__(self): self.calls = 0
    def complete(self, messages, max_tokens=8): self.calls += 1; return None


class RuntimeTests(unittest.TestCase):
    def test_runtime_is_bounded_and_stops(self):
        provider = Provider()
        runtime = NPCAdvisorRuntime(provider, queued=1)
        self.assertTrue(runtime.observe({"event": "tick"}))
        runtime.observe({"event": "tick"})
        self.assertTrue(runtime.shutdown())
        self.assertTrue(runtime.status_snapshot()["closed"])


if __name__ == "__main__": unittest.main()
