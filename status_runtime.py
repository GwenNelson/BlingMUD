"""Small, non-blocking coordinator for elapsed player status effects."""

import time


STATUS_INTERVAL_SECONDS = 60.0


class StatusCoordinator(object):
    """Ask active sessions to apply whole-minute status decay."""

    def __init__(self, sessions_function, time_source=None):
        if not callable(sessions_function):
            raise TypeError("sessions_function must be callable")

        self.sessions_function = sessions_function
        self.time_source = time_source or time.monotonic
        self.runs = 0
        self.updated = 0
        self.busy = 0

    def tick(self, now=None):
        if now is None:
            now = self.time_source()

        self.runs += 1

        for session in self.sessions_function():
            result = session.decay_online_status(now=now, wait=False)

            if result == "busy":
                self.busy += 1
            elif result:
                self.updated += 1

        return True

    def status_snapshot(self):
        return {
            "runs": self.runs,
            "updated": self.updated,
            "busy": self.busy
        }
