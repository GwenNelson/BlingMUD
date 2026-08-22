"""Bounded, discard-safe background advisory runtime for NPC AI."""

import queue
import threading


class NPCAdvisorRuntime(object):
    def __init__(self, provider, workers=1, queued=8):
        if workers < 1 or queued < 0:
            raise ValueError("invalid advisor runtime bounds")
        self.provider = provider
        self.queue = queue.Queue(maxsize=queued)
        self.closed = False
        self.lock = threading.RLock()
        self.submitted = 0
        self.dropped = 0
        self.completed = 0
        self.worker = threading.Thread(target=self._run, name="blingmud-npc-ai", daemon=True)
        self.worker.start()

    def observe(self, frame):
        if not isinstance(frame, dict) or len(frame) > 8:
            raise ValueError("invalid advisory frame")
        with self.lock:
            if self.closed:
                self.dropped += 1
                return False
        try:
            self.queue.put_nowait(frame)
        except queue.Full:
            with self.lock: self.dropped += 1
            return False
        with self.lock: self.submitted += 1
        return True

    def _run(self):
        while True:
            frame = self.queue.get()
            if frame is None: return
            # This initial advisory endpoint deliberately submits no player
            # text and cannot alter FSM output. Provider failure is inert.
            try:
                self.provider.complete([{"role": "system", "content": "Return {}"}], max_tokens=8)
            except Exception:
                pass
            with self.lock: self.completed += 1

    def status_snapshot(self):
        with self.lock:
            return {"queued": self.queue.qsize(), "submitted": self.submitted, "dropped": self.dropped, "completed": self.completed, "closed": self.closed}

    def shutdown(self, timeout=1.0):
        with self.lock:
            if self.closed: return True
            self.closed = True
        try:
            self.queue.put(None, timeout=max(0.0, timeout / 2.0))
        except queue.Full:
            return False
        self.worker.join(max(0.0, timeout / 2.0))
        return not self.worker.is_alive()
