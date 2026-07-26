#!/usr/bin/env python3
#
# BLINGMUD
#
# Deliberately simple threaded Telnet MUD server.
# Compatible with Python 3.0-era syntax: no f-strings, dataclasses,
# asyncio, type annotations, or other modern frippery.
#

import hashlib
import socketserver
import threading
import traceback


HOST = "0.0.0.0"
PORT = 4000

# Temporary in-memory user database.
# Everything disappears whenever the server restarts.
#
# username_lower: {
#     "name": original_display_name,
#     "password": SHA-256 password hash
# }
USERS = {}

# Active sessions, indexed by lowercase username.
SESSIONS = {}

USERS_LOCK = threading.RLock()
SESSIONS_LOCK = threading.RLock()


def password_hash(password):
    """Return a simple password hash.

    This is adequate only for the deliberately temporary prototype.
    Use a proper slow password hash before adding persistent accounts.
    """
    encoded = password.encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def strip_telnet_control_codes(data):
    """Remove basic Telnet negotiation bytes.

    This is not a complete Telnet implementation. It is enough to prevent
    common IAC negotiation sequences from appearing as player input.
    """
    output = bytearray()
    position = 0

    while position < len(data):
        byte = data[position]

        # IAC
        if byte == 255:
            if position + 1 >= len(data):
                break

            command = data[position + 1]

            # WILL, WONT, DO, DONT followed by an option byte.
            if command in (251, 252, 253, 254):
                position += 3
                continue

            # Escaped 255.
            if command == 255:
                output.append(255)
                position += 2
                continue

            position += 2
            continue

        output.append(byte)
        position += 1

    return bytes(output)


class Entity(object):
    """Base class for things which can exist in the world."""

    def __init__(self, name, description=""):
        self.name = name
        self.description = description

    def look(self, viewer):
        if self.description:
            return self.description
        return "You see nothing remarkable about {0}.".format(self.name)


class Item(Entity):
    """An object which may be carried or equipped."""

    def __init__(self, name, description="", wearable=False):
        Entity.__init__(self, name, description)
        self.wearable = wearable

    def on_equip(self, player):
        pass

    def on_unequip(self, player):
        pass


class PimpHat(Item):
    def __init__(self):
        Item.__init__(
            self,
            "pimp hat",
            "An enormous and excessively fabulous pimp hat.",
            wearable=True
        )

    def on_equip(self, player):
        player.fabulousness += 10

    def on_unequip(self, player):
        player.fabulousness -= 10


class Room(object):
    """Base class for a location.

    Rooms are code, so subclasses may add arbitrary state and behaviour.
    """

    def __init__(self, room_id, name, description):
        self.room_id = room_id
        self.name = name
        self.description = description
        self.exits = {}
        self.players = []
        self.items = []
        self.lock = threading.RLock()

    def add_exit(self, direction, destination):
        self.exits[direction.lower()] = destination

    def enter(self, player, announce=True):
        with self.lock:
            if player not in self.players:
                self.players.append(player)

        player.room = self

        if announce:
            self.broadcast(
                "* {0} arrives.".format(player.name),
                exclude=player.session
            )

    def leave(self, player, announce=True):
        with self.lock:
            if player in self.players:
                self.players.remove(player)

        if announce:
            self.broadcast(
                "* {0} leaves.".format(player.name),
                exclude=player.session
            )

    def broadcast(self, message, exclude=None):
        with self.lock:
            recipients = list(self.players)

        for player in recipients:
            session = player.session
            if session is not None and session is not exclude:
                session.send(message)

    def describe_to(self, player):
        player.session.send("")
        player.session.send(self.name)
        player.session.send("-" * len(self.name))
        player.session.send(self.description)

        with self.lock:
            other_players = [
                present.name
                for present in self.players
                if present is not player
            ]
            item_names = [item.name for item in self.items]

        if other_players:
            player.session.send(
                "People here: {0}".format(", ".join(other_players))
            )

        if item_names:
            player.session.send(
                "Objects here: {0}".format(", ".join(item_names))
            )

        if self.exits:
            player.session.send(
                "Exits: {0}".format(", ".join(sorted(self.exits.keys())))
            )
        else:
            player.session.send("There are no obvious exits.")

    def on_command(self, session, command, arguments):
        """Allow an individual room to handle custom commands.

        Return True when the room handled the command.
        """
        return False


