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
import sqlite3
import hashlib
import hmac
import socketserver
import sys
import threading
import traceback

from player_state import (
    MAX_PLAYER_STATE_BYTES,
    PlayerStateError,
    new_player_state_json,
    restore_player_state,
    serialize_player_state
)

USERS_DB = 'users.sqlite'
HOST = "0.0.0.0"
PORT = 4000

# Active sessions, indexed by lowercase username.
SESSIONS = {}

USERS_LOCK = threading.RLock()
SESSIONS_LOCK = threading.RLock()

ADMIN_PASSWORD_HASH = None

PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 600000
PASSWORD_HASH_MAX_ITERATIONS = 1200000
PASSWORD_SALT_BYTES = 16
PASSWORD_DIGEST_BYTES = 32
MAX_PASSWORD_LENGTH = 4096
MAX_STORED_PASSWORD_HASH_LENGTH = 512
MAX_INPUT_LENGTH = 4096
MAX_USERNAME_INPUT_LENGTH = 21

IAC = 255
WILL = 251
WONT = 252
DO = 253
DONT = 254

TELOPT_ECHO = 1
TELOPT_SGA = 3
TELOPT_LINEMODE = 34

def password_hash(password):
    """Return a salted, deliberately slow password hash for storage."""
    if not isinstance(password, str):
        raise TypeError("password must be text")

    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("password is too long")

    salt = os.urandom(PASSWORD_SALT_BYTES)
    encoded = password.encode("utf-8")
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        encoded,
        salt,
        PASSWORD_HASH_ITERATIONS
    )

    return "{0}${1}${2}${3}".format(
        PASSWORD_HASH_SCHEME,
        PASSWORD_HASH_ITERATIONS,
        salt.hex(),
        digest.hex()
    )


def verify_password(password, stored_hash):
    """Verify current hashes and legacy unsalted SHA-256 hashes."""
    if not isinstance(password, str) or not isinstance(stored_hash, str):
        return False

    if not stored_hash or len(password) > MAX_PASSWORD_LENGTH:
        return False

    if len(stored_hash) > MAX_STORED_PASSWORD_HASH_LENGTH:
        return False

    if "$" not in stored_hash:
        if len(stored_hash) != 64:
            return False

        try:
            int(stored_hash, 16)
        except ValueError:
            return False

        legacy_digest = hashlib.sha256(
            password.encode("utf-8")
        ).hexdigest()
        return hmac.compare_digest(legacy_digest, stored_hash)

    try:
        scheme, iterations_text, salt_hex, digest_hex = stored_hash.split("$", 3)
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except (TypeError, ValueError):
        return False

    if (
        scheme != PASSWORD_HASH_SCHEME
        or iterations <= 0
        or iterations > PASSWORD_HASH_MAX_ITERATIONS
        or len(salt) != PASSWORD_SALT_BYTES
        or len(expected_digest) != PASSWORD_DIGEST_BYTES
    ):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def password_hash_needs_upgrade(stored_hash):
    if not stored_hash:
        return True

    prefix = "{0}${1}$".format(
        PASSWORD_HASH_SCHEME,
        PASSWORD_HASH_ITERATIONS
    )
    return not stored_hash.startswith(prefix)


def write_admin_password_hash(stored_hash, filename="admin.hash"):
    descriptor = os.open(
        filename,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600
    )

    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            descriptor = None
            handle.write(stored_hash)
    finally:
        if descriptor is not None:
            os.close(descriptor)


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
                new_player_state_json()
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
            "state_json": row[2]
        }

    finally:
        connection.close()


def update_user_password_hash(username, new_password_hash):
    connection = sqlite3.connect(USERS_DB)

    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE users SET password_hash=? WHERE username_lower=?",
            (new_password_hash, username.lower())
        )
        connection.commit()

    finally:
        connection.close()


def update_user_state(username, encoded_state):
    if not isinstance(encoded_state, str):
        raise TypeError("encoded state must be text")

    if len(encoded_state) > MAX_PLAYER_STATE_BYTES:
        raise PlayerStateError("player state is too large")

    try:
        encoded_size = len(encoded_state.encode("utf-8"))
    except UnicodeError:
        raise PlayerStateError("player state contains invalid text")

    if encoded_size > MAX_PLAYER_STATE_BYTES:
        raise PlayerStateError("player state is too large")

    connection = sqlite3.connect(USERS_DB)

    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE users SET json_state=? WHERE username_lower=?",
            (encoded_state, username.lower())
        )

        if cursor.rowcount != 1:
            raise PlayerStateError("cannot save an unknown player")

        connection.commit()

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

from core import *

from rooms.fabulous_chamber import FabulousChamber
from rooms.crossroads import Crossroads
from rooms.suspicious_alley import SuspiciousAlley
from rooms.hanging_tree import HangingTreeCanopy
from rooms.village_green import VillageGreen
from village_state import VillageState

from commands.core import *

