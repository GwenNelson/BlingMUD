#!/usr/bin/env python3
#
# BLINGMUD
#
# Deliberately simple threaded Telnet MUD server.
# Compatible with Python 3.0-era syntax: no f-strings, dataclasses,
# asyncio, type annotations, or other modern frippery.
#


import os
import time
import random
import json
import sqlite3
import hashlib
import socketserver
import threading
import traceback

USERS_DB = 'users.sqlite'
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

ADMIN_PASSWORD_HASH = None

IAC = 255
WILL = 251
WONT = 252
DO = 253
DONT = 254

TELOPT_ECHO = 1
TELOPT_SGA = 3
TELOPT_LINEMODE = 34

def password_hash(password):
    """Return a simple password hash.

    This is adequate only for the deliberately temporary prototype.
    Use a proper slow password hash before adding persistent accounts.
    """
    encoded = password.encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def init_user_database():
    connection = sqlite3.connect(USERS_DB)

    try:
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                username_lower TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                json_state TEXT NOT NULL
            )
        """)

        connection.commit()

    finally:
        connection.close()


def user_exists(username):
    connection = sqlite3.connect(USERS_DB)

    try:
        cursor = connection.cursor()

        cursor.execute(
            "SELECT 1 FROM users WHERE username_lower=?",
            (username.lower(),)
        )

        return cursor.fetchone() is not None

    finally:
        connection.close()


def create_user(username, password):
    connection = sqlite3.connect(USERS_DB)

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO users
            (username, username_lower, password_hash, json_state)
            VALUES (?, ?, ?, ?)
            """,
            (
                username,
                username.lower(),
                password_hash(password),
                json.dumps({})
            )
        )

        connection.commit()

    finally:
        connection.close()


