#!/usr/bin/env python3
#
# BLINGMUD
#
# Deliberately simple sequential-session Telnet MUD server.
# Runtime baseline: Python 3.11 or newer.  The code deliberately retains a
# plain Python 3.0-era style: no f-strings, dataclasses, asyncio, type-heavy
# architecture, or other modern frippery in the gameplay path.
#


import os
import time
import random
import sqlite3
import hashlib
import hmac
import sys
import threading
import traceback

from server_runtime import SelectorMudServer
from persistence_runtime import (
    AutosaveCoordinator,
    GRACEFUL_FLUSH_SECONDS,
    PersistenceWriter
)
from telnet_parser import (
    BackspaceInputEvent,
    DONT,
    DO,
    IAC,
    LineInputEvent,
    TabInputEvent,
    TelnetInputParser,
    TextInputEvent,
    WILL,
    WONT
)

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

PLAINTEXT_TELNET_WARNING = (
    "SECURITY WARNING: BlingMUD uses plaintext Telnet.",
    "Passwords and gameplay can be observed or altered in transit.",
    "Do not reuse an important password or treat this connection as secure."
)

# Active sessions, indexed by lowercase username.
SESSIONS = {}

USERS_LOCK = threading.RLock()
SESSIONS_LOCK = threading.RLock()

ADMIN_PASSWORD_HASH = None
PERSISTENCE_WRITER = None
AUTOSAVE_COORDINATOR = None

PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 600000
PASSWORD_HASH_MAX_ITERATIONS = 1200000
PASSWORD_SALT_BYTES = 16
PASSWORD_DIGEST_BYTES = 32
MAX_PASSWORD_LENGTH = 4096
MAX_STORED_PASSWORD_HASH_LENGTH = 512
MAX_INPUT_LENGTH = 4096
MAX_USERNAME_INPUT_LENGTH = 21

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


def persist_user_state(username, encoded_state):
    """Write one validated player snapshot through the shared DB lock."""
    with USERS_LOCK:
        update_user_state(username, encoded_state)


def active_sessions_snapshot():
    with SESSIONS_LOCK:
        return list(SESSIONS.values())

from core import *

from rooms.fabulous_chamber import FabulousChamber
from rooms.crossroads import Crossroads
from rooms.suspicious_alley import SuspiciousAlley
from rooms.hanging_tree import HangingTreeCanopy
from rooms.village_green import VillageGreen
from rooms.vals_hella_holler import ValsHellaHoller
from village_state import VillageState

from commands.core import *