class FabulousChamber(Room):
    """Example room with custom code and state."""

    def __init__(self):
        Room.__init__(
            self,
            "fabulous_chamber",
            "The Chamber of Immeasurable Fabulousness",
            "Sequins glitter across every surface. The room appears to "
            "have been decorated by someone with unlimited confidence."
        )
        self.number_of_hats_summoned = 0

    def hat_was_summoned(self):
        self.number_of_hats_summoned += 1


class Player(Entity):
    def __init__(self, name):
        Entity.__init__(self, name, "A mysterious adventurer.")
        self.session = None
        self.room = None
        self.inventory = []
        self.equipment = {}
        self.fabulousness = 0

    def find_item(self, name):
        wanted = name.strip().lower()

        for item in self.inventory:
            if item.name.lower() == wanted:
                return item

        return None


class Command(object):
    name = None
    aliases = ()

    def execute(self, session, arguments):
        raise NotImplementedError()


COMMANDS = {}


def register_command(command_class):
    command = command_class()
    names = [command.name]
    names.extend(command.aliases)

    for name in names:
        COMMANDS[name.lower()] = command

    return command_class


@register_command
class HelpCommand(Command):
    name = "help"
    aliases = ("commands",)

    def execute(self, session, arguments):
        session.send("")
        session.send("BLINGMUD commands")
        session.send("-----------------")
        session.send("Anything without a slash is spoken aloud.")
        session.send("")
        session.send("/look")
        session.send("/look <object or person>")
        session.send("/north, /south, /east, /west")
        session.send("/go <direction>")
        session.send("/me <action>")
        session.send("/who")
        session.send("/inventory")
        session.send("/take <object>")
        session.send("/drop <object>")
        session.send("/equip <object>")
        session.send("/stats")
        session.send("/worship <person>")
        session.send("/bling")
        session.send("/quit")


@register_command
class LookCommand(Command):
    name = "look"
    aliases = ("l",)

    def execute(self, session, arguments):
        player = session.player

        if not arguments:
            player.room.describe_to(player)
            return

        target_name = arguments.strip().lower()

        with player.room.lock:
            room_items = list(player.room.items)
            room_players = list(player.room.players)

        for item in player.inventory + room_items:
            if item.name.lower() == target_name:
                session.send(item.look(player))
                return

        for other_player in room_players:
            if other_player.name.lower() == target_name:
                session.send(other_player.look(player))
                return

        session.send("You do not see {0} here.".format(arguments))


@register_command
class GoCommand(Command):
    name = "go"
    aliases = ()

    def execute(self, session, arguments):
        direction = arguments.strip().lower()

        if not direction:
            session.send("Go where?")
            return

        session.move(direction)


class DirectionCommand(Command):
    direction = None

    def execute(self, session, arguments):
        session.move(self.direction)


@register_command
class NorthCommand(DirectionCommand):
    name = "north"
    aliases = ("n",)
    direction = "north"


@register_command
class SouthCommand(DirectionCommand):
    name = "south"
    aliases = ("s",)
    direction = "south"


@register_command
class EastCommand(DirectionCommand):
    name = "east"
    aliases = ("e",)
    direction = "east"


@register_command
class WestCommand(DirectionCommand):
    name = "west"
    aliases = ("w",)
    direction = "west"


@register_command
class EmoteCommand(Command):
    name = "me"
    aliases = ("emote",)

    def execute(self, session, arguments):
        if not arguments:
            session.send("Do what?")
            return

        session.player.room.broadcast(
            "* {0} {1}".format(session.player.name, arguments)
        )


@register_command
class WhoCommand(Command):
    name = "who"
    aliases = ()

    def execute(self, session, arguments):
        with SESSIONS_LOCK:
            names = [
                active_session.player.name
                for active_session in SESSIONS.values()
                if active_session.player is not None
            ]

        names.sort(key=lambda value: value.lower())

        session.send("Online: {0}".format(", ".join(names)))


