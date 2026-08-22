import json

from items.pimp_hat import PimpHat
from items.possum_token import RoyalPossumBottleCap


PLAYER_STATE_VERSION = 1
MAX_PLAYER_STATE_BYTES = 65536
MAX_INVENTORY_ITEMS = 100
MAX_EQUIPMENT_SLOTS = 32
MIN_FABULOUSNESS = -10000
MAX_FABULOUSNESS = 10000

ITEM_FACTORIES = {
    "pimp_hat": PimpHat,
    "royal_possum_bottle_cap": RoyalPossumBottleCap
}

ITEM_TEMPLATE_IDS = {
    PimpHat: "pimp_hat",
    RoyalPossumBottleCap: "royal_possum_bottle_cap"
}


class PlayerStateError(ValueError):
    """Raised when character state cannot be safely saved or restored."""


def _default_document():
    return {
        "version": PLAYER_STATE_VERSION,
        "room_id": None,
        "stats": {
            "fabulousness": 0
        },
        "inventory": [],
        "equipment": {}
    }


def new_player_state_json():
    return _encode_document(_default_document())


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


def serialize_player_state(player):
    inventory = []
    inventory_indexes = {}

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
            "fabulousness": _validated_fabulousness(player.fabulousness)
        },
        "inventory": inventory,
        "equipment": equipment
    }

    return _encode_document(document)


def _decode_document(encoded_state):
    if not isinstance(encoded_state, str):
        raise PlayerStateError("player state must be JSON text")

    _validated_encoded_size(encoded_state)

    try:
        document = json.loads(encoded_state)
    except (TypeError, ValueError, RuntimeError):
        raise PlayerStateError("player state contains invalid JSON")

    if document == {}:
        return _default_document()

    if not isinstance(document, dict):
        raise PlayerStateError("player state must be an object")

    version = document.get("version")

    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != PLAYER_STATE_VERSION
    ):
        raise PlayerStateError("unsupported player state version")

    return document


def restore_player_state(player, encoded_state, world):
    document = _decode_document(encoded_state)
    stats = document.get("stats")
    inventory_data = document.get("inventory")
    equipment_data = document.get("equipment")
    room_id = document.get("room_id")

    if not isinstance(stats, dict):
        raise PlayerStateError("player stats must be an object")

    fabulousness = _validated_fabulousness(stats.get("fabulousness"))

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

    return room
