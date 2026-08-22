import json
import math
import time

from core import (
    DEFAULT_MAX_HEALTH,
    MAX_HEALTH,
    MAX_INTOXICATION,
    MAX_STATUS_TIMESTAMP,
    PLAYER_INVENTORY_LIMIT
)
from items.pimp_hat import PimpHat
from items.possum_token import RoyalPossumBottleCap
from items.giant_acorn import GiantAcorn
from items.drinks import HornBornSpecial, ValHealingPotion, ValkyrieMead


PLAYER_STATE_VERSION = 2
MAX_PLAYER_STATE_BYTES = 65536
MAX_INVENTORY_ITEMS = PLAYER_INVENTORY_LIMIT
MAX_EQUIPMENT_SLOTS = 32
MIN_FABULOUSNESS = -10000
MAX_FABULOUSNESS = 10000

ITEM_FACTORIES = {
    "pimp_hat": PimpHat,
    "royal_possum_bottle_cap": RoyalPossumBottleCap,
    "giant_acorn": GiantAcorn,
    "val_healing_potion": ValHealingPotion,
    "valkyrie_mead": ValkyrieMead,
    "horn_born_special": HornBornSpecial
}

ITEM_TEMPLATE_IDS = {
    PimpHat: "pimp_hat",
    RoyalPossumBottleCap: "royal_possum_bottle_cap",
    GiantAcorn: "giant_acorn",
    ValHealingPotion: "val_healing_potion",
    ValkyrieMead: "valkyrie_mead",
    HornBornSpecial: "horn_born_special"
}


class PlayerStateError(ValueError):
    """Raised when character state cannot be safely saved or restored."""


def _current_timestamp(time_source=None):
    source = time_source or time.time
    return _validated_timestamp("status update timestamp", source())


def _default_document(time_source=None):
    return {
        "version": PLAYER_STATE_VERSION,
        "room_id": None,
        "stats": {
            "fabulousness": 0,
            "max_health": DEFAULT_MAX_HEALTH,
            "health": DEFAULT_MAX_HEALTH,
            "intoxication": 0
        },
        "inventory": [],
        "equipment": {},
        "status": {
            "recently_respawned": False,
            "last_status_update": _current_timestamp(time_source)
        }
    }


def new_player_state_json(time_source=None):
    return _encode_document(_default_document(time_source))


def _encode_document(document):
    encoded = json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True
    )

    if len(encoded.encode("utf-8")) > MAX_PLAYER_STATE_BYTES:
        raise PlayerStateError("player state is too large")

    return encoded


def _validated_encoded_size(encoded_state):
    if len(encoded_state) > MAX_PLAYER_STATE_BYTES:
        raise PlayerStateError("player state is too large")

    try:
        encoded_size = len(encoded_state.encode("utf-8"))
    except UnicodeError:
        raise PlayerStateError("player state contains invalid text")

    if encoded_size > MAX_PLAYER_STATE_BYTES:
        raise PlayerStateError("player state is too large")


