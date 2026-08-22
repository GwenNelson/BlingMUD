"""Bounded selector-based network runtime for BlingMUD.

The selector owns every network socket.  Gameplay code sees a small
socket-like connection object, so Session can retain its straightforward,
sequential read/send API without giving every unauthenticated connection a
thread.
"""

import collections
import concurrent.futures
import errno
import queue
import selectors
import socket
import sys
import threading
import time
import traceback

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


TOTAL_CONNECTION_LIMIT = 64
PREAUTH_CONNECTION_LIMIT = 32
AUTHENTICATED_CONNECTION_LIMIT = 32
PER_IP_CONNECTION_LIMIT = 8
PREAUTH_IDLE_SECONDS = 120.0
AUTHENTICATED_IDLE_WARNING_SECONDS = 10.0 * 60.0 * 60.0
AUTHENTICATED_IDLE_DISCONNECT_SECONDS = 12.0 * 60.0 * 60.0
OUTPUT_QUEUE_LIMIT = 256 * 1024
# One extra byte lets callers detect and reject a 4097-byte password while
# ordinary gameplay lines remain capped at 4096 by Session.
INPUT_LINE_LIMIT = 4097
INPUT_QUEUE_LIMIT = 64
AUTH_WORKERS = 2
AUTH_QUEUE_LIMIT = 16
AUTH_FAILURE_LIMIT = 5
AUTH_FAILURE_WINDOW_SECONDS = 5.0 * 60.0
ACCOUNT_CREATION_LIMIT = 3
ACCOUNT_CREATION_WINDOW_SECONDS = 60.0 * 60.0
SELECT_TIMEOUT_SECONDS = 0.25

class AuthRateLimiter(object):
    """Track bounded authentication failures and account creations."""

    def __init__(self, time_source=None):
        self.time_source = time_source or time.monotonic
        self.lock = threading.RLock()
        self.auth_failures = {}
        self.account_creations = {}

    def _recent(self, records, key, window, now):
        timestamps = records.get(key)

        if timestamps is None:
            return collections.deque()

        threshold = now - window

        while timestamps and timestamps[0] <= threshold:
            timestamps.popleft()

        if not timestamps:
            records.pop(key, None)

        return timestamps

    def authentication_allowed(self, ip_address, account_name):
        key = (str(ip_address), str(account_name).lower())

        with self.lock:
            attempts = self._recent(
                self.auth_failures,
                key,
                AUTH_FAILURE_WINDOW_SECONDS,
                self.time_source()
            )
            return len(attempts) < AUTH_FAILURE_LIMIT

    def record_authentication_failure(self, ip_address, account_name):
        key = (str(ip_address), str(account_name).lower())

        with self.lock:
            now = self.time_source()
            attempts = self._recent(
                self.auth_failures,
                key,
                AUTH_FAILURE_WINDOW_SECONDS,
                now
            )

            if key not in self.auth_failures:
                self.auth_failures[key] = attempts

            attempts.append(now)
            return len(attempts)

    def clear_authentication_failures(self, ip_address, account_name):
        key = (str(ip_address), str(account_name).lower())

        with self.lock:
            self.auth_failures.pop(key, None)

    def claim_account_creation(self, ip_address):
        key = str(ip_address)

        with self.lock:
            now = self.time_source()
            creations = self._recent(
                self.account_creations,
                key,
                ACCOUNT_CREATION_WINDOW_SECONDS,
                now
            )

            if len(creations) >= ACCOUNT_CREATION_LIMIT:
                return False

            if key not in self.account_creations:
                self.account_creations[key] = creations

            creations.append(now)
            return True

    def release_account_creation(self, ip_address):
        key = str(ip_address)

        with self.lock:
            creations = self.account_creations.get(key)

            if not creations:
                return

            creations.pop()

            if not creations:
                self.account_creations.pop(key, None)