@register_command
class InventoryCommand(Command):
    name = "inventory"
    aliases = ("inv", "i")

    def execute(self, session, arguments):
        player = session.player

        if not player.inventory:
            session.send("You are carrying nothing.")
            return

        session.send("You are carrying:")
        for item in player.inventory:
            equipped = ""

            if item in player.equipment.values():
                equipped = " (equipped)"

            session.send("  {0}{1}".format(item.name, equipped))


@register_command
class TakeCommand(Command):
    name = "take"
    aliases = ("get",)

    def execute(self, session, arguments):
        player = session.player
        wanted = arguments.strip().lower()

        if not wanted:
            session.send("Take what?")
            return

        item = None

        with player.room.lock:
            for candidate in player.room.items:
                if candidate.name.lower() == wanted:
                    item = candidate
                    break

            if item is not None:
                player.room.items.remove(item)

        if item is None:
            session.send("There is no {0} here.".format(arguments))
            return

        player.inventory.append(item)
        session.send("You take the {0}.".format(item.name))

        player.room.broadcast(
            "* {0} takes the {1}.".format(player.name, item.name),
            exclude=session
        )


@register_command
class DropCommand(Command):
    name = "drop"
    aliases = ()

    def execute(self, session, arguments):
        player = session.player
        item = player.find_item(arguments)

        if item is None:
            session.send("You are not carrying that.")
            return

        for slot, equipped_item in list(player.equipment.items()):
            if equipped_item is item:
                item.on_unequip(player)
                del player.equipment[slot]

        player.inventory.remove(item)

        with player.room.lock:
            player.room.items.append(item)

        session.send("You drop the {0}.".format(item.name))

        player.room.broadcast(
            "* {0} drops the {1}.".format(player.name, item.name),
            exclude=session
        )


@register_command
class EquipCommand(Command):
    name = "equip"
    aliases = ("wear",)

    def execute(self, session, arguments):
        player = session.player
        item = player.find_item(arguments)

        if item is None:
            session.send("You are not carrying that.")
            return

        if not item.wearable:
            session.send("You cannot equip that.")
            return

        old_item = player.equipment.get("head")

        if old_item is item:
            session.send("You are already wearing it.")
            return

        if old_item is not None:
            old_item.on_unequip(player)

        player.equipment["head"] = item
        item.on_equip(player)

        session.send("You equip the {0}.".format(item.name))
        session.send("You feel considerably more fabulous.")

        player.room.broadcast(
            "* {0} equips an enormous fabulous pimp hat.".format(player.name),
            exclude=session
        )


@register_command
class StatsCommand(Command):
    name = "stats"
    aliases = ()

    def execute(self, session, arguments):
        player = session.player
        session.send("Name: {0}".format(player.name))
        session.send(
            "Fabulousness: +{0}%".format(player.fabulousness)
        )


@register_command
class BlingCommand(Command):
    name = "bling"
    aliases = ()

    def execute(self, session, arguments):
        player = session.player
        hat = PimpHat()

        with player.room.lock:
            player.room.items.append(hat)

        if hasattr(player.room, "hat_was_summoned"):
            player.room.hat_was_summoned()

        player.room.broadcast("")
        player.room.broadcast(
            "* AN ENORMOUS FABULOUS PIMP HAT FALLS FROM THE SKY *"
        )
        player.room.broadcast("")
        session.send("It lands at your feet with impossible style.")


@register_command
class WorshipCommand(Command):
    name = "worship"
    aliases = ()

    def execute(self, session, arguments):
        player = session.player
        wanted = arguments.strip().lower()

        if not wanted:
            session.send("Worship whom?")
            return

        target = None

        with player.room.lock:
            for candidate in player.room.players:
                if candidate.name.lower() == wanted:
                    target = candidate
                    break

        if target is None:
            session.send("That person is not here.")
            return

        if target is player:
            session.send("")
            session.send("BEHOLD EGOTHEISM!")
            session.send("")
            player.room.broadcast(
                "* {0} worships {0} *".format(player.name)
            )
            return

        session.send("You bow before {0}.".format(target.name))

        player.room.broadcast(
            "* {0} bows before {1} *".format(player.name, target.name),
            exclude=session
        )


