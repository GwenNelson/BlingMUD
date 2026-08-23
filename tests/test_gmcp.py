import unittest

import blingmud
from core import Player, Room
from gmcp import (
    GMCP_MAX_MESSAGE_BYTES,
    GMCP_OPTION,
    GmcpError,
    GmcpProtocol,
    NO_PAYLOAD,
    decode_gmcp,
    encode_gmcp
)
from telnet_parser import (
    DONT,
    DO,
    IAC,
    SB,
    SE,
    TelnetNegotiationEvent,
    TelnetSubnegotiationEvent
)


class RecordingRequest(object):
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)

    def shutdown(self, how):
        pass

    def close(self):
        pass


def decode_wire_message(data):
    prefix = bytes((IAC, SB, GMCP_OPTION))
    suffix = bytes((IAC, SE))
    if not data.startswith(prefix) or not data.endswith(suffix):
        raise AssertionError("not a GMCP wire message")
    body = data[len(prefix):-len(suffix)].replace(
        bytes((IAC, IAC)),
        bytes((IAC,))
    )
    return decode_gmcp(body)


class GmcpCodecTests(unittest.TestCase):
    def test_message_is_compact_utf8_telnet_subnegotiation(self):
        encoded = encode_gmcp("Char.Name", {"name": "Café"})

        self.assertEqual(
            encoded,
            bytes((IAC, SB, GMCP_OPTION))
            + 'Char.Name {"name":"Café"}'.encode("utf-8")
            + bytes((IAC, SE))
        )
        self.assertEqual(
            decode_wire_message(encoded),
            ("Char.Name", {"name": "Café"})
        )

    def test_no_payload_and_invalid_or_oversized_messages_are_bounded(self):
        package, payload = decode_wire_message(encode_gmcp("Core.Ping"))
        self.assertEqual(package, "Core.Ping")
        self.assertIs(payload, NO_PAYLOAD)

        for package_name in ("", "Bad Package", "Bad.1"):
            with self.assertRaises(GmcpError):
                encode_gmcp(package_name)

        with self.assertRaises(GmcpError):
            encode_gmcp("Core.Hello", "x" * GMCP_MAX_MESSAGE_BYTES)

        with self.assertRaises(GmcpError):
            decode_gmcp(b"Core.Hello {")


class GmcpProtocolTests(unittest.TestCase):
    def setUp(self):
        self.protocol = GmcpProtocol()

    def test_negotiation_identity_subscriptions_ping_and_disable(self):
        action = self.protocol.handle_negotiation(
            DO,
            GMCP_OPTION,
            DO,
            DONT
        )
        self.assertTrue(action.refresh)

        self.protocol.handle_message(
            b'Core.Hello {"Client":"Mudlet","Version":"4.0"}'
        )
        self.assertEqual(self.protocol.client_name, "Mudlet")
        self.assertEqual(self.protocol.client_version, "4.0")

        action = self.protocol.handle_message(
            b'Core.Supports.Set ["Char 1","Room.Info 1"]'
        )
        self.assertTrue(action.refresh)
        unchanged = self.protocol.handle_message(
            b'Core.Supports.Set ["Char 1","Room.Info 1"]'
        )
        self.assertFalse(unchanged.refresh)
        self.assertTrue(self.protocol.supports("Char.Vitals"))
        self.assertTrue(self.protocol.supports("Room.Info"))
        self.assertFalse(self.protocol.supports("Room.Players"))

        self.protocol.handle_message(b'Core.Supports.Add ["Room 1"]')
        self.assertTrue(self.protocol.supports("Room.Players"))
        self.protocol.handle_message(b'Core.Supports.Remove ["Char"]')
        self.assertFalse(self.protocol.supports("Char.Vitals"))

        ping = self.protocol.handle_message(b"Core.Ping")
        self.assertEqual(ping.responses, (("Core.Ping", NO_PAYLOAD),))

        disabled = self.protocol.handle_negotiation(
            DONT,
            GMCP_OPTION,
            DO,
            DONT
        )
        self.assertTrue(disabled.refresh)
        self.assertFalse(self.protocol.enabled)
        self.assertFalse(self.protocol.subscriptions)

    def test_malformed_and_unnegotiated_messages_are_ignored(self):
        self.protocol.handle_message(b'Core.Supports.Set ["Char 1"]')
        self.assertFalse(self.protocol.subscriptions)

        self.protocol.handle_negotiation(DO, GMCP_OPTION, DO, DONT)
        for message in (
            b'Core.Supports.Set ["Char zero"]',
            b'Core.Supports.Set [1]',
            b'Core.Hello {"client":"Mudlet"}',
            b"Unknown.Package not-json"
        ):
            self.protocol.handle_message(message)

        self.assertFalse(self.protocol.subscriptions)
        self.assertIsNone(self.protocol.client_name)


