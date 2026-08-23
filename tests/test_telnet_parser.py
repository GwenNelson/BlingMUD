import unittest

from telnet_parser import (
    BackspaceInputEvent,
    DONT,
    DO,
    IAC,
    LineInputEvent,
    SB,
    SE,
    TabInputEvent,
    TelnetNegotiationEvent,
    TelnetSubnegotiationEvent,
    TelnetInputParser,
    TextInputEvent,
    WILL,
    WONT
)


def lines(events):
    return [
        event.text
        for event in events
        if isinstance(event, LineInputEvent)
    ]


class TelnetInputParserTests(unittest.TestCase):
    def test_fragmented_utf8_is_decoded_without_replacement(self):
        parser = TelnetInputParser(20)
        encoded = "café 🦄".encode("utf-8")
        events = []

        for byte in encoded:
            events.extend(parser.feed(bytes((byte,))))

        events.extend(parser.feed(b"\n"))

        self.assertEqual(lines(events), ["café 🦄"])
        self.assertNotIn("\ufffd", lines(events)[0])

    def test_all_option_negotiations_are_incrementally_removed(self):
        parser = TelnetInputParser(20)
        events = []
        negotiation = bytes((
            IAC, WILL, 1,
            IAC, WONT, 2,
            IAC, DO, 3,
            IAC, DONT, 4
        ))

        for byte in negotiation + b"hello\n":
            events.extend(parser.feed(bytes((byte,))))

        self.assertEqual(lines(events), ["hello"])
        negotiations = [
            event
            for event in events
            if isinstance(event, TelnetNegotiationEvent)
        ]
        self.assertEqual(
            [(event.command, event.option) for event in negotiations],
            [(WILL, 1), (WONT, 2), (DO, 3), (DONT, 4)]
        )

    def test_subnegotiation_is_ignored_until_fragmented_iac_se(self):
        parser = TelnetInputParser(20)
        fragments = (
            bytes((IAC, SB, 24)),
            b"terminal-type",
            bytes((IAC, IAC, 1, 2, IAC)),
            bytes((SE,)) + b"visible\n"
        )
        events = []

        for fragment in fragments:
            events.extend(parser.feed(fragment))

        self.assertEqual(lines(events), ["visible"])
        subnegotiations = [
            event
            for event in events
            if isinstance(event, TelnetSubnegotiationEvent)
        ]
        self.assertEqual(len(subnegotiations), 1)
        self.assertEqual(subnegotiations[0].option, 24)
        self.assertEqual(
            subnegotiations[0].data,
            b"terminal-type" + bytes((IAC, 1, 2))
        )

    def test_subnegotiation_overflow_is_discarded_and_parser_recovers(self):
        parser = TelnetInputParser(20, maximum_subnegotiation_length=4)
        events = parser.feed(
            bytes((IAC, SB, 201))
            + b"12345"
            + bytes((IAC, SE))
            + b"visible\n"
        )

        self.assertFalse(any(
            isinstance(event, TelnetSubnegotiationEvent)
            for event in events
        ))
        self.assertEqual(lines(events), ["visible"])

    def test_escaped_iac_is_data_not_a_telnet_command(self):
        parser = TelnetInputParser(20)
        events = parser.feed(bytes((IAC, IAC, 10)))

        self.assertEqual(lines(events), ["\ufffd"])

    def test_crlf_crnul_and_lf_each_produce_exactly_one_line(self):
        parser = TelnetInputParser(20)
        events = parser.feed(b"one\r\ntwo\r\x00three\n")

        self.assertEqual(lines(events), ["one", "two", "three"])

    def test_unicode_backspace_removes_one_decoded_character(self):
        parser = TelnetInputParser(20)
        events = parser.feed("é".encode("utf-8") + b"\x08e\n")

        self.assertEqual(lines(events), ["e"])
        self.assertEqual(
            len([
                event
                for event in events
                if isinstance(event, BackspaceInputEvent)
            ]),
            1
        )

    def test_character_bound_counts_unicode_characters_not_bytes(self):
        parser = TelnetInputParser(2)
        events = parser.feed("🦄ab\n".encode("utf-8"))

        self.assertEqual(lines(events), ["🦄a"])

    def test_tab_is_an_explicit_event_and_does_not_finish_line(self):
        parser = TelnetInputParser(20)
        events = parser.feed(b"/lo\tok\n")
        tabs = [
            event
            for event in events
            if isinstance(event, TabInputEvent)
        ]

        self.assertEqual(len(tabs), 1)
        self.assertEqual(tabs[0].text, "/lo")
        self.assertEqual(lines(events), ["/look"])

    def test_terminal_and_bidirectional_controls_are_dropped(self):
        parser = TelnetInputParser(30)
        unsafe = "safe\x1b[31m\u202edanger\n".encode("utf-8")
        events = parser.feed(unsafe)

        self.assertEqual(lines(events), ["safe[31mdanger"])

    def test_text_events_contain_only_accepted_echo_text(self):
        parser = TelnetInputParser(2)
        events = parser.feed("abextra\n".encode("utf-8"))
        echoed = "".join(
            event.text
            for event in events
            if isinstance(event, TextInputEvent)
        )

        self.assertEqual(echoed, "ab")


if __name__ == "__main__":
    unittest.main()
