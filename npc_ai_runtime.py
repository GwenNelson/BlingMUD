"""Bounded, discard-safe background advisory runtime for NPC AI."""

import queue
import threading
import json
import heapq
import time


class NPCAdvisorRuntime(object):
    def __init__(self, provider, workers=1, queued=8):
        if workers < 1 or workers > 4 or queued < 1 or queued > 64:
            raise ValueError("invalid advisor runtime bounds")
        self.provider = provider
        self.queue = queue.PriorityQueue(maxsize=queued)
        self.closed = False
        self.lock = threading.RLock()
        self.submitted = 0
        self.dropped = 0
        self.completed = 0
        self.invalid_responses = 0
        self.sequence = 0
        self.workers = []
        for index in range(workers):
            worker = threading.Thread(
                target=self._run,
                name="blingmud-npc-ai-{0}".format(index),
                daemon=True
            )
            self.workers.append(worker)
            worker.start()
        self.worker = self.workers[0]

    def observe(self, frame):
        if not isinstance(frame, dict) or len(frame) > 8:
            raise ValueError("invalid advisory frame")
        with self.lock:
            if self.closed:
                self.dropped += 1
                return False
        try:
            encoded = json.dumps(
                frame, ensure_ascii=True, separators=(",", ":")
            ).encode("utf-8")
            if len(encoded) > 8192:
                raise ValueError("advisory frame is too large")
            with self.lock:
                self.sequence += 1
                item = (-self.priority_score(frame), self.sequence, frame)
            self.queue.put_nowait(item)
        except queue.Full:
            with self.queue.mutex:
                queued = list(self.queue.queue)
                if not queued:
                    with self.lock:
                        self.dropped += 1
                    return False
                worst = max(queued, key=lambda value: (value[0], -value[1]))
                if item[0] >= worst[0]:
                    with self.lock:
                        self.dropped += 1
                    return False
                self.queue.queue.remove(worst)
                heapq.heapify(self.queue.queue)
                self.queue.queue.append(item)
                heapq.heapify(self.queue.queue)
                self.queue.not_empty.notify()
                with self.lock:
                    self.dropped += 1
        except (TypeError, ValueError, OverflowError):
            with self.lock:
                self.dropped += 1
            return False
        with self.lock: self.submitted += 1
        return True

    @staticmethod
    def priority_score(frame):
        event = frame.get("event")
        interactive = 100 if event in ("on_say", "on_emote", "on_player_enter") else 0
        occupancy = min(max(int(frame.get("occupancy", 0)), 0), 32)
        visits = min(max(int(frame.get("visits", 0)), 0), 1000000)
        interactions = min(max(int(frame.get("interactions", 0)), 0), 1000000)
        return interactive + occupancy * 10 + min(visits // 10, 50) + min(interactions, 100)

    def refresh_catalogue(self):
        return self.observe({"event": "refresh_catalogue"})

    def _run(self):
        while True:
            unused_priority, unused_sequence, frame = self.queue.get()
            if frame is None: return
            try:
                if frame.get("event") == "refresh_catalogue":
                    self.provider.refresh_models()
                else:
                    prompt = json.dumps(frame, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
                    if len(prompt) > 8192:
                        raise ValueError("advisory frame is too large")
                    response = self.provider.complete([
                        {"role": "system", "content": "Choose only an offered candidate. Return JSON: {\"choice\":0}."},
                        {"role": "user", "content": prompt}
                    ], max_tokens=16)
                    if response is not None:
                        parsed = json.loads(response)
                        if parsed != {"choice": 0}:
                            raise ValueError("invalid advisory choice")
            except Exception:
                with self.lock: self.invalid_responses += 1
            with self.lock: self.completed += 1

    def status_snapshot(self):
        with self.lock:
            return {
                "queued": self.queue.qsize(),
                "submitted": self.submitted,
                "dropped": self.dropped,
                "completed": self.completed,
                "invalid_responses": self.invalid_responses,
                "workers": len(self.workers),
                "workers_alive": sum(
                    worker.is_alive() for worker in self.workers
                ),
                "closed": self.closed
            }

    def shutdown(self, timeout=1.0):
        with self.lock:
            if self.closed: return True
            self.closed = True
        with self.queue.mutex:
            self.queue.queue.clear()
            self.queue.not_empty.notify_all()
        with self.lock:
            self.dropped += self.queue.qsize()
        for unused in self.workers:
            try:
                with self.lock:
                    self.sequence += 1
                    item = (float("-inf"), self.sequence, None)
                self.queue.put_nowait(item)
            except queue.Full:
                return False
        deadline = time.monotonic() + max(0.0, timeout)
        for worker in self.workers:
            worker.join(max(0.0, deadline - time.monotonic()))
        return all(not worker.is_alive() for worker in self.workers)
