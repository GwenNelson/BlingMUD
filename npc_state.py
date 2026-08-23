"""Strict, bounded snapshots for the small set of persistent NPC brains."""

import json
import math
import threading
import time


NPC_STATE_VERSION = 1
MAX_NPC_STATE_BYTES = 16384
NPC_IDS = frozenset(("brave_sir_knight", "val"))


class NPCStateError(ValueError):
    pass


def _finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_memory(memory):
    if not isinstance(memory, dict) or len(memory) > 64:
        raise NPCStateError("invalid NPC memory")
    result = {}
    for key, value in memory.items():
        if not isinstance(key, str) or not key or len(key) > 64:
            raise NPCStateError("invalid NPC memory key")
        if not isinstance(value, dict) or set(value) != {
            "name", "visits", "present", "last_entered", "last_left"
        }:
            raise NPCStateError("invalid NPC memory entry")
        if (
            not isinstance(value["name"], str) or len(value["name"]) > 21
            or isinstance(value["visits"], bool)
            or not isinstance(value["visits"], int)
            or not 0 <= value["visits"] <= 1000000
            or not isinstance(value["present"], bool)
        ):
            raise NPCStateError("invalid NPC memory values")
        for timestamp in (value["last_entered"], value["last_left"]):
            if timestamp is not None and not _finite_number(timestamp):
                raise NPCStateError("invalid NPC memory timestamp")
        result[key] = dict(value)
    return result


def validate_npc_state(document):
    if not isinstance(document, dict) or set(document) != {
        "version", "npc_id", "state", "resources", "memory"
    }:
        raise NPCStateError("invalid NPC state keys")
    if document["version"] != NPC_STATE_VERSION:
        raise NPCStateError("unsupported NPC state version")
    if document["npc_id"] not in NPC_IDS:
        raise NPCStateError("unknown NPC state id")
    if not isinstance(document["state"], str) or not document["state"] or len(document["state"]) > 64:
        raise NPCStateError("invalid NPC state name")
    resources = document["resources"]
    if not isinstance(resources, dict) or len(resources) > 16:
        raise NPCStateError("invalid NPC resources")
    for key, value in resources.items():
        if not isinstance(key, str) or len(key) > 64 or not _finite_number(value):
            raise NPCStateError("invalid NPC resource value")
    return {
        "version": 1,
        "npc_id": document["npc_id"],
        "state": document["state"],
        "resources": dict(resources),
        "memory": _validate_memory(document["memory"])
    }


def serialize_npc_state(npc_id, behavior):
    if npc_id not in NPC_IDS or not hasattr(behavior, "persistent_state"):
        raise NPCStateError("NPC does not support persistence")
    document = behavior.persistent_state(npc_id)
    document = validate_npc_state(document)
    encoded = json.dumps(document, ensure_ascii=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_NPC_STATE_BYTES:
        raise NPCStateError("NPC state is too large")
    return encoded


def validate_npc_state_json(encoded):
    if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > MAX_NPC_STATE_BYTES:
        raise NPCStateError("NPC state JSON is too large")
    try:
        document = json.loads(encoded)
    except (TypeError, ValueError, UnicodeError) as error:
        raise NPCStateError("invalid NPC state JSON") from error
    return validate_npc_state(document)


def restore_npc_state(behavior, encoded):
    document = validate_npc_state_json(encoded)
    if not hasattr(behavior, "restore_persistent_state"):
        raise NPCStateError("NPC does not support persistence")
    behavior.restore_persistent_state(document)


class NPCStateSaveCoordinator(object):
    """Dirty-only bounded coordinator for explicitly registered NPC brains."""

    def __init__(self, behaviors, writer, persisted=None, interval=60.0):
        if not isinstance(behaviors, dict) or not behaviors:
            raise ValueError("NPC behaviors must be a non-empty mapping")
        self.behaviors = dict(behaviors)
        self.writer = writer
        self.persisted = {} if persisted is None else dict(persisted)
        self.submitted = dict(self.persisted)
        self.receipts = {}
        self.interval = float(interval)
        self.next_run_at = time.monotonic() + self.interval
        self.lock = threading.RLock()
        self.runs = 0
        self.queued = 0
        self.unchanged = 0
        self.failed = 0
        self.last_error = None

    def _completed(self, success, error, npc_id, encoded):
        with self.lock:
            if success:
                self.persisted[npc_id] = encoded
                self.last_error = None
            else:
                self.last_error = error
                if self.submitted.get(npc_id) == encoded:
                    self.submitted[npc_id] = self.persisted.get(npc_id)

    def save_if_changed(self, wait=False, timeout=10.0):
        results = []
        for npc_id, behavior in self.behaviors.items():
            encoded = serialize_npc_state(npc_id, behavior)
            with self.lock:
                if encoded == self.submitted.get(npc_id):
                    receipt = self.receipts.get(npc_id)
                    if not wait or receipt is None:
                        self.unchanged += 1
                        continue
                else:
                    self.submitted[npc_id] = encoded
                    receipt = self.writer.submit(
                        npc_id,
                        encoded,
                        completion=lambda success, error, key=npc_id, value=encoded: self._completed(
                            success, error, key, value
                        )
                    )
                    self.receipts[npc_id] = receipt
                    self.queued += 1
            results.append(receipt)
        if not wait:
            return "queued" if results else "unchanged"
        deadline = time.monotonic() + max(0.0, timeout)
        for receipt in results:
            if not receipt.wait(max(0.0, deadline - time.monotonic())):
                return "timeout"
            if not receipt.success:
                self.failed += 1
                return "failed"
        return "saved"

    def tick(self, now=None, force=False):
        now = time.monotonic() if now is None else now
        if not force and now < self.next_run_at:
            return False
        self.next_run_at = now + self.interval
        self.runs += 1
        self.save_if_changed()
        return True

    def status_snapshot(self):
        with self.lock:
            return {
                "interval": self.interval,
                "next_run_at": self.next_run_at,
                "runs": self.runs,
                "queued": self.queued,
                "unchanged": self.unchanged,
                "failed": self.failed,
                "last_error": None if self.last_error is None else type(self.last_error).__name__
            }
