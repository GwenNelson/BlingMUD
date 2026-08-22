import threading


class VillageState(object):
    """Bounded runtime state shared by the first village locations."""

    INITIAL_ACORN_DANGER = 3
    INITIAL_ACORN_SUPPLY = 12
    WISP_DARK_SECONDS = 1800.0

    def __init__(self):
        self.lock = threading.RLock()
        self.acorn_danger = self.INITIAL_ACORN_DANGER
        self.acorn_supply = self.INITIAL_ACORN_SUPPLY
        self.acorns_harvested = 0
        self.wisp_warded = False
        self.wisp_absent_until = None
        self.wisp_harmed_count = 0

    def tree_snapshot(self):
        with self.lock:
            return {
                "danger": self.acorn_danger,
                "supply": self.acorn_supply,
                "harvested": self.acorns_harvested
            }

    def harvest_acorn(self):
        with self.lock:
            if self.acorn_supply <= 0:
                return None

            self.acorn_supply -= 1
            self.acorns_harvested += 1
            self.acorn_danger = max(0, self.acorn_danger - 1)
            return {
                "danger": self.acorn_danger,
                "supply": self.acorn_supply,
                "harvested": self.acorns_harvested
            }

    def refresh_wisp(self, now):
        with self.lock:
            if self.wisp_absent_until is None:
                return False

            if now < self.wisp_absent_until:
                return False

            self.wisp_absent_until = None
            self.wisp_warded = False
            return True

    def wisp_is_present(self):
        with self.lock:
            return self.wisp_absent_until is None

    def protect_wisp(self):
        with self.lock:
            if self.wisp_absent_until is not None:
                return "absent"

            if self.wisp_warded:
                return "already_warded"

            self.wisp_warded = True
            return "warded"

    def attack_wisp(self, now):
        with self.lock:
            if self.wisp_absent_until is not None:
                return "absent"

            if self.wisp_warded:
                self.wisp_warded = False
                return "ward_broken"

            self.wisp_absent_until = now + self.WISP_DARK_SECONDS
            self.wisp_harmed_count += 1
            return "removed"

    def wisp_snapshot(self):
        with self.lock:
            return {
                "present": self.wisp_absent_until is None,
                "warded": self.wisp_warded,
                "absent_until": self.wisp_absent_until,
                "harmed_count": self.wisp_harmed_count
            }