@register_command
class QuitCommand(Command):
    name = "quit"
    aliases = ("exit",)

    def execute(self, session, arguments):
        session.send("Goodbye!")
        session.running = False


class Session(object):
    """One connected Telnet user.

    Each instance is run by one server-created thread.
    """

    def __init__(self, request, address, world):
        self.request = request
        self.address = address
        self.world = world
        self.player = None
        self.running = True
        self.receive_buffer = b""
        self.send_lock = threading.RLock()

    def send(self, message=""):
        if not self.running:
            return

        text = "{0}\r\n".format(message)

        try:
            data = text.encode("utf-8", "replace")
            with self.send_lock:
                self.request.sendall(data)
        except Exception:
            self.running = False

    def prompt(self, text):
        if not self.running:
            return

        try:
            data = text.encode("utf-8", "replace")
            with self.send_lock:
                self.request.sendall(data)
        except Exception:
            self.running = False

    def read_line(self, hidden=False):
        """Read one line.

        'hidden' is advisory only. Ordinary Telnet cannot reliably disable
        local echo without proper option negotiation, so passwords may be
        visible depending on the client.
        """
        while self.running:
            newline = self.receive_buffer.find(b"\n")

            if newline != -1:
                raw_line = self.receive_buffer[:newline]
                self.receive_buffer = self.receive_buffer[newline + 1:]

                raw_line = raw_line.rstrip(b"\r")
                raw_line = strip_telnet_control_codes(raw_line)

                return raw_line.decode("utf-8", "replace").strip()

            data = self.request.recv(1024)

            if not data:
                self.running = False
                return None

            self.receive_buffer += data

        return None

    def login(self):
        self.send("")
        self.send("Welcome to BLINGMUD")
        self.send("===================")
        self.send("")
        self.send("Type NEWUSER if you're new.")
        self.send("Do not reuse an important password here.")
        self.send("")

        while self.running:
            self.prompt("Name: ")
            name = self.read_line()

            if name is None:
                return False

            name = name.strip()

            if not name:
                continue

            if name.lower() == "newuser":
                return self.create_user()

            key = name.lower()

            with USERS_LOCK:
                account = USERS.get(key)

            if account is None:
                self.send(
                    "No such user. Type NEWUSER to create an account."
                )
                continue

            self.prompt("Password: ")
            password = self.read_line(hidden=True)

            if password is None:
                return False

            if password_hash(password) != account["password"]:
                self.send("Incorrect password.")
                continue

            with SESSIONS_LOCK:
                if key in SESSIONS:
                    self.send("That user is already connected.")
                    continue

                self.player = Player(account["name"])
                self.player.session = self
                SESSIONS[key] = self

            return True

        return False

    def create_user(self):
        self.send("")
        self.send("Creating a new BLINGMUD user.")

        while self.running:
            self.prompt("Choose a name: ")
            name = self.read_line()

            if name is None:
                return False

            name = name.strip()

            if not valid_username(name):
                self.send(
                    "Names must be 2-20 characters and contain only "
                    "letters, numbers, underscores or hyphens."
                )
                continue

            key = name.lower()

            with USERS_LOCK:
                if key in USERS:
                    self.send("That name is already registered.")
                    continue

            self.prompt("Choose a password: ")
            password = self.read_line(hidden=True)

            if password is None:
                return False

            if len(password) < 4:
                self.send("Please use at least four characters.")
                continue

            self.prompt("Confirm password: ")
            confirmation = self.read_line(hidden=True)

            if confirmation is None:
                return False

            if password != confirmation:
                self.send("The passwords did not match.")
                continue

            with USERS_LOCK:
                if key in USERS:
                    self.send(
                        "Someone registered that name while you typed."
                    )
                    continue

                USERS[key] = {
                    "name": name,
                    "password": password_hash(password)
                }

            with SESSIONS_LOCK:
                self.player = Player(name)
                self.player.session = self
                SESSIONS[key] = self

            self.send("Account created.")
            return True

        return False

    def move(self, direction):
        player = self.player
        direction = direction.lower()

        destination = player.room.exits.get(direction)

        if destination is None:
            self.send("You cannot go {0}.".format(direction))
            return

        old_room = player.room
        old_room.leave(player)
        destination.enter(player)
        destination.describe_to(player)

    def handle_chat(self, line):
        self.player.room.broadcast(
            "<{0}> {1}".format(self.player.name, line)
        )

    def handle_command(self, line):
        command_line = line[1:].strip()

        if not command_line:
            return

        pieces = command_line.split(None, 1)
        command_name = pieces[0].lower()

        if len(pieces) == 2:
            arguments = pieces[1]
        else:
            arguments = ""

        command = COMMANDS.get(command_name)

        if command is not None:
            command.execute(self, arguments)
            return

        if self.player.room.on_command(
            self,
            command_name,
            arguments
        ):
            return

        self.send(
            "Unknown command: /{0}. Try /help.".format(command_name)
        )

    def run(self):
        try:
            if not self.login():
                return

            self.send("")
            self.send("Welcome, {0}.".format(self.player.name))
            self.send("Ordinary text is spoken aloud.")
            self.send("Commands begin with a slash. Try /help.")
            self.send("More importantly, try /bling.")
            self.send("")

            self.world.starting_room.enter(self.player)
            self.world.starting_room.describe_to(self.player)

            while self.running:
                self.prompt("> ")
                line = self.read_line()

                if line is None:
                    break

                if not line:
                    continue

                if line.startswith("/"):
                    self.handle_command(line)
                else:
                    self.handle_chat(line)

        except Exception:
            traceback.print_exc()

        finally:
            self.disconnect()

    def disconnect(self):
        if not self.running and self.player is None:
            return

        self.running = False

        if self.player is not None:
            player = self.player

            if player.room is not None:
                player.room.leave(player)

            key = player.name.lower()

            with SESSIONS_LOCK:
                if SESSIONS.get(key) is self:
                    del SESSIONS[key]

            player.session = None
            self.player = None

        try:
            self.request.shutdown(2)
        except Exception:
            pass

        try:
            self.request.close()
        except Exception:
            pass


