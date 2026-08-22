"""Strict, versioned persistence for bounded shared village state."""

import json
import math

from village_state import VillageState


WORLD_STATE_VERSION = 1
MAX_WORLD_STATE_BYTES = 4096
MAX_WORLD_TIMESTAMP = 32503680000.0


class WorldStateError(ValueError):
    pass


def _bounded_integer(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorldStateError("{0} must be an integer".format(label))

    if value < minimum or value > maximum:
        raise WorldStateError("{0} is outside its allowed range".format(label))

    return value


def _bounded_timestamp(value):
    if value is None:
        return None

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or value > MAX_WORLD_TIMESTAMP
    ):
        raise WorldStateError("wisp absence timestamp is invalid")

    return float(value)


def _validated_document(encoded_state):
    if not isinstance(encoded_state, str):
        raise WorldStateError("world state must be text")

    try:
        encoded_size = len(encoded_state.encode("utf-8"))
    except UnicodeError:
        raise WorldStateError("world state contains invalid text")

    if encoded_size > MAX_WORLD_STATE_BYTES:
        raise WorldStateError("world state is too large")

    try:
        document = json.loads(encoded_state)
    except (TypeError, ValueError):
        raise WorldStateError("world state is not valid JSON")

    if not isinstance(document, dict):
        raise WorldStateError("world state must be an object")

    if set(document) != set(("version", "village")):
        raise WorldStateError("world state has unknown or missing fields")

    if (
        isinstance(document["version"], bool)
        or not isinstance(document["version"], int)
        or document["version"] != WORLD_STATE_VERSION
    ):
        raise WorldStateError("unsupported world state version")

    village = document["village"]

    if not isinstance(village, dict) or set(village) != set((
        "acorn_danger",
        "acorn_supply",
        "acorns_harvested",
        "wisp_warded",
        "wisp_absent_until",
        "wisp_harmed_count"
    )):
        raise WorldStateError("village state has unknown or missing fields")

    danger = _bounded_integer(
        village["acorn_danger"],
        "acorn danger",
        0,
        VillageState.INITIAL_ACORN_DANGER
    )
    supply = _bounded_integer(
        village["acorn_supply"],
        "acorn supply",
        0,
        VillageState.INITIAL_ACORN_SUPPLY
    )
    harvested = _bounded_integer(
        village["acorns_harvested"],
        "harvested acorns",
        0,
        VillageState.INITIAL_ACORN_SUPPLY
    )

    if supply + harvested != VillageState.INITIAL_ACORN_SUPPLY:
        raise WorldStateError("acorn supply totals are inconsistent")

    expected_danger = max(0, VillageState.INITIAL_ACORN_DANGER - harvested)

    if danger != expected_danger:
        raise WorldStateError("acorn danger is inconsistent with harvests")

    warded = village["wisp_warded"]

    if not isinstance(warded, bool):
        raise WorldStateError("wisp ward state must be true or false")

    absent_until = _bounded_timestamp(village["wisp_absent_until"])

    if absent_until is not None and warded:
        raise WorldStateError("an absent wisp cannot also be warded")

    harmed_count = _bounded_integer(
        village["wisp_harmed_count"],
        "wisp harm count",
        0,
        VillageState.MAX_WISP_HARM_COUNT
    )

    return {
        "acorn_danger": danger,
        "acorn_supply": supply,
        "acorns_harvested": harvested,
        "wisp_warded": warded,
        "wisp_absent_until": absent_until,
        "wisp_harmed_count": harmed_count
    }


def serialize_world_state(village_state):
    snapshot = village_state.persistence_snapshot()
    document = {
        "version": WORLD_STATE_VERSION,
        "village": snapshot
    }
    encoded_state = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":")
    )

    # Validate the serializer too, so corrupted in-memory state is never
    # silently written as the new durable baseline.
    _validated_document(encoded_state)
    return encoded_state


def restore_world_state(village_state, encoded_state):
    snapshot = _validated_document(encoded_state)
    village_state.restore_persistence_snapshot(snapshot)
    return snapshot


def new_world_state_json():
    return serialize_world_state(VillageState())


def validate_world_state_json(encoded_state):
    _validated_document(encoded_state)
    return encoded_state