def _validated_fabulousness(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlayerStateError("fabulousness must be an integer")

    if value < MIN_FABULOUSNESS or value > MAX_FABULOUSNESS:
        raise PlayerStateError("fabulousness is outside the supported range")

    return value


def _validated_integer(name, value, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlayerStateError("{0} must be an integer".format(name))

    if value < minimum or value > maximum:
        raise PlayerStateError(
            "{0} is outside the supported range".format(name)
        )

    return value


def _validated_timestamp(name, value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        or value > MAX_STATUS_TIMESTAMP
    ):
        raise PlayerStateError("{0} is invalid".format(name))

    return float(value)


def serialize_player_state(player):
    inventory = []
    inventory_indexes = {}
    max_health = _validated_integer(
        "max health",
        player.max_health,
        1,
        MAX_HEALTH
    )
    health = _validated_integer(
        "health",
        player.health,
        0,
        max_health
    )
    intoxication = _validated_integer(
        "intoxication",
        player.intoxication,
        0,
        MAX_INTOXICATION
    )
    recently_respawned = player.recently_respawned

    if not isinstance(recently_respawned, bool):
        raise PlayerStateError("recent respawn state must be true or false")

    last_status_update = _validated_timestamp(
        "status update timestamp",
        player.last_status_update
    )

    if len(player.inventory) > MAX_INVENTORY_ITEMS:
        raise PlayerStateError("inventory contains too many items")

    for index, item in enumerate(player.inventory):
        object_key = id(item)

        if object_key in inventory_indexes:
            raise PlayerStateError("inventory contains the same object twice")

        template_id = ITEM_TEMPLATE_IDS.get(type(item))

        if template_id is None:
            raise PlayerStateError(
                "inventory contains an unsupported item template"
            )

        inventory_indexes[object_key] = index
        inventory.append({"template": template_id})

    equipment = {}

    for slot, item in player.equipment.items():
        index = inventory_indexes.get(id(item))

        if index is None:
            raise PlayerStateError("equipped item is not in inventory")

        if not item.wearable or item.worn_where != slot:
            raise PlayerStateError("equipped item does not match its slot")

        equipment[slot] = index

    room_id = None

    if player.room is not None:
        room_id = player.room.room_id

    document = {
        "version": PLAYER_STATE_VERSION,
        "room_id": room_id,
        "stats": {
            "fabulousness": _validated_fabulousness(player.fabulousness),
            "max_health": max_health,
            "health": health,
            "intoxication": intoxication
        },
        "inventory": inventory,
        "equipment": equipment,
        "status": {
            "recently_respawned": recently_respawned,
            "last_status_update": last_status_update
        }
    }

    return _encode_document(document)


def _migrate_version_one(document, now):
    stats = document.get("stats")

    if isinstance(stats, dict):
        stats = {
            "fabulousness": stats.get("fabulousness"),
            "max_health": stats.get("max_health", DEFAULT_MAX_HEALTH),
            "health": stats.get(
                "health",
                stats.get("max_health", DEFAULT_MAX_HEALTH)
            ),
            "intoxication": stats.get("intoxication", 0)
        }

    return {
        "version": PLAYER_STATE_VERSION,
        "room_id": document.get("room_id"),
        "stats": stats,
        "inventory": document.get("inventory"),
        "equipment": document.get("equipment"),
        "status": {
            "recently_respawned": False,
            "last_status_update": now
        }
    }


def _decode_document(encoded_state, time_source=None):
    if not isinstance(encoded_state, str):
        raise PlayerStateError("player state must be JSON text")

    _validated_encoded_size(encoded_state)

    try:
        document = json.loads(encoded_state)
    except (TypeError, ValueError, RuntimeError):
        raise PlayerStateError("player state contains invalid JSON")

    if document == {}:
        return _default_document(time_source)

    if not isinstance(document, dict):
        raise PlayerStateError("player state must be an object")

    version = document.get("version")

    if isinstance(version, bool) or not isinstance(version, int):
        raise PlayerStateError("unsupported player state version")

    now = _current_timestamp(time_source)

    if version == 1:
        document = _migrate_version_one(document, now)
    elif version != PLAYER_STATE_VERSION:
        raise PlayerStateError("unsupported player state version")

    if set(document) != set((
        "version",
        "room_id",
        "stats",
        "inventory",
        "equipment",
        "status"
    )):
        raise PlayerStateError("player state has unknown or missing fields")

    return document


def restore_player_state(player, encoded_state, world, time_source=None):
    document = _decode_document(encoded_state, time_source=time_source)
    stats = document.get("stats")
    inventory_data = document.get("inventory")
    equipment_data = document.get("equipment")
    room_id = document.get("room_id")
    status = document.get("status")

    if not isinstance(stats, dict):
        raise PlayerStateError("player stats must be an object")

    if set(stats) != set((
        "fabulousness",
        "max_health",
        "health",
        "intoxication"
    )):
        raise PlayerStateError("player stats have unknown or missing fields")

    fabulousness = _validated_fabulousness(stats.get("fabulousness"))
    max_health = _validated_integer(
        "max health",
        stats.get("max_health", DEFAULT_MAX_HEALTH),
        1,
        MAX_HEALTH
    )
    health = _validated_integer(
        "health",
        stats.get("health", max_health),
        0,
        max_health
    )
    intoxication = _validated_integer(
        "intoxication",
        stats.get("intoxication", 0),
        0,
        MAX_INTOXICATION
    )

    if not isinstance(status, dict) or set(status) != set((
        "recently_respawned",
        "last_status_update"
    )):
        raise PlayerStateError("player status has unknown or missing fields")

    recently_respawned = status["recently_respawned"]

    if not isinstance(recently_respawned, bool):
        raise PlayerStateError("recent respawn state must be true or false")

    last_status_update = _validated_timestamp(
        "status update timestamp",
        status["last_status_update"]
    )
    now = _current_timestamp(time_source)
    elapsed_seconds = max(0.0, now - last_status_update)
    intoxication = max(0, intoxication - int(elapsed_seconds // 60.0))
    current_status_update = max(last_status_update, now)

    if not isinstance(inventory_data, list):
        raise PlayerStateError("player inventory must be a list")

    if len(inventory_data) > MAX_INVENTORY_ITEMS:
        raise PlayerStateError("inventory contains too many items")

    inventory = []

    for item_data in inventory_data:
        if not isinstance(item_data, dict):
            raise PlayerStateError("inventory entry must be an object")

        if set(item_data.keys()) != set(("template",)):
            raise PlayerStateError("inventory entry has unsupported fields")

        factory = ITEM_FACTORIES.get(item_data.get("template"))

        if factory is None:
            raise PlayerStateError("inventory uses an unknown item template")

        inventory.append(factory())

    if not isinstance(equipment_data, dict):
        raise PlayerStateError("player equipment must be an object")

    if len(equipment_data) > MAX_EQUIPMENT_SLOTS:
        raise PlayerStateError("player has too many equipment slots")

    equipment = {}

    for slot, index in equipment_data.items():
        if not isinstance(slot, str):
            raise PlayerStateError("equipment slot must be text")

        if isinstance(index, bool) or not isinstance(index, int):
            raise PlayerStateError("equipment index must be an integer")

        if index < 0 or index >= len(inventory):
            raise PlayerStateError("equipment index is outside inventory")

        item = inventory[index]

        if not item.wearable or item.worn_where != slot:
            raise PlayerStateError("equipped item does not match its slot")

        equipment[slot] = item

    if room_id is not None and not isinstance(room_id, str):
        raise PlayerStateError("room ID must be text or null")

    room = world.rooms.get(room_id)

    if room is None:
        room = world.starting_room

    player.inventory = inventory
    player.equipment = equipment
    player.fabulousness = fabulousness
    player.max_health = max_health
    player.health = health
    player.intoxication = intoxication
    player.recently_respawned = recently_respawned
    player.last_status_update = current_status_update

    return room