class World(object):
    def __init__(self):
        self.rooms = {}
        self.starting_room = None
        self.build()

    def add_room(self, room):
        self.rooms[room.room_id] = room
        return room

    def build(self):
        square = self.add_room(
            Room(
                "town_square",
                "The Town Square",
                "This is the social heart of BLINGMUD. A tasteful sign "
                "reads: ORDINARY TEXT IS CHAT. COMMANDS BEGIN WITH /."
            )
        )

        chamber = self.add_room(FabulousChamber())

        alley = self.add_room(
            Room(
                "suspicious_alley",
                "A Suspicious Alley",
                "The alley is dark, narrow and probably needlessly "
                "dramatic. Something rustles behind a bin."
            )
        )

        square.add_exit("north", chamber)
        chamber.add_exit("south", square)

        square.add_exit("east", alley)
        alley.add_exit("west", square)

        self.starting_room = square


WORLD = World()


def valid_username(name):
    if len(name) < 2 or len(name) > 20:
        return False

    for character in name:
        if not (
            character.isalnum()
            or character == "_"
            or character == "-"
        ):
            return False

    return True


class MudRequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        session = Session(
            self.request,
            self.client_address,
            WORLD
        )
        session.run()


class ThreadedMudServer(
    socketserver.ThreadingMixIn,
    socketserver.TCPServer
):
    allow_reuse_address = True

    # Client threads will not prevent server shutdown.
    daemon_threads = True


def main():
    server = ThreadedMudServer((HOST, PORT), MudRequestHandler)

    print("BLINGMUD listening on {0}:{1}".format(HOST, PORT))
    print("Connect with: telnet localhost {0}".format(PORT))
    print("Press Ctrl-C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("Shutting down BLINGMUD.")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
