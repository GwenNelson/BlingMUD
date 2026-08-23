"""Bounded Generic MUD Communication Protocol framing and state."""

import json
import re
import threading


GMCP_OPTION = 201
GMCP_MAX_MESSAGE_BYTES = 16 * 1024
GMCP_MAX_PACKAGE_LENGTH = 128
GMCP_MAX_IDENTITY_LENGTH = 128
GMCP_MAX_SUBSCRIPTIONS = 64
GMCP_MAX_VERSION = 1000000

IAC = 255
SB = 250
SE = 240

NO_PAYLOAD = object()

_PACKAGE_PATTERN = re.compile(r"^[A-Za-z]+(?:\.[A-Za-z]+)*$")
_SUBSCRIPTION_PATTERN = re.compile(
    r"^([A-Za-z]+(?:\.[A-Za-z]+)*) ([1-9][0-9]*)$"
)


class GmcpError(ValueError):
    pass


class GmcpAction(object):
    """Result of one inbound GMCP event."""

    def __init__(self, refresh=False, responses=()):
        self.refresh = bool(refresh)
        self.responses = tuple(responses)


def validate_package(package):
    if not isinstance(package, str):
        raise GmcpError("GMCP package must be text")

    if (
        not package
        or len(package) > GMCP_MAX_PACKAGE_LENGTH
        or _PACKAGE_PATTERN.match(package) is None
    ):
        raise GmcpError("GMCP package is invalid")

    return package


def encode_gmcp(package, payload=NO_PAYLOAD):
    """Encode one complete GMCP Telnet subnegotiation."""
    package = validate_package(package)
    body = package.encode("ascii")

    if payload is not NO_PAYLOAD:
        try:
            encoded_payload = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":")
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise GmcpError("GMCP payload is not valid JSON") from error

        body += b" " + encoded_payload

    if len(body) > GMCP_MAX_MESSAGE_BYTES:
        raise GmcpError("GMCP message is too large")

    body = body.replace(bytes((IAC,)), bytes((IAC, IAC)))
    return bytes((IAC, SB, GMCP_OPTION)) + body + bytes((IAC, SE))


def _decode_envelope(data):
    if not isinstance(data, (bytes, bytearray)):
        raise GmcpError("GMCP data must be bytes")

    if len(data) > GMCP_MAX_MESSAGE_BYTES:
        raise GmcpError("GMCP message is too large")

    try:
        text = bytes(data).decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise GmcpError("GMCP message is not UTF-8") from error

    if " " not in text:
        return validate_package(text), NO_PAYLOAD

    package, payload_text = text.split(" ", 1)

    if not payload_text:
        raise GmcpError("GMCP JSON payload is empty")

    return validate_package(package), payload_text


def decode_gmcp(data):
    """Decode a bounded GMCP subnegotiation body."""
    package, payload_text = _decode_envelope(data)

    if payload_text is NO_PAYLOAD:
        return package, NO_PAYLOAD

    try:
        payload = json.loads(payload_text)
    except (ValueError, RecursionError) as error:
        raise GmcpError("GMCP JSON payload is invalid") from error

    return package, payload


class GmcpProtocol(object):
    """Track negotiated state, client identity, and package subscriptions."""

    def __init__(self):
        self.lock = threading.RLock()
        self.enabled = False
        self.client_name = None
        self.client_version = None
        self.subscriptions = {}

    def handle_negotiation(self, command, option, do_command, dont_command):
        if option != GMCP_OPTION:
            return GmcpAction()

        with self.lock:
            if command == do_command:
                changed = not self.enabled
                self.enabled = True
                return GmcpAction(refresh=changed)

            if command == dont_command:
                changed = self.enabled or bool(self.subscriptions)
                self.enabled = False
                self.subscriptions = {}
                return GmcpAction(refresh=changed)

        return GmcpAction()

    @staticmethod
    def _identity_value(payload, wanted):
        for key, value in payload.items():
            if isinstance(key, str) and key.lower() == wanted:
                if (
                    isinstance(value, str)
                    and value
                    and len(value) <= GMCP_MAX_IDENTITY_LENGTH
                ):
                    return value
                return None
        return None

    @staticmethod
    def _parse_subscriptions(payload):
        if not isinstance(payload, list):
            return None

        parsed = {}

        for entry in payload:
            if not isinstance(entry, str):
                return None

            matched = _SUBSCRIPTION_PATTERN.match(entry)

            if matched is None:
                return None

            version = int(matched.group(2))

            if version > GMCP_MAX_VERSION:
                return None

            parsed[matched.group(1).lower()] = version

            if len(parsed) > GMCP_MAX_SUBSCRIPTIONS:
                return None

        return parsed

    def handle_message(self, data):
        with self.lock:
            if not self.enabled:
                return GmcpAction()

        try:
            package, payload_text = _decode_envelope(data)
        except GmcpError:
            return GmcpAction()

        lowered = package.lower()
        supported = {
            "core.hello",
            "core.supports.set",
            "core.supports.add",
            "core.supports.remove",
            "core.ping",
            "core.keepalive"
        }

        if lowered not in supported:
            return GmcpAction()

        if payload_text is NO_PAYLOAD:
            payload = NO_PAYLOAD
        else:
            try:
                payload = json.loads(payload_text)
            except (ValueError, RecursionError):
                return GmcpAction()

        with self.lock:
            if lowered == "core.hello":
                if not isinstance(payload, dict):
                    return GmcpAction()

                client_name = self._identity_value(payload, "client")
                client_version = self._identity_value(payload, "version")

                if client_name is None or client_version is None:
                    return GmcpAction()

                self.client_name = client_name
                self.client_version = client_version
                return GmcpAction()

            if lowered in (
                "core.supports.set",
                "core.supports.add",
                "core.supports.remove"
            ):
                previous = dict(self.subscriptions)

                if lowered == "core.supports.remove":
                    if not isinstance(payload, list):
                        return GmcpAction()

                    removed = []

                    for entry in payload:
                        try:
                            removed.append(validate_package(entry).lower())
                        except GmcpError:
                            return GmcpAction()

                    if len(removed) > GMCP_MAX_SUBSCRIPTIONS:
                        return GmcpAction()

                    for package_name in removed:
                        self.subscriptions.pop(package_name, None)
                else:
                    parsed = self._parse_subscriptions(payload)

                    if parsed is None:
                        return GmcpAction()

                    if lowered == "core.supports.set":
                        self.subscriptions = parsed
                    else:
                        combined = dict(self.subscriptions)
                        combined.update(parsed)

                        if len(combined) > GMCP_MAX_SUBSCRIPTIONS:
                            return GmcpAction()

                        self.subscriptions = combined

                return GmcpAction(
                    refresh=self.subscriptions != previous
                )

            if lowered == "core.ping":
                return GmcpAction(responses=(("Core.Ping", NO_PAYLOAD),))

            if lowered == "core.keepalive":
                return GmcpAction()

        return GmcpAction()

    def supports(self, package):
        package = validate_package(package).lower()

        with self.lock:
            if not self.enabled:
                return False

            for subscribed in self.subscriptions:
                if package == subscribed or package.startswith(subscribed + "."):
                    return True

        return False