@register_command
class AdminCommand(Command):
    name = "admin"
    def execute(self,session,arguments):
        global ADMIN_PASSWORD_HASH

        if ADMIN_PASSWORD_HASH is None:
            session.send("Thou hath failed to configure thy admin.hash file, foolish fool!")
            return
        session.prompt("Password: ")

        try_admin_pwd = session.read_line(
            hidden=True,
            maximum_length=MAX_PASSWORD_LENGTH + 1
        )

        if (
            try_admin_pwd is not None
            and len(try_admin_pwd) <= MAX_PASSWORD_LENGTH
            and verify_password(try_admin_pwd, ADMIN_PASSWORD_HASH)
        ):
           if password_hash_needs_upgrade(ADMIN_PASSWORD_HASH):
               upgraded_hash = password_hash(try_admin_pwd)

               try:
                   write_admin_password_hash(upgraded_hash)
               except OSError:
                   print("WARNING: could not upgrade admin password hash.")
               else:
                   ADMIN_PASSWORD_HASH = upgraded_hash

           session.player.is_admin = True
           session.send("Reality bends to your will")
        else:
           session.send("Be gone! That is not the magic word!")


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
        self.login_room = None

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


    def read_line(self, hidden=False, maximum_length=MAX_INPUT_LENGTH):
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

            if len(characters) >= maximum_length:
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
        self.send(colour("Welcome to BlingMUD",Colour.TITLE))
        self.send("")
        self.send("Type %s if you're new. Use all caps. Note that this a seperate service from IRC or whatever else is hosted by the admins" % colour("NEWUSER",Colour.BRIGHT_WHITE))
        self.send("You will need to setup a new account if you've never used BlingMUD before")
        self.send("")
        self.send("BlingMUD is in heavy development right now - watch this space for updates!")
        self.send("")
        self.send("")
        self.send(colour("**** IMPORTANT ****",Colour.BRIGHT_RED))
        self.send("DO NOT reuse an important password here.")
        self.send("Please also note that passwords will potentially echo - you have been warned!")
        self.send("")

        while self.running:
            self.prompt("Name: ")
            name = self.read_line(maximum_length=MAX_USERNAME_INPUT_LENGTH)

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
            password = self.read_line(
                hidden=True,
                maximum_length=MAX_PASSWORD_LENGTH + 1
            )

            if password is None:
                return False

            if len(password) > MAX_PASSWORD_LENGTH:
                self.send("That password is too long.")
                continue

            if not verify_password(password, account["password"]):
                self.send("Incorrect password.")
                continue

            if password_hash_needs_upgrade(account["password"]):
                with USERS_LOCK:
                    update_user_password_hash(name, password_hash(password))

            player = Player(account["username"])
            player.session = self
            invalid_state = False

            try:
                login_room = restore_player_state(
                    player,
                    account["state_json"],
                    self.world
                )
            except PlayerStateError:
                sys.stderr.write(
                    "Invalid saved state for {0}; using safe defaults.\n".format(
                        account["username"]
                    )
                )
                invalid_state = True
                login_room = self.world.starting_room

            with SESSIONS_LOCK:
                already_connected = key in SESSIONS

                if not already_connected:
                    self.player = player
                    self.login_room = login_room
                    SESSIONS[key] = self

            if already_connected:
                self.send("That user is already connected.")
                continue

            if invalid_state:
                self.send(
                    "Your saved character state was invalid, so this "
                    "session is starting from safe defaults."
                )

            return True

        return False

    def create_user(self):
        self.send("")
        self.send("Creating a new BlingMUD user.")

        while self.running:
            self.prompt("Choose a name: ")
            name = self.read_line(maximum_length=MAX_USERNAME_INPUT_LENGTH)

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
            self.prompt("Choose a password: ")
            password = self.read_line(
                hidden=True,
                maximum_length=MAX_PASSWORD_LENGTH + 1
            )

            if password is None:
                return False

            if len(password) > MAX_PASSWORD_LENGTH:
                self.send("That password is too long.")
                continue

            if len(password) < 12:
                self.send("Please use at least twelve characters.")
                continue

            self.prompt("Confirm password: ")
            confirmation = self.read_line(
                hidden=True,
                maximum_length=MAX_PASSWORD_LENGTH + 1
            )

            if confirmation is None:
                return False

            if len(confirmation) > MAX_PASSWORD_LENGTH:
                self.send("That password confirmation is too long.")
                continue

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
                self.login_room = self.world.starting_room
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
            "<{0}> {1}".format(colour(self.player.name,Colour.BRIGHT_CYAN), line)
        )
        self.player.room.notify_player_said(self.player, line)

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
            if command.admin_only and not self.player.is_admin:
                self.send("You lack sufficient fabulousness.")
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

            entry_room = self.login_room or self.world.starting_room
            entry_room.enter(self.player)
            entry_room.describe_to(self.player)

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

            try:
                encoded_state = serialize_player_state(player)

                with USERS_LOCK:
                    update_user_state(player.name, encoded_state)
            except (PlayerStateError, sqlite3.Error) as error:
                sys.stderr.write(
                    "Could not save player state for {0}: {1}\n".format(
                        player.name,
                        error
                    )
                )

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
        self.village_state = VillageState()
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

        alley = self.add_room(SuspiciousAlley())

        crossroads = self.add_room(Crossroads())

        green = self.add_room(VillageGreen(self.village_state))
        canopy = self.add_room(HangingTreeCanopy(self.village_state))

        square.add_exit("north", chamber)
        chamber.add_exit("south", square)

        square.add_exit("east", alley)
        alley.add_exit("west", square)

        square.add_exit("south",crossroads)
        crossroads.add_exit("north",square)

        square.add_exit("west", green)
        green.add_exit("east", square)

        green.add_exit("up", canopy)
        canopy.add_exit("down", green)

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