class BoundedWorkerPool(object):
    """Small worker pool whose pending work cannot grow without bound."""

    def __init__(
        self,
        workers=AUTH_WORKERS,
        queued=AUTH_QUEUE_LIMIT,
        wake_callback=None
    ):
        if workers <= 0 or queued < 0:
            raise ValueError("worker and queue limits must be non-negative")

        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="blingmud-auth"
        )
        self.capacity = threading.BoundedSemaphore(workers + queued)
        self.completed = queue.Queue()
        self.wake_callback = wake_callback
        self.closed = False
        self.lock = threading.RLock()

    def submit(self, function, callback, *arguments):
        with self.lock:
            if self.closed or not self.capacity.acquire(blocking=False):
                return False

            try:
                future = self.executor.submit(function, *arguments)
            except Exception:
                self.capacity.release()
                raise

        future.add_done_callback(
            lambda completed: self._completed(completed, callback)
        )
        return True

    def _completed(self, future, callback):
        self.completed.put((future, callback))

        if self.wake_callback is not None:
            self.wake_callback()

    def drain(self):
        while True:
            try:
                future, callback = self.completed.get_nowait()
            except queue.Empty:
                return

            self.capacity.release()

            try:
                result = future.result()
            except Exception as error:
                try:
                    callback(None, error)
                except Exception:
                    traceback.print_exc(file=sys.stderr)
            else:
                try:
                    callback(result, None)
                except Exception:
                    traceback.print_exc(file=sys.stderr)

    def shutdown(self):
        with self.lock:
            if self.closed:
                return

            self.closed = True

        self.executor.shutdown(wait=True, cancel_futures=True)
        self.drain()


class ConnectionAdmission(object):
    """Pure connection-limit policy, separated for inspection and tests."""

    def rejection_reason(self, connections, ip_address):
        open_connections = [
            connection
            for connection in connections
            if not connection.closed
        ]

        if len(open_connections) >= TOTAL_CONNECTION_LIMIT:
            return "The server has reached its connection limit."

        from_ip = [
            connection
            for connection in open_connections
            if connection.ip_address == ip_address
        ]

        if len(from_ip) >= PER_IP_CONNECTION_LIMIT:
            return "Too many connections are already open from your address."

        authenticated = [
            connection
            for connection in open_connections
            if connection.authenticated
        ]

        if len(authenticated) >= AUTHENTICATED_CONNECTION_LIMIT:
            return "The authenticated-player limit has been reached."

        preauth = [
            connection
            for connection in open_connections
            if not connection.authenticated
        ]

        if len(preauth) >= PREAUTH_CONNECTION_LIMIT:
            return "The login connection limit has been reached."

        return None

    def can_promote(self, connections, wanted_connection):
        authenticated = [
            connection
            for connection in connections
            if (
                not connection.closed
                and connection.authenticated
                and connection is not wanted_connection
            )
        ]
        return len(authenticated) < AUTHENTICATED_CONNECTION_LIMIT