@register_command
class AdminCommand(Command):
    name = "admin"
    aliases = ()
    usage = "/admin"
    summary = "Authenticate this session for administrative commands."
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
    usage = "/who"
    summary = "List authenticated players currently online."

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
    usage = "/worship <person>"
    summary = "Offer the appropriate reverence to someone in the room."

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

    Authenticated gameplay for each instance is run by one sequential worker.
    Network reads and writes may be owned by the selector runtime.
    """

    def __init__(self, request, address, world, persistence_writer=None):
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
        self.gameplay_thread = None
        self.gameplay_thread_lock = threading.RLock()
        self.state_lock = threading.RLock()
        self.save_lock = threading.RLock()
        self.persistence_writer = persistence_writer
        self.persisted_state_json = None
        self.last_submitted_state_json = None
        self.last_save_receipt = None
        self.last_save_error = None
        self.input_parser = TelnetInputParser(MAX_INPUT_LENGTH)

    def set_persisted_state(self, encoded_state):
        with self.save_lock:
            self.persisted_state_json = encoded_state
            self.last_submitted_state_json = encoded_state
            self.last_save_receipt = None
            self.last_save_error = None

    def _save_completed(self, success, error, requested_state):
        with self.save_lock:
            if success:
                self.persisted_state_json = requested_state
                self.last_save_error = None
            else:
                self.last_save_error = error

                if self.last_submitted_state_json == requested_state:
                    self.last_submitted_state_json = self.persisted_state_json

    def save_if_changed(self, wait=False, timeout=GRACEFUL_FLUSH_SECONDS):
        """Serialize once and write only when the snapshot has changed."""
        if self.player is None:
            return "unavailable"

        if not self.running and not wait:
            return "unavailable"

        state_acquired = self.state_lock.acquire(blocking=bool(wait))

        if not state_acquired:
            return "busy"

        try:
            player = self.player

            if player is None:
                return "unavailable"

            username = player.name
            encoded_state = serialize_player_state(player)
        except PlayerStateError as error:
            with self.save_lock:
                self.last_save_error = error
            return "failed"
        finally:
            self.state_lock.release()

        wait_for_existing = None
        receipt = None

        with self.save_lock:
            if encoded_state == self.last_submitted_state_json:
                wait_for_existing = self.last_save_receipt

                if wait_for_existing is None or not wait:
                    return "unchanged"

                if wait_for_existing.event.is_set():
                    if wait_for_existing.success:
                        return "unchanged"

                    self.last_save_error = wait_for_existing.error
                    return "failed"
            else:
                writer = self.persistence_writer

                if writer is None:
                    try:
                        persist_user_state(username, encoded_state)
                    except (PlayerStateError, sqlite3.Error) as error:
                        self.last_save_error = error
                        return "failed"

                    self.persisted_state_json = encoded_state
                    self.last_submitted_state_json = encoded_state
                    self.last_save_receipt = None
                    self.last_save_error = None
                    return "queued"

                receipt = writer.submit(
                    username,
                    encoded_state,
                    self._save_completed
                )

                if receipt.event.is_set() and not receipt.success:
                    self.last_save_error = receipt.error
                    return "failed"

                self.last_submitted_state_json = encoded_state
                self.last_save_receipt = receipt

        if wait_for_existing is not None:
            if wait_for_existing.wait(timeout):
                return "unchanged"

            with self.save_lock:
                if wait_for_existing.error is not None:
                    self.last_save_error = wait_for_existing.error
                else:
                    self.last_save_error = RuntimeError(
                        "timed out waiting for persistence writer"
                    )
            return "failed"

        if wait and not receipt.wait(timeout):
            with self.save_lock:
                if receipt.error is not None:
                    self.last_save_error = receipt.error
                else:
                    self.last_save_error = RuntimeError(
                        "timed out waiting for persistence writer"
                    )
            return "failed"

        return "queued"

    def enable_character_mode(self):
        """Ask a real Telnet client to use server-side character input."""
        negotiation = bytes((
            IAC, WILL, TELOPT_ECHO,
            IAC, WILL, TELOPT_SGA,
            IAC, DONT, TELOPT_LINEMODE
        ))

        with self.send_lock:
            self.request.sendall(negotiation)

    def send_transport_warning(self):
        """Warn before authentication that Telnet has no encryption."""
        self.send(colour("**** PLAINTEXT TELNET WARNING ****", Colour.BRIGHT_RED))

        for line in PLAINTEXT_TELNET_WARNING:
            self.send(line)

        self.send(
            "BlingMUD suppresses password echo, but a client may still "
            "display typed characters."
        )

    def send_login_banner(self):
        self.send("")
        self.send(colour("Welcome to BlingMUD", Colour.TITLE))
        self.send("")
        self.send(
            "Type {0} if you're new. Use all caps. This is a separate "
            "service from IRC or anything else hosted by the admins.".format(
                colour("NEWUSER", Colour.BRIGHT_WHITE)
            )
        )
        self.send(
            "You need a separate BlingMUD account if you have never used "
            "this service before."
        )
        self.send("")
        self.send("BlingMUD is in heavy development right now!")
        self.send("")
        self.send_transport_warning()
        self.send("")

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

    def prompt(self, text, hidden=False, maximum_length=MAX_INPUT_LENGTH):
        """Display a prompt and begin tracking the player's input line."""
        if not self.running:
            return

        try:
            data = text.encode("utf-8", "replace")

            with self.send_lock:
                self.prompt_text = text
                self.current_input = ""
                self.input_active = True
                self.input_hidden = bool(hidden)

                self.request.sendall(data)

                configure_input = getattr(
                    self.request,
                    "configure_input",
                    None
                )

                if configure_input is not None:
                    configure_input(hidden, maximum_length)

                self.input_parser.set_maximum_length(maximum_length)

        except Exception:
            self.running = False

    def read_line(self, hidden=False, maximum_length=MAX_INPUT_LENGTH):
        """Read and edit one line using server-side character echo."""

        queued_reader = getattr(self.request, "read_line", None)

        if queued_reader is not None:
            with self.send_lock:
                self.input_active = True
                self.input_hidden = hidden

            while self.running:
                line = queued_reader(hidden, maximum_length)

                if isinstance(line, TabInputEvent):
                    self.handle_tab_completion(line.text)
                    continue

                break

            with self.send_lock:
                self.current_input = ""
                self.prompt_text = ""
                self.input_active = False
                self.input_hidden = False

            if line is None:
                self.running = False
                return None

            return line.strip()

        with self.send_lock:
            self.current_input = self.input_parser.current_text
            self.input_active = True
            self.input_hidden = hidden

        self.input_parser.set_maximum_length(maximum_length)

        while self.running:
            try:
                data = self.request.recv(1)
            except Exception:
                self.running = False
                return None

            if not data:
                self.running = False
                return None

            for event in self.input_parser.feed(data):
                if isinstance(event, TextInputEvent):
                    with self.send_lock:
                        self.current_input = event.current_text

                        if not hidden:
                            self.request.sendall(
                                event.text.encode("utf-8", "replace")
                            )
                elif isinstance(event, BackspaceInputEvent):
                    with self.send_lock:
                        self.current_input = event.current_text

                        if not hidden:
                            self.request.sendall(b"\b \b")
                elif isinstance(event, TabInputEvent):
                    self.handle_tab_completion(event.text)
                elif isinstance(event, LineInputEvent):
                    with self.send_lock:
                        self.request.sendall(b"\r\n")
                        self.current_input = ""
                        self.prompt_text = ""
                        self.input_active = False
                        self.input_hidden = False

                    return event.text.strip()

    def handle_tab_completion(self, current_text):
        """Complete the command token without clobbering newer input."""
        if self.input_hidden:
            try:
                with self.send_lock:
                    self.request.sendall(b"\a")
            except Exception:
                self.running = False
            return

        replacement, candidates = complete_command_text(
            self,
            current_text
        )

        if replacement is not None:
            replacer = getattr(self.request, "replace_current_input", None)

            with self.send_lock:
                if replacer is None:
                    if self.input_parser.current_text != current_text:
                        accepted = None
                    else:
                        accepted = self.input_parser.replace_current_text(
                            replacement
                        )
                else:
                    accepted = replacer(current_text, replacement)

                if accepted is not None:
                    self.current_input = accepted
                    self.request.sendall(b"\r\033[2K")
                    self.request.sendall(
                        (self.prompt_text + accepted).encode(
                            "utf-8",
                            "replace"
                        )
                    )
                    return

        if candidates:
            self.send(
                "Matches: {0}".format(
                    ", ".join("/" + name for name in candidates)
                )
            )
            return

        try:
            with self.send_lock:
                self.request.sendall(b"\a")
        except Exception:
            self.running = False



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
        self.send_login_banner()

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

            self.set_persisted_state(account["state_json"])

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

            self.set_persisted_state(new_player_state_json())

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

        room = self.player.room

        if command_name not in RESERVED_GLOBAL_COMMANDS and room is not None:
            if room.on_command(
                self,
                command_name,
                arguments
            ):
                return

        command = COMMANDS.get(command_name)

        if command is not None:
            if command.admin_only and not self.player.is_admin:
                self.send("You lack sufficient fabulousness.")
                return
            command.execute(self, arguments)
            return

        self.send(
            "Unknown command: /{0}. Try /help.".format(command_name)
        )


    def start_gameplay_worker(self):
        """Start exactly one sequential worker after authentication."""
        with self.gameplay_thread_lock:
            if self.gameplay_thread is not None:
                return False

            player_name = "unknown"

            if self.player is not None:
                player_name = self.player.name.lower()

            worker = threading.Thread(
                target=self.run_authenticated,
                name="blingmud-player-{0}".format(player_name),
                daemon=True
            )
            self.gameplay_thread = worker
            worker.start()
        return True

    def run(self):
        """Compatibility entry point for a directly-owned blocking socket."""
        self.enable_character_mode()

        try:
            if not self.login():
                return

            self._gameplay_loop()

        except Exception:
            traceback.print_exc()

        finally:
            self.disconnect()

    def run_authenticated(self):
        """Run gameplay after selector-driven authentication completes."""
        try:
            self._gameplay_loop()

        except Exception:
            traceback.print_exc()

        finally:
            self.disconnect()

    def _gameplay_loop(self):
        if self.player is None:
            return

        self.send("")
        self.send("Welcome, {0}.".format(self.player.name))
        self.send("Ordinary text is spoken aloud.")
        self.send("Commands begin with a slash. Try /help.")
        self.send("More importantly, try /bling.")
        self.send("")

        with self.state_lock:
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

            with self.state_lock:
                if line.startswith("/"):
                    self.handle_command(line)
                else:
                    self.handle_chat(line)

    def disconnect(self):
        if not self.running and self.player is None:
            return

        self.running = False

        if self.player is not None:
            player = self.player

            save_result = self.save_if_changed(
                wait=True,
                timeout=GRACEFUL_FLUSH_SECONDS
            )

            if save_result == "failed":
                sys.stderr.write(
                    "Could not save player state for {0}: {1}\n".format(
                        player.name,
                        self.last_save_error
                    )
                )

            with self.state_lock:
                if player.room is not None:
                    player.room.leave(player)

            key = player.name.lower()

            with SESSIONS_LOCK:
                if SESSIONS.get(key) is self:
                    del SESSIONS[key]

            with self.state_lock:
                player.session = None

                if self.player is player:
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
        tavern = self.add_room(ValsHellaHoller(self.village_state))

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

        green.add_exit("north", tavern)
        tavern.add_exit("south", green)

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


