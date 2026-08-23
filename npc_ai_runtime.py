"""Bounded, discard-safe background advisory runtime for NPC AI."""

import queue
import threading
import json
import heapq
import time
from collections import deque

from operational_log import log_event


class NPCAdvisorRuntime(object):
    supports_callbacks = True
    def __init__(
        self, provider, workers=2, queued=16, time_source=None,
        global_limit=120, npc_limit=30, room_limit=60
    ):
        if workers < 1 or workers > 4 or queued < 1 or queued > 64:
            raise ValueError("invalid advisor runtime bounds")
        if not all(
            isinstance(value, int) and value > 0
            for value in (global_limit, npc_limit, room_limit)
        ):
            raise ValueError("invalid advisory budget bounds")
        self.provider = provider
        self.time_source = time_source or time.monotonic
        self.global_limit = global_limit
        self.npc_limit = npc_limit
        self.room_limit = room_limit
        self.global_requests = deque()
        self.npc_requests = {}
        self.room_requests = {}
        self.budget_rejections = 0
        self.last_catalogue_request = None
        self.queue = queue.PriorityQueue(maxsize=queued)
        self.closed = False
        self.enabled = True
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

    def observe(self, frame, result_handler=None):
        if not isinstance(frame, dict) or len(frame) > 8:
            raise ValueError("invalid advisory frame")
        with self.lock:
            if self.closed or (
                not self.enabled and frame.get("event") != "refresh_catalogue"
            ):
                self.dropped += 1
                return False
            if not self._budget_available(frame):
                self.budget_rejections += 1
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
                item = (
                    -self.priority_score(frame),
                    self.sequence,
                    frame,
                    result_handler
                )
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

    def set_enabled(self, enabled):
        with self.lock:
            if self.closed and enabled:
                return False
            self.enabled = bool(enabled)
            return self.enabled

    def clear_circuit(self):
        clearer = getattr(self.provider, "clear_circuit", None)
        if clearer is not None:
            clearer()
        with self.lock:
            self.budget_rejections = 0
            self.last_catalogue_request = None
        return True

    def _budget_available(self, frame):
        now = self.time_source()
        cutoff = now - 3600.0

        while self.global_requests and self.global_requests[0] < cutoff:
            self.global_requests.popleft()

        npc = str(frame.get("npc", ""))[:80]
        room = str(frame.get("room", ""))[:80]
        npc_history = self.npc_requests.setdefault(npc, deque())
        room_history = self.room_requests.setdefault(room, deque())
        while npc_history and npc_history[0] < cutoff:
            npc_history.popleft()
        while room_history and room_history[0] < cutoff:
            room_history.popleft()

        if (
            len(self.global_requests) >= self.global_limit
            or len(npc_history) >= self.npc_limit
            or len(room_history) >= self.room_limit
        ):
            return False

        self.global_requests.append(now)
        npc_history.append(now)
        room_history.append(now)
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
        with self.lock:
            self.last_catalogue_request = self.time_source()
        return self.observe({"event": "refresh_catalogue"})

    def maintenance(self):
        with self.lock:
            last_request = self.last_catalogue_request
        now = self.time_source()
        if last_request is None or now - last_request >= 900.0:
            self.refresh_catalogue()

    def _run(self):
        while True:
            try:
                unused_priority, unused_sequence, frame, result_handler = self.queue.get(
                    timeout=0.1
                )
            except queue.Empty:
                with self.lock:
                    if self.closed:
                        return
                continue
            if frame is None:
                return
            try:
                if frame.get("event") == "refresh_catalogue":
                    self.provider.refresh_models()
                    with self.lock:
                        self.last_catalogue_request = self.time_source()
                    log_event("npc_ai.catalogue_refresh", result="success")
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
                        if (
                            not isinstance(parsed, dict)
                            or set(parsed) != {"choice"}
                            or isinstance(parsed["choice"], bool)
                            or not isinstance(parsed["choice"], int)
                            or parsed["choice"] < 0
                            or parsed["choice"] >= len(frame.get("candidates", ()))
                        ):
                            raise ValueError("invalid advisory choice")
                        if result_handler is not None:
                            result_handler(parsed["choice"], frame)
            except Exception:
                with self.lock:
                    self.invalid_responses += 1
                log_event(
                    "npc_ai.advisory_failure",
                    provider_status=getattr(self.provider, "status", "unknown")
                )
            with self.lock: self.completed += 1

    def status_snapshot(self):
        with self.lock:
            return {
                "queued": self.queue.qsize(),
                "submitted": self.submitted,
                "dropped": self.dropped,
                "completed": self.completed,
                "invalid_responses": self.invalid_responses,
                "budget_rejections": self.budget_rejections,
                "budget_global": len(self.global_requests),
                "workers": len(self.workers),
                "workers_alive": sum(
                    worker.is_alive() for worker in self.workers
                ),
                "closed": self.closed
                ,"enabled": self.enabled
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
        deadline = time.monotonic() + max(0.0, timeout)
        for worker in self.workers:
            worker.join(max(0.0, deadline - time.monotonic()))
        return all(not worker.is_alive() for worker in self.workers)
