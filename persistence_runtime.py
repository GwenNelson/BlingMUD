"""Bounded asynchronous persistence and periodic autosave coordination."""

import collections
import threading
import time


AUTOSAVE_INTERVAL_SECONDS = 60.0
PERSISTENCE_PENDING_KEY_LIMIT = 64
GRACEFUL_FLUSH_SECONDS = 10.0


class SaveReceipt(object):
    """Waitable result for a requested durable write."""

    def __init__(self):
        self.event = threading.Event()
        self.success = None
        self.error = None

    def complete(self, success, error=None):
        self.success = bool(success)
        self.error = error
        self.event.set()

    def wait(self, timeout=None):
        if not self.event.wait(timeout):
            return False

        return bool(self.success)


class PendingSave(object):
    def __init__(self, encoded_state):
        self.encoded_state = encoded_state
        self.completions = []


class PersistenceWriter(object):
    """One coalescing writer with a finite number of pending players."""

    def __init__(
        self,
        save_function,
        pending_key_limit=PERSISTENCE_PENDING_KEY_LIMIT
    ):
        if not callable(save_function):
            raise TypeError("save_function must be callable")

        if pending_key_limit <= 0:
            raise ValueError("pending_key_limit must be positive")

        self.save_function = save_function
        self.pending_key_limit = pending_key_limit
        self.condition = threading.Condition(threading.RLock())
        self.pending = collections.OrderedDict()
        self.in_flight = False
        self.closing = False
        self.started = False
        self.thread = None
        self.completed_writes = 0
        self.failed_writes = 0
        self.last_error = None

    def start(self):
        with self.condition:
            if self.started:
                return False

            if self.closing:
                raise RuntimeError("closed persistence writer cannot start")

            self.started = True
            self.thread = threading.Thread(
                target=self._run,
                name="blingmud-persistence",
                daemon=True
            )
            self.thread.start()
            return True

    def submit(self, username, encoded_state, completion=None):
        if not isinstance(username, str) or not username:
            raise ValueError("username must be non-empty text")

        if not isinstance(encoded_state, str):
            raise TypeError("encoded_state must be text")

        receipt = SaveReceipt()
        key = username.lower()

        with self.condition:
            if not self.started or self.closing:
                receipt.complete(
                    False,
                    RuntimeError("writer is not accepting saves")
                )
                return receipt

            pending_save = self.pending.get(key)

            if pending_save is None:
                if len(self.pending) >= self.pending_key_limit:
                    receipt.complete(
                        False,
                        RuntimeError("persistence queue is full")
                    )
                    return receipt

                pending_save = PendingSave(encoded_state)
                self.pending[key] = pending_save
            else:
                pending_save.encoded_state = encoded_state
                self.pending.move_to_end(key)

            pending_save.completions.append(
                (receipt, completion, encoded_state)
            )
            self.condition.notify_all()

        return receipt

    def _run(self):
        while True:
            with self.condition:
                while not self.pending and not self.closing:
                    self.condition.wait()

                if not self.pending and self.closing:
                    self.condition.notify_all()
                    return

                username, pending_save = self.pending.popitem(last=False)
                self.in_flight = True

            error = None

            try:
                self.save_function(username, pending_save.encoded_state)
            except Exception as caught_error:
                error = caught_error

            success = error is None

            with self.condition:
                if success:
                    self.completed_writes += 1
                else:
                    self.failed_writes += 1
                    self.last_error = error

                self.in_flight = False
                self.condition.notify_all()

            for receipt, completion, requested_state in (
                pending_save.completions
            ):
                receipt.complete(success, error)

                if completion is not None:
                    try:
                        completion(success, error, requested_state)
                    except Exception:
                        # Persistence has already completed. A bookkeeping
                        # callback must not kill the only writer.
                        pass

    def flush(self, timeout=GRACEFUL_FLUSH_SECONDS):
        deadline = time.monotonic() + max(0.0, float(timeout))

        with self.condition:
            while self.pending or self.in_flight:
                remaining = deadline - time.monotonic()

                if remaining <= 0:
                    return False

                self.condition.wait(remaining)

            return True

    def shutdown(self, timeout=GRACEFUL_FLUSH_SECONDS):
        with self.condition:
            if self.closing:
                thread = self.thread
            else:
                self.closing = True
                self.condition.notify_all()
                thread = self.thread

        if thread is None:
            return True

        thread.join(max(0.0, float(timeout)))
        return not thread.is_alive()

    def status_snapshot(self):
        with self.condition:
            return {
                "started": self.started,
                "closing": self.closing,
                "pending": len(self.pending),
                "in_flight": self.in_flight,
                "completed_writes": self.completed_writes,
                "failed_writes": self.failed_writes,
                "last_error": None if self.last_error is None else str(
                    self.last_error
                )
            }


class AutosaveCoordinator(object):
    """Serialize active sessions every minute and queue changed snapshots."""

    def __init__(
        self,
        sessions_function,
        interval=AUTOSAVE_INTERVAL_SECONDS,
        time_source=None
    ):
        if not callable(sessions_function):
            raise TypeError("sessions_function must be callable")

        if interval <= 0:
            raise ValueError("autosave interval must be positive")

        self.sessions_function = sessions_function
        self.interval = float(interval)
        self.time_source = time_source or time.monotonic
        self.next_run_at = self.time_source() + self.interval
        self.last_run_at = None
        self.runs = 0
        self.queued = 0
        self.unchanged = 0
        self.busy = 0
        self.failed = 0

    def tick(self, now=None, force=False):
        if now is None:
            now = self.time_source()

        if not force and now < self.next_run_at:
            return False

        self.last_run_at = now
        self.next_run_at = now + self.interval
        self.runs += 1

        for session in self.sessions_function():
            result = session.save_if_changed(wait=False)

            if result == "queued":
                self.queued += 1
            elif result == "unchanged":
                self.unchanged += 1
            elif result == "busy":
                self.busy += 1
            else:
                self.failed += 1

        return True

    def status_snapshot(self):
        return {
            "interval": self.interval,
            "next_run_at": self.next_run_at,
            "last_run_at": self.last_run_at,
            "runs": self.runs,
            "queued": self.queued,
            "unchanged": self.unchanged,
            "busy": self.busy,
            "failed": self.failed
        }