def configured_server_address(environ=None):
    """Return the validated listener configured through the environment."""
    if environ is None:
        environ = os.environ

    host_value = environ.get("BLINGMUD_HOST", HOST)
    port_value = environ.get("BLINGMUD_PORT", str(PORT))

    if not isinstance(host_value, str) or not isinstance(port_value, str):
        raise ValueError("listener configuration must be text")

    host = host_value.strip()
    port_text = port_value.strip()

    if not host or len(host) > 255 or "\x00" in host:
        raise ValueError("BLINGMUD_HOST is invalid")

    try:
        port = int(port_text)
    except (TypeError, ValueError):
        raise ValueError("BLINGMUD_PORT must be an integer")

    if port < 1 or port > 65535:
        raise ValueError("BLINGMUD_PORT must be between 1 and 65535")

    return host, port


def _load_account_for_authentication(name):
    with USERS_LOCK:
        return load_user(name)


def _authenticate_account(account, password, world):
    if not verify_password(password, account["password"]):
        return {"authenticated": False}

    if password_hash_needs_upgrade(account["password"]):
        try:
            upgraded_hash = password_hash(password)

            with USERS_LOCK:
                update_user_password_hash(account["username"], upgraded_hash)
        except (OSError, sqlite3.Error, ValueError) as error:
            sys.stderr.write(
                "Could not upgrade password hash for {0}: {1}\n".format(
                    account["username"],
                    error
                )
            )

    player = Player(account["username"])
    invalid_state = False

    try:
        login_room = restore_player_state(
            player,
            account["state_json"],
            world
        )
    except PlayerStateError:
        sys.stderr.write(
            "Invalid saved state for {0}; using safe defaults.\n".format(
                account["username"]
            )
        )
        invalid_state = True
        login_room = world.starting_room

    return {
        "authenticated": True,
        "player": player,
        "login_room": login_room,
        "invalid_state": invalid_state,
        "stored_state": account["state_json"]
    }