class SelectorConnection(object):
    """Thread-safe bridge between one socket and one sequential Session."""

    LINE_CLOSED = object()

    def __init__(self, server, client_socket, address, time_source=None):
        self.server = server
        self.socket = client_socket
        self.address = address
        self.ip_address = str(address[0])
        self.time_source = time_source or time.monotonic
        self.created_at = self.time_source()
        self.last_input_at = self.created_at
        self.authenticated = False
        self.idle_warning_sent = False
        self.closed = False
        self.close_requested = False
        self.close_after_output = False
        self.close_after_output_deadline = None
        self.session = None
        self.line_handler = None
        self.input_hidden = False
        self.input_limit = INPUT_LINE_LIMIT
        self.input_lock = threading.RLock()
        self.input_parser = TelnetInputParser(INPUT_LINE_LIMIT)
        self.output_buffer = bytearray()
        self.output_lock = threading.RLock()
        self.input_lines = queue.Queue(maxsize=INPUT_QUEUE_LIMIT)

    def fileno(self):
        return self.socket.fileno()

    def attach_session(self, session):
        self.session = session

    def set_line_handler(self, handler):
        self.line_handler = handler

    def configure_input(self, hidden=False, maximum_length=INPUT_LINE_LIMIT):
        if maximum_length is None:
            maximum_length = INPUT_LINE_LIMIT

        maximum_length = max(0, min(int(maximum_length), INPUT_LINE_LIMIT))
        with self.input_lock:
            self.input_hidden = bool(hidden)
            self.input_limit = maximum_length
            self.input_parser.set_maximum_length(maximum_length)

    def replace_current_input(self, expected_text, replacement):
        """Atomically replace only the input that produced a Tab event."""
        with self.input_lock:
            if self.input_parser.current_text != expected_text:
                return None

            return self.input_parser.replace_current_text(replacement)

    def sendall(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("network output must be bytes")

        with self.output_lock:
            if self.closed or self.close_requested:
                return

            if len(self.output_buffer) + len(data) > OUTPUT_QUEUE_LIMIT:
                self.close_requested = True
                self.server.request_close(self)
                raise BufferError("connection output queue limit exceeded")

            self.output_buffer.extend(data)

        self.server.wake()

    def has_output(self):
        with self.output_lock:
            return bool(self.output_buffer)

    def peek_output(self, maximum=65536):
        with self.output_lock:
            return bytes(self.output_buffer[:maximum])

    def discard_output(self, amount):
        with self.output_lock:
            del self.output_buffer[:amount]

    def shutdown(self, how):
        self.request_close()

    def close(self):
        self.request_close()

    def request_close(self):
        if self.close_requested or self.closed:
            return

        self.close_requested = True
        self.server.request_close(self)

    def request_close_after_output(self, grace_seconds=1.0):
        if self.close_requested or self.closed:
            return

        self.close_after_output = True
        self.close_after_output_deadline = self.time_source() + max(
            0.0,
            float(grace_seconds)
        )
        self.server.wake()

    def mark_closed(self):
        if self.closed:
            return

        self.closed = True
        self.close_requested = True
        self.close_after_output = False

        if self.session is not None:
            self.session.running = False

        controller = getattr(self, "auth_controller", None)

        if controller is not None:
            controller.connection_closed()

        while True:
            try:
                self.input_lines.get_nowait()
            except queue.Empty:
                break

        self.input_lines.put_nowait(self.LINE_CLOSED)

    def read_line(self, hidden=False, maximum_length=INPUT_LINE_LIMIT):
        self.configure_input(hidden, maximum_length)
        line = self.input_lines.get()

        if line is self.LINE_CLOSED:
            return None

        return line

    def _queue_output_without_failure(self, data):
        try:
            self.sendall(data)
        except BufferError:
            pass

    def _update_session_input(self, text, hidden):
        if self.session is None:
            return

        with self.session.send_lock:
            self.session.current_input = text
            self.session.input_active = True
            self.session.input_hidden = hidden

    def _deliver_line(self, line):
        self._queue_output_without_failure(b"\r\n")

        if self.session is not None:
            with self.session.send_lock:
                self.session.current_input = ""
                self.session.prompt_text = ""
                self.session.input_active = False
                self.session.input_hidden = False

        if self.authenticated:
            try:
                self.input_lines.put_nowait(line)
            except queue.Full:
                self.request_close()
        elif self.line_handler is not None:
            try:
                self.line_handler(line)
            except Exception:
                sys.stderr.write(
                    "Pre-authentication input handler failed; closing "
                    "that connection.\n"
                )
                traceback.print_exc(file=sys.stderr)
                self.request_close()

    def _deliver_tab(self, event):
        if not self.authenticated:
            self._queue_output_without_failure(b"\a")
            return

        try:
            self.input_lines.put_nowait(event)
        except queue.Full:
            self.request_close()

    def feed_received(self, data):
        """Process incremental Telnet and UTF-8 input events."""
        if not data or self.closed:
            return

        self.last_input_at = self.time_source()
        self.idle_warning_sent = False

        with self.input_lock:
            hidden = self.input_hidden
            events = self.input_parser.feed(data)

        for event in events:
            if isinstance(event, TextInputEvent):
                self._update_session_input(event.current_text, hidden)

                if not hidden:
                    self._queue_output_without_failure(
                        event.text.encode("utf-8", "replace")
                    )
            elif isinstance(event, BackspaceInputEvent):
                self._update_session_input(event.current_text, hidden)

                if not hidden:
                    self._queue_output_without_failure(b"\b \b")
            elif isinstance(event, LineInputEvent):
                self._deliver_line(event.text)
            elif isinstance(event, TabInputEvent):
                self._deliver_tab(event)

    def idle_action(self, now):
        idle_for = max(0.0, now - self.last_input_at)

        if not self.authenticated:
            if idle_for >= PREAUTH_IDLE_SECONDS:
                return "disconnect"
            return None

        if idle_for >= AUTHENTICATED_IDLE_DISCONNECT_SECONDS:
            return "disconnect"

        if (
            idle_for >= AUTHENTICATED_IDLE_WARNING_SECONDS
            and not self.idle_warning_sent
        ):
            self.idle_warning_sent = True
            return "warn"

        return None


class SelectorMudServer(object):
    """Own sockets in one selector; delegate only bounded work to threads."""

    allow_reuse_address = True

    def __init__(
        self,
        address,
        connection_started,
        time_source=None,
        selector_factory=None,
        socket_factory=None
    ):
        self.address = address
        self.connection_started = connection_started
        self.time_source = time_source or time.monotonic
        self.selector = (selector_factory or selectors.DefaultSelector)()
        self.socket_factory = socket_factory or socket.socket
        self.listener = None
        self.connections = set()
        self.admission = ConnectionAdmission()
        self.rate_limiter = AuthRateLimiter(self.time_source)
        self.control_queue = queue.Queue()
        self.maintenance_callbacks = []
        self.stopping = threading.Event()
        self.owner_thread = None
        self.wake_reader, self.wake_writer = socket.socketpair()
        self.wake_reader.setblocking(False)
        self.wake_writer.setblocking(False)
        self.selector.register(self.wake_reader, selectors.EVENT_READ, None)
        self.auth_pool = BoundedWorkerPool(
            AUTH_WORKERS,
            AUTH_QUEUE_LIMIT,
            self.wake
        )

    def bind(self):
        if self.listener is not None:
            return

        listener = self.socket_factory(socket.AF_INET, socket.SOCK_STREAM)

        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(self.address)
            listener.listen()
            listener.setblocking(False)
            self.selector.register(
                listener,
                selectors.EVENT_READ,
                "listener"
            )
        except Exception:
            listener.close()
            raise

        self.listener = listener

    def wake(self):
        try:
            self.wake_writer.send(b"x")
        except OSError as error:
            if error.errno not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EBADF):
                raise

    def request_close(self, connection):
        self.control_queue.put(("close", connection))
        self.wake()

    def add_maintenance_callback(self, callback):
        if not callable(callback):
            raise TypeError("maintenance callback must be callable")

        self.maintenance_callbacks.append(callback)

    def promote_authenticated(self, connection):
        if not self.admission.can_promote(self.connections, connection):
            return False

        connection.authenticated = True
        return True

    def _reject_socket(self, client_socket, reason):
        try:
            client_socket.send(
                ("BlingMUD cannot accept this connection: {0}\r\n".format(
                    reason
                )).encode("utf-8", "replace")
            )
        except OSError:
            pass

        try:
            client_socket.close()
        except OSError:
            pass

    def _accept_ready(self):
        while True:
            try:
                client_socket, address = self.listener.accept()
            except BlockingIOError:
                return

            client_socket.setblocking(False)
            ip_address = str(address[0])
            reason = self.admission.rejection_reason(
                self.connections,
                ip_address
            )

            if reason is not None:
                self._reject_socket(client_socket, reason)
                continue

            connection = SelectorConnection(
                self,
                client_socket,
                address,
                self.time_source
            )
            self.connections.add(connection)
            self.selector.register(
                client_socket,
                selectors.EVENT_READ,
                connection
            )

            try:
                self.connection_started(self, connection)
            except Exception:
                sys.stderr.write(
                    "Connection initialization failed; closing that "
                    "connection.\n"
                )
                traceback.print_exc(file=sys.stderr)
                self._close_connection(connection)

    def _read_ready(self, connection):
        try:
            data = connection.socket.recv(65536)
        except BlockingIOError:
            return
        except OSError:
            self._close_connection(connection)
            return

        if not data:
            self._close_connection(connection)
            return

        connection.feed_received(data)

    def _write_ready(self, connection):
        data = connection.peek_output()

        if not data:
            return

        try:
            sent = connection.socket.send(data)
        except BlockingIOError:
            return
        except OSError:
            self._close_connection(connection)
            return

        if sent:
            connection.discard_output(sent)

    def _sync_interest(self, connection):
        if connection.closed:
            return

        events = selectors.EVENT_READ

        if connection.has_output():
            events |= selectors.EVENT_WRITE

        try:
            self.selector.modify(connection.socket, events, connection)
        except (KeyError, ValueError, OSError):
            self._close_connection(connection)

    def _drain_waker(self):
        while True:
            try:
                if not self.wake_reader.recv(4096):
                    return
            except BlockingIOError:
                return
            except OSError:
                return

    def _drain_controls(self):
        while True:
            try:
                action, connection = self.control_queue.get_nowait()
            except queue.Empty:
                return

            if action == "close":
                self._close_connection(connection)

    def _close_connection(self, connection):
        if connection.closed:
            self.connections.discard(connection)
            return

        try:
            self.selector.unregister(connection.socket)
        except Exception:
            pass

        try:
            connection.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

        try:
            connection.socket.close()
        except OSError:
            pass

        connection.mark_closed()
        self.connections.discard(connection)

    def _check_idle_connections(self):
        now = self.time_source()

        for connection in list(self.connections):
            if connection.close_after_output:
                if (
                    not connection.has_output()
                    or now >= connection.close_after_output_deadline
                ):
                    self._close_connection(connection)
                continue

            action = connection.idle_action(now)

            if action == "warn" and connection.session is not None:
                connection.session.send(
                    "\aYou have been idle for ten hours. Activity within "
                    "two hours is required to remain connected."
                )
            elif action == "disconnect":
                if connection.session is not None:
                    connection.session.send(
                        "This idle connection is being closed."
                    )
                    connection.request_close_after_output()
                else:
                    self._close_connection(connection)

    def _run_maintenance(self):
        for callback in list(self.maintenance_callbacks):
            try:
                callback()
            except Exception:
                sys.stderr.write(
                    "Selector maintenance callback failed.\n"
                )
                traceback.print_exc(file=sys.stderr)

    def serve_once(self, timeout=SELECT_TIMEOUT_SECONDS):
        self.auth_pool.drain()
        self._drain_controls()

        for connection in list(self.connections):
            self._sync_interest(connection)

        for key, mask in self.selector.select(timeout):
            if key.fileobj is self.wake_reader:
                self._drain_waker()
            elif key.data == "listener":
                self._accept_ready()
            else:
                connection = key.data

                if mask & selectors.EVENT_READ:
                    self._read_ready(connection)

                if not connection.closed and mask & selectors.EVENT_WRITE:
                    self._write_ready(connection)

        self.auth_pool.drain()
        self._drain_controls()
        self._check_idle_connections()
        self._run_maintenance()

    def serve_forever(self):
        self.bind()
        self.owner_thread = threading.current_thread()

        while not self.stopping.is_set():
            self.serve_once()

    def shutdown(self):
        self.stopping.set()
        self.wake()

    def server_close(self):
        self.shutdown()

        for connection in list(self.connections):
            self._close_connection(connection)

        if self.listener is not None:
            try:
                self.selector.unregister(self.listener)
            except Exception:
                pass

            try:
                self.listener.close()
            except OSError:
                pass

            self.listener = None

        self.auth_pool.shutdown()

        for wake_socket in (self.wake_reader, self.wake_writer):
            try:
                wake_socket.close()
            except OSError:
                pass

        self.selector.close()

    def connection_snapshot(self):
        return {
            "total": len(self.connections),
            "preauth": len([
                connection
                for connection in self.connections
                if not connection.authenticated
            ]),
            "authenticated": len([
                connection
                for connection in self.connections
                if connection.authenticated
            ])
        }