class GmcpSessionTests(unittest.TestCase):
    def setUp(self):
        self.world = blingmud.WORLD
        self.request = RecordingRequest()
        self.session = blingmud.Session(
            self.request,
            ("127.0.0.1", 1),
            self.world
        )
        self.player = Player("Mapper")
        self.player.session = self.session
        self.session.player = self.player
        self.world.starting_room.enter(self.player, announce=False)

    def tearDown(self):
        if self.player.room is not None:
            self.player.room.leave(self.player, announce=False)

    def _negotiate_and_subscribe(self):
        self.session.handle_telnet_event(
            TelnetNegotiationEvent(DO, GMCP_OPTION)
        )
        self.session.handle_telnet_event(
            TelnetSubnegotiationEvent(
                GMCP_OPTION,
                b'Core.Supports.Set ["Char 1","Room 1"]'
            )
        )

    def _messages(self):
        return [decode_wire_message(data) for data in self.request.sent]

    def test_connection_negotiation_advertises_gmcp_and_ping_round_trips(self):
        self.session.enable_character_mode()
        self.assertTrue(self.request.sent[-1].endswith(
            bytes((IAC, 251, GMCP_OPTION))
        ))

        self.request.sent = []
        self.session.handle_telnet_event(
            TelnetNegotiationEvent(DO, GMCP_OPTION)
        )
        self.session.handle_telnet_event(
            TelnetSubnegotiationEvent(GMCP_OPTION, b"Core.Ping")
        )
        package, payload = decode_wire_message(self.request.sent[-1])
        self.assertEqual(package, "Core.Ping")
        self.assertIs(payload, NO_PAYLOAD)

    def test_initial_snapshots_are_subscribed_and_mapper_compatible(self):
        self.assertEqual(self.session.flush_gmcp(force=True), 0)
        self._negotiate_and_subscribe()
        messages = dict(self._messages())

        self.assertEqual(messages["Char.Name"]["name"], "Mapper")
        self.assertEqual(messages["Char.Vitals"]["hp"], 100)
        self.assertEqual(messages["Char.Status"]["coins"], 0)
        room = messages["Room.Info"]
        self.assertEqual(room["num"], 1)
        self.assertEqual(room["id"], "town_square")
        self.assertEqual(room["exits"]["s"], 4)
        self.assertEqual(room["exits"]["w"], 5)

    def test_unchanged_snapshots_are_suppressed_and_changes_are_sent(self):
        self._negotiate_and_subscribe()
        initial_count = len(self.request.sent)
        self.assertEqual(self.session.flush_gmcp(), 0)
        self.assertEqual(len(self.request.sent), initial_count)

        self.player.take_damage(7)
        self.assertEqual(self.session.flush_gmcp(), 1)
        package, payload = decode_wire_message(self.request.sent[-1])
        self.assertEqual(package, "Char.Vitals")
        self.assertEqual(payload["hp"], 93)

        self.session.move("south")
        self.assertEqual(self.session.flush_gmcp(), 1)
        package, payload = decode_wire_message(self.request.sent[-1])
        self.assertEqual(package, "Room.Info")
        self.assertEqual(payload["num"], 4)

    def test_asynchronous_damage_and_status_decay_push_vitals(self):
        self._negotiate_and_subscribe()
        self.request.sent = []

        self.assertEqual(self.session.damage_player(2, "testing"), 2)
        package, payload = decode_wire_message(self.request.sent[-1])
        self.assertEqual(package, "Char.Vitals")
        self.assertEqual(payload["hp"], 98)

        self.player.intoxication = 2
        self.session.last_status_update = 0.0
        self.session.flush_gmcp()
        self.request.sent = []
        self.assertEqual(self.session.decay_online_status(now=60.0), 1)
        package, payload = decode_wire_message(self.request.sent[-1])
        self.assertEqual(package, "Char.Vitals")
        self.assertEqual(payload["intoxication"], 1)

    def test_world_rejects_duplicate_or_invalid_gmcp_room_ids(self):
        self.assertEqual(len(self.world.gmcp_rooms), len(self.world.rooms))
        self.assertEqual(
            sorted(self.world.gmcp_rooms),
            list(range(1, len(self.world.rooms) + 1))
        )

        with self.assertRaises(ValueError):
            self.world.add_room(Room("duplicate", "Duplicate", ""), 1)

        with self.assertRaises(TypeError):
            self.world.add_room(Room("boolean", "Boolean", ""), True)


if __name__ == "__main__":
    unittest.main()
