"""Bounded JSON-lines operational events with conservative redaction."""

import json
import math
import os
import re
import sys
import threading
import time
import unicodedata


MAX_EVENT_LENGTH = 64
MAX_FIELDS = 16
MAX_FIELD_LENGTH = 160
MAX_LOG_LINE_BYTES = 4096
EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
FIELD_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
RESERVED_FIELDS = frozenset(("event", "thread", "time"))
SECRET_MARKERS = (
    "api_key",
    "authorization",
    "cookie",
    "hash",
    "password",
    "passwd",
    "prompt",
    "secret",
    "token"
)


def _safe_text(value):
    result = []

    for character in str(value):
        if unicodedata.category(character) in ("Cc", "Cf", "Cs"):
            result.append("?")
        else:
            result.append(character)

        if len(result) >= MAX_FIELD_LENGTH:
            break

    return "".join(result)


def _safe_value(key, value):
    if any(marker in key for marker in SECRET_MARKERS):
        return "[redacted]"

    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else "non-finite"

    return _safe_text(value)


class OperationalLogger(object):
    def __init__(self, sink=None, time_source=None, enabled=True):
        self.sink = sink
        self.time_source = time_source or time.time
        self.enabled = bool(enabled)
        self.lock = threading.RLock()

    def emit(self, event, **fields):
        try:
            if not self.enabled:
                return False

            if (
                not isinstance(event, str)
                or len(event) > MAX_EVENT_LENGTH
                or EVENT_PATTERN.fullmatch(event) is None
            ):
                return False

            timestamp = float(self.time_source())

            if not math.isfinite(timestamp):
                return False

            document = {
                "event": event,
                "time": timestamp,
                "thread": _safe_text(threading.current_thread().name)
            }

            safe_keys = sorted(
                key
                for key in fields
                if (
                    isinstance(key, str)
                    and FIELD_PATTERN.fullmatch(key) is not None
                    and key not in RESERVED_FIELDS
                )
            )

            for key in safe_keys[:MAX_FIELDS]:
                document[key] = _safe_value(key, fields[key])

            encoded = json.dumps(
                document,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True
            )

            if len(encoded.encode("utf-8")) > MAX_LOG_LINE_BYTES:
                return False

            with self.lock:
                sink = self.sink or sys.stderr
                sink.write(encoded + "\n")
                sink.flush()

            return True
        except Exception:
            # Logging must never become a gameplay or shutdown failure mode.
            return False

    def exception(self, event, error, **fields):
        fields["error_type"] = type(error).__name__
        return self.emit(event, **fields)


OPS_LOG = OperationalLogger(
    enabled=os.environ.get("BLINGMUD_SUPPRESS_OPERATIONAL_LOG") != "1"
)


def log_event(event, **fields):
    return OPS_LOG.emit(event, **fields)


def log_exception(event, error, **fields):
    return OPS_LOG.exception(event, error, **fields)