def _new_name_is_available(name):
    with USERS_LOCK:
        return not user_exists(name)


def _create_account_for_authentication(name, password):
    with USERS_LOCK:
        if user_exists(name):
            return False

        try:
            create_user(name, password)
        except sqlite3.IntegrityError:
            return False

    return True


class PreAuthController(object):
    """Line-oriented pre-login state machine owned by the selector."""

    STATE_NAME = "name"
    STATE_PASSWORD = "password"
    STATE_NEW_NAME = "new_name"
    STATE_NEW_PASSWORD = "new_password"
    STATE_CONFIRM_PASSWORD = "confirm_password"

    def __init__(self, server, connection, session):
        self.server = server
        self.connection = connection
        self.session = session
        self.state = self.STATE_NAME
        self.busy = False
        self.account = None
        self.requested_name = None
        self.new_name = None
        self.new_password = None

    def connection_closed(self):
        """Discard authentication-only secrets when the socket closes."""
        self.account = None
        self.requested_name = None
        self.new_name = None
        self.new_password = None

    def start(self):
        self.connection.attach_session(self.session)
        self.connection.set_line_handler(self.on_line)
        self.session.enable_character_mode()
        self.session.send_login_banner()
        self._prompt_name()

    def _prompt(self, text, hidden=False, maximum_length=MAX_INPUT_LENGTH):
        self.session.prompt(
            text,
            hidden=hidden,
            maximum_length=maximum_length
        )

    def _prompt_name(self):
        self.state = self.STATE_NAME
        self.account = None
        self._prompt("Name: ", maximum_length=MAX_USERNAME_INPUT_LENGTH)

    def _prompt_new_name(self):
        self.state = self.STATE_NEW_NAME
        self._prompt(
            "Choose a name: ",
            maximum_length=MAX_USERNAME_INPUT_LENGTH
        )

    def _prompt_password(self):
        self.state = self.STATE_PASSWORD
        self._prompt(
            "Password: ",
            hidden=True,
            maximum_length=MAX_PASSWORD_LENGTH + 1
        )

    def _prompt_new_password(self):
        self.state = self.STATE_NEW_PASSWORD
        self._prompt(
            "Choose a password: ",
            hidden=True,
            maximum_length=MAX_PASSWORD_LENGTH + 1
        )

    def _prompt_confirmation(self):
        self.state = self.STATE_CONFIRM_PASSWORD
        self._prompt(
            "Confirm password: ",
            hidden=True,
            maximum_length=MAX_PASSWORD_LENGTH + 1
        )

    def _submit(self, function, callback, *arguments):
        if self.busy or self.connection.closed:
            return False

        self.busy = True
        self.connection.configure_input(False, 0)

        def completed(result, error):
            self.busy = False

            if self.connection.closed:
                return

            callback(result, error)

        if self.server.auth_pool.submit(
            function,
            completed,
            *arguments
        ):
            return True

        self.busy = False
        self.session.send(
            "The login workers are busy. Please try that line again."
        )
        self._repeat_prompt()
        return False

    def _repeat_prompt(self):
        if self.state == self.STATE_PASSWORD:
            self._prompt_password()
        elif self.state == self.STATE_NEW_NAME:
            self._prompt_new_name()
        elif self.state == self.STATE_NEW_PASSWORD:
            self._prompt_new_password()
        elif self.state == self.STATE_CONFIRM_PASSWORD:
            self._prompt_confirmation()
        else:
            self._prompt_name()

    def on_line(self, line):
        if self.busy or self.connection.closed:
            return

        if self.state == self.STATE_NAME:
            self._handle_name(line)
        elif self.state == self.STATE_PASSWORD:
            self._handle_password(line)
        elif self.state == self.STATE_NEW_NAME:
            self._handle_new_name(line)
        elif self.state == self.STATE_NEW_PASSWORD:
            self._handle_new_password(line)
        elif self.state == self.STATE_CONFIRM_PASSWORD:
            self._handle_confirmation(line)

    def _handle_name(self, line):
        name = line.strip()

        if not name:
            self._prompt_name()
            return

        if name.lower() == "newuser":
            self.session.send("")
            self.session.send("Creating a new BlingMUD user.")
            self._prompt_new_name()
            return

        if not self.server.rate_limiter.authentication_allowed(
            self.connection.ip_address,
            name
        ):
            self.session.send(
                "Too many failed logins for that account from this address. "
                "Please wait five minutes."
            )
            self.connection.request_close_after_output()
            return

        self.requested_name = name
        self._submit(
            _load_account_for_authentication,
            self._account_loaded,
            name
        )

    def _account_loaded(self, account, error):
        if error is not None:
            self.session.send("Login storage is temporarily unavailable.")
            self._prompt_name()
            return

        if account is None:
            self.session.send("No such user. Type NEWUSER to create one.")
            attempts = self.server.rate_limiter.record_authentication_failure(
                self.connection.ip_address,
                self.requested_name
            )

            if attempts >= 5:
                self.session.send(
                    "Too many failed logins. This connection is being closed."
                )
                self.connection.request_close_after_output()
            else:
                self._prompt_name()
            return

        self.account = account
        self._prompt_password()

    def _handle_password(self, password):
        if self.account is None:
            self._prompt_name()
            return

        if len(password) > MAX_PASSWORD_LENGTH:
            self.session.send("That password is too long.")
            self._record_failed_login()
            return

        self._submit(
            _authenticate_account,
            self._authentication_finished,
            self.account,
            password,
            self.session.world
        )

    def _record_failed_login(self):
        attempts = self.server.rate_limiter.record_authentication_failure(
            self.connection.ip_address,
            self.account["username"]
        )

        if attempts >= 5:
            self.session.send(
                "Too many failed logins. This connection is being closed."
            )
            self.connection.request_close_after_output()
        else:
            self._prompt_password()

    def _authentication_finished(self, result, error):
        if error is not None:
            self.session.send("Login verification is temporarily unavailable.")
            self._prompt_password()
            return

        if not result["authenticated"]:
            self.session.send("Incorrect password.")
            self._record_failed_login()
            return

        self._finish_authenticated(
            result["player"],
            result["login_room"],
            result["invalid_state"],
            result["stored_state"]
        )

    def _handle_new_name(self, line):
        name = line.strip()

        if not valid_username(name):
            self.session.send(
                "Names must be 2-20 characters and contain only letters, "
                "numbers, underscores or hyphens."
            )
            self._prompt_new_name()
            return

        self.new_name = name
        self._submit(
            _new_name_is_available,
            self._new_name_checked,
            name
        )

    def _new_name_checked(self, available, error):
        if error is not None:
            self.session.send("Login storage is temporarily unavailable.")
            self._prompt_new_name()
            return

        if not available:
            self.session.send("That name is already registered.")
            self._prompt_new_name()
            return

        self.session.send(
            "DO NOT USE A PASSWORD YOU USE SOMEWHERE ELSE."
        )
        self._prompt_new_password()

    def _handle_new_password(self, password):
        if len(password) > MAX_PASSWORD_LENGTH:
            self.session.send("That password is too long.")
            self._prompt_new_password()
            return

        if len(password) < 12:
            self.session.send("Please use at least twelve characters.")
            self._prompt_new_password()
            return

        self.new_password = password
        self._prompt_confirmation()

    def _handle_confirmation(self, confirmation):
        if len(confirmation) > MAX_PASSWORD_LENGTH:
            self.new_password = None
            self.session.send("That password confirmation is too long.")
            self._prompt_new_password()
            return

        if self.new_password != confirmation:
            self.new_password = None
            self.session.send("The passwords did not match.")
            self._prompt_new_password()
            return

        if not self.server.rate_limiter.claim_account_creation(
            self.connection.ip_address
        ):
            self.new_password = None
            self.session.send(
                "Too many accounts have been created from this address "
                "within the last hour."
            )
            self.connection.request_close_after_output()
            return

        password = self.new_password
        self.new_password = None
        self._submit(
            _create_account_for_authentication,
            self._account_created,
            self.new_name,
            password
        )

    def _account_created(self, created, error):
        if error is not None:
            self.server.rate_limiter.release_account_creation(
                self.connection.ip_address
            )
            self.session.send("The account could not be created right now.")
            self._prompt_new_name()
            return

        if not created:
            self.server.rate_limiter.release_account_creation(
                self.connection.ip_address
            )
            self.session.send(
                "Someone registered that name while you were typing."
            )
            self._prompt_new_name()
            return

        player = Player(self.new_name)
        self.session.send("Account created.")
        self._finish_authenticated(
            player,
            self.session.world.starting_room,
            False,
            new_player_state_json()
        )

    def _finish_authenticated(
        self,
        player,
        login_room,
        invalid_state,
        stored_state
    ):
        key = player.name.lower()

        with SESSIONS_LOCK:
            if key in SESSIONS:
                self.session.send("That user is already connected.")
                self._prompt_name()
                return

            if not self.server.promote_authenticated(self.connection):
                self.session.send(
                    "The authenticated-player limit has been reached."
                )
                self.connection.request_close_after_output()
                return

            self.session.player = player
            self.session.login_room = login_room
            player.session = self.session
            SESSIONS[key] = self.session

        if invalid_state:
            self.session.send(
                "Your saved character state was invalid, so this session "
                "is starting from safe defaults."
            )

        self.server.rate_limiter.clear_authentication_failures(
            self.connection.ip_address,
            player.name
        )
        self.session.set_persisted_state(stored_state)
        self.account = None
        self.requested_name = None
        self.new_name = None
        self.connection.set_line_handler(None)
        self.connection.configure_input(False, MAX_INPUT_LENGTH)
        self.session.start_gameplay_worker()