def load_user(username):
    connection = sqlite3.connect(USERS_DB)

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT username,
                   password_hash,
                   json_state
            FROM users
            WHERE username_lower=?
            """,
            (username.lower(),)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "username": row[0],
            "password": row[1],
            "state": json.loads(row[2])
        }

    finally:
        connection.close()

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

class Colour:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

def colour(text, code):
    return code + text + Colour.RESET

from core import *

from rooms.fabulous_chamber import FabulousChamber
from rooms.crossroads import Crossroads

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
class AdminCommand(Command):
    name = "admin"
    def execute(self,session,arguments):
        if ADMIN_PASSWORD_HASH is None:
            session.send("Thou hath failed to configure thy admin.hash file, foolish fool!")
            return
        session.prompt("Password: ")

        try_admin_pwd = session.read_line(hidden=True)
        hashed = password_hash(try_admin_pwd)
        if hashed == ADMIN_PASSWORD_HASH:
           session.player.is_admin = True
           session.send("Reality bends to your will")
        else:
           session.send("Be gone! That is not the magic word!")


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
            room_items   = list(player.room.items)
            room_players = list(player.room.players)
            room_npcs    = list(player.room.npcs)

        for item in player.inventory + room_items:
            if item.name.lower() == target_name:
                session.send(item.look(player))
                return

        for other_player in room_players:
            if other_player.name.lower() == target_name:
                session.send(other_player.look(player))
                return

        for npc in room_npcs:
            if npc.name.lower() == target_name:
               session.send(npc.look(player))
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
            player.room.broadcast("BEHOLD EGOTHEISM: * {0} worships {0} *".format(player.name))
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

        # State for preserving partially typed input when asynchronous
        # world messages arrive.
        self.prompt_text = ""
        self.current_input = ""
        self.input_active = False
        self.input_hidden = False

    def enable_character_mode(self):
        """Ask a real Telnet client to use server-side character input."""
        negotiation = bytes((
            IAC, WILL, TELOPT_ECHO,
            IAC, WILL, TELOPT_SGA,
            IAC, DONT, TELOPT_LINEMODE
        ))

        with self.send_lock:
            self.request.sendall(negotiation)

    def _consume_telnet_command(self):
        """Consume one Telnet command after an IAC byte."""

        try:
            command_data = self.request.recv(1)

            if not command_data:
                self.running = False
                return False

            command = command_data[0]

            # WILL, WONT, DO and DONT have an option byte.
            if command in (WILL, WONT, DO, DONT):
                option_data = self.request.recv(1)

                if not option_data:
                    self.running = False
                    return False

                return True

            # Escaped literal 255. Currently ignored.
            if command == IAC:
                return True

            return True

        except Exception:
            self.running = False
            return False

    def send(self, message=""):
        """Send a complete line to the client.

        If the player is currently typing, temporarily erase their prompt
        and partial input, print the message, then restore both.
        """
        if not self.running:
            return

        text = "{0}\r\n".format(message)

        try:
            data = text.encode("utf-8", "replace")

            with self.send_lock:
                if self.input_active:
                    # Return to column zero and erase the entire current line.
                    self.request.sendall(b"\r\033[2K")

                self.request.sendall(data)

                if self.input_active:
                    restored = self.prompt_text

                    # Passwords and other hidden input should not be redrawn.
                    if not self.input_hidden:
                        restored += self.current_input

                    self.request.sendall(
                        restored.encode("utf-8", "replace")
                    )

        except Exception:
            self.running = False

    def prompt(self, text):
        """Display a prompt and begin tracking the player's input line."""
        if not self.running:
            return

        try:
            data = text.encode("utf-8", "replace")

            with self.send_lock:
                self.prompt_text = text
                self.current_input = ""
                self.input_active = True
                self.input_hidden = False

                self.request.sendall(data)

        except Exception:
            self.running = False

    def _input_text_from_bytes(self, data):
        """Produce the current editable input text from received bytes.

        This handles ordinary characters and basic Backspace/Delete editing.
        More advanced cursor movement and command history can be added later.
        """
        data = strip_telnet_control_codes(data)
        text = data.decode("utf-8", "replace")

        result = []

        for character in text:
            if character == "\r" or character == "\n":
                continue

            if character == "\b" or ord(character) == 127:
                if result:
                    result.pop()
                continue

            result.append(character)

        return "".join(result)


    def read_line(self, hidden=False):
        """Read and edit one line using server-side character echo."""

        characters = []

        with self.send_lock:
            self.current_input = ""
            self.input_active = True
            self.input_hidden = hidden

        while self.running:
            try:
                data = self.request.recv(1)
            except Exception:
                self.running = False
                return None

            if not data:
                self.running = False
                return None

            byte = data[0]

            # Telnet command.
            if byte == IAC:
                if not self._consume_telnet_command():
                    return None
                continue

            # Enter may arrive as CR LF, CR NUL, or just LF.
            if byte in (10, 13):
                with self.send_lock:
                    self.request.sendall(b"\r\n")

                    self.current_input = ""
                    self.prompt_text = ""
                    self.input_active = False
                    self.input_hidden = False

                return "".join(characters).strip()

            # Backspace or Delete.
            if byte in (8, 127):
                if characters:
                    characters.pop()

                    with self.send_lock:
                        self.current_input = "".join(characters)

                        if not hidden:
                            # Move back, erase character, move back again.
                            self.request.sendall(b"\b \b")

                continue

            # Ignore other ASCII control characters for now.
            if byte < 32:
                continue

            character = bytes((byte,)).decode("utf-8", "replace")
            characters.append(character)

            with self.send_lock:
                self.current_input = "".join(characters)

                if not hidden:
                    self.request.sendall(
                        character.encode("utf-8", "replace")
                    )



    def typewriter(self, text, delay=0.4):
        with self.send_lock:
            time.sleep(delay)

            for character in text:
                self.request.sendall(
                    character.encode("utf-8")
                )

                if character == "\n":
                    self.current_input = ""
                    self.prompt_text = ""
                    self.input_active = False
                    self.input_hidden = False

                elif character == "\r":
                    pass

                elif character == "\b":
                    if self.current_input:
                        self.current_input = self.current_input[:-1]

                else:
                    self.current_input += character

                time.sleep(delay)


    def login(self):
        self.send("")
        self.send("Welcome to BlingMUD")
        self.send("===================")
        self.send("")
        self.send("Type NEWUSER if you're new. Use all caps. Note that this a seperate service from IRC or whatever else is hosted by the admins")
        self.send("You will need to setup a new account if you've never used BlingMUD before")
        self.send("")
        self.send("BlingMUD is in heavy development right now - watch this space for updates!")
        self.send("")
        self.send("As of 27th July 2026 at 23:38 BST, user accounts are usually persistent - remember this is alpha software, resets might still occur")
        self.send("If you find your login fails and you get the NEWUSER insult screen, the user database probably got reset, oops")
        self.send("")
        self.send("**** IMPORTANT ****")
        self.send("DO NOT reuse an important password here.")
        self.send("Please also note that passwords will probably echo - you have been warned!")
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
                account = load_user(name)

            if account is None:
                self.send("No such user")
                self.send("Are you new? We told you to type NEWUSER, but never mind, maybe we should do that for you?")
                self.send("If you're not new, maybe disconnect and reconnect - and mind your typos!")
                time.sleep(0.5)
                self.send("")
                self.send("But assuming you're a newbie, fine, wait a moment")
                self.typewriter("......\r\n")
                self.send("")
                time.sleep(1.5)
                self.prompt("Calling someone to fix your mess")
                self.typewriter(".........\r\n")
                self.send("Don't worry, someone is fixing it for you now. Watch and learn:")
                self.send("")
                time.sleep(0.75)
                self.prompt("Name: ")
                self.typewriter("NEWUSER\r\n")
                self.send("")
                self.send("Creating a newbie BlingMUD user.")
                self.prompt("Choose a name: ")
                self.typewriter("StupidNewbie\r\n")
                self.send("")
                self.send("Only joking, let's do it properly - this time you take over after we type NEWUSER for you, mmkay?")
                self.send("")
                time.sleep(1.5)
                self.prompt("Name: ")
                self.typewriter("NEWUSER\r\n")
                return self.create_user()

            self.send("Please note, your password input might echo - meaning people might see you typing it")
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

                self.player = Player(account["username"])
                self.player.session = self
                SESSIONS[key] = self

            return True

        return False

    def create_user(self):
        self.send("")
        self.send("Creating a new BlingMUD user.")

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
                if user_exists(name):
                    self.send("That name is already registered.")
                    continue
            self.send("DO NOT USE A PASSWORD YOU USE SOMEWHERE ELSE - the admins do not accept any liability for any loss if you do")
            self.send("Remember, this place is just for fun, it's not meant to be serious")
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
                if user_exists(name):
                    self.send(
                        "Someone registered that name while you typed."
                    )
                    continue

                create_user(name,password)

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
        destination.describe_to(player)
        self.send("")
        destination.enter(player)

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
           if command.admin_only and not session.player.is_admin:
              session.send("You lack sufficient fabulousness.")
              return
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
        self.enable_character_mode()

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
                "\r\n\r\n"
                "To the south lay the crossroads, where travellers may begin quests\r\n"
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

        crossroads = self.add_room(Crossroads())

        square.add_exit("north", chamber)
        chamber.add_exit("south", square)

        square.add_exit("east", alley)
        alley.add_exit("west", square)

        square.add_exit("south",crossroads)
        crossroads.add_exit("north",square)

        self.starting_room = square


NPC_MANAGER = NPCManager.instance() # just to init it
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
    global ADMIN_PASSWORD_HASH
    global NPC_MANAGER

    init_user_database()

    if os.path.exists("admin.hash"):
        with open("admin.hash", "r") as f:
            ADMIN_PASSWORD_HASH = f.read().strip()

        print("Admin password loaded.")
    else:
        print("WARNING: admin.hash not found.")
        print("         Administrative commands are disabled.")


    server = ThreadedMudServer((HOST, PORT), MudRequestHandler)

    print("BLINGMUD listening on {0}:{1}".format(HOST, PORT))
    print("Connect with: telnet localhost {0}".format(PORT))
    print("Press Ctrl-C to stop.")

    try:
        NPC_MANAGER.start()
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("Shutting down BLINGMUD.")
    finally:
        server.shutdown()
        server.server_close()
        NPC_MANAGER.stop()

if __name__ == "__main__":
    main()