def begin_selector_connection(server, connection):
    session = Session(
        connection,
        connection.address,
        WORLD,
        persistence_writer=PERSISTENCE_WRITER
    )
    controller = PreAuthController(server, connection, session)
    connection.auth_controller = controller
    controller.start()


def main():
    global ADMIN_PASSWORD_HASH
    global NPC_MANAGER
    global PERSISTENCE_WRITER
    global AUTOSAVE_COORDINATOR

    try:
        host, port = configured_server_address()
    except ValueError as error:
        sys.stderr.write("Configuration error: {0}\n".format(error))
        return 2

    init_user_database()

    PERSISTENCE_WRITER = PersistenceWriter(persist_user_state)
    PERSISTENCE_WRITER.start()
    AUTOSAVE_COORDINATOR = AutosaveCoordinator(active_sessions_snapshot)

    if os.path.exists("admin.hash"):
        with open("admin.hash", "r") as f:
            ADMIN_PASSWORD_HASH = f.read().strip()

        print("Admin password loaded.")
    else:
        print("WARNING: admin.hash not found.")
        print("         Administrative commands are disabled.")


    print("")
    print("*** ACCEPTED PLAINTEXT TRANSPORT RISK ***")

    for line in PLAINTEXT_TELNET_WARNING:
        print(line)

    print("No TLS or encrypted transport is implemented by this server.")
    print("")

    server = SelectorMudServer(
        (host, port),
        begin_selector_connection
    )
    server.add_maintenance_callback(AUTOSAVE_COORDINATOR.tick)

    try:
        server.bind()
    except OSError as error:
        server.server_close()
        PERSISTENCE_WRITER.shutdown(GRACEFUL_FLUSH_SECONDS)
        PERSISTENCE_WRITER = None
        AUTOSAVE_COORDINATOR = None
        sys.stderr.write("Could not bind BlingMUD listener: {0}\n".format(error))
        return 1

    print("BLINGMUD listening on {0}:{1}".format(host, port))
    print("Connect with: telnet localhost {0}".format(port))
    print("Press Ctrl-C to stop.")

    try:
        NPC_MANAGER.start()
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("Shutting down BLINGMUD.")
    finally:
        NPC_MANAGER.stop()
        sessions = active_sessions_snapshot()
        server.shutdown()
        server.server_close()

        deadline = time.monotonic() + GRACEFUL_FLUSH_SECONDS

        for session in sessions:
            worker = session.gameplay_thread

            if worker is None or worker is threading.current_thread():
                continue

            remaining = deadline - time.monotonic()

            if remaining <= 0:
                break

            worker.join(remaining)

        if any(
            session.gameplay_thread is not None
            and session.gameplay_thread.is_alive()
            for session in sessions
        ):
            sys.stderr.write(
                "One or more gameplay workers did not stop within ten "
                "seconds.\n"
            )

        remaining = max(0.0, deadline - time.monotonic())

        if not PERSISTENCE_WRITER.flush(remaining):
            sys.stderr.write(
                "Persistence flush did not finish within ten seconds.\n"
            )

        remaining = max(0.0, deadline - time.monotonic())

        if not PERSISTENCE_WRITER.shutdown(remaining):
            sys.stderr.write(
                "Persistence writer did not stop within ten seconds.\n"
            )

        PERSISTENCE_WRITER = None
        AUTOSAVE_COORDINATOR = None

    return 0

if __name__ == "__main__":
    sys.exit(main())
