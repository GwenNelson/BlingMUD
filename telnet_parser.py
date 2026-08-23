"""Incremental, bounded Telnet and UTF-8 line input parsing."""

import codecs
import unicodedata


IAC = 255
SE = 240
SB = 250
WILL = 251
WONT = 252
DO = 253
DONT = 254
DEFAULT_SUBNEGOTIATION_LIMIT = 16 * 1024


class TextInputEvent(object):
    def __init__(self, text, current_text):
        self.text = text
        self.current_text = current_text


class BackspaceInputEvent(object):
    def __init__(self, current_text):
        self.current_text = current_text


class LineInputEvent(object):
    def __init__(self, text):
        self.text = text


class TabInputEvent(object):
    def __init__(self, text):
        self.text = text


class TelnetNegotiationEvent(object):
    def __init__(self, command, option):
        self.command = command
        self.option = option


class TelnetSubnegotiationEvent(object):
    def __init__(self, option, data):
        self.option = option
        self.data = data


def _allowed_input_character(character):
    category = unicodedata.category(character)

    if category in ("Cc", "Cf", "Cs", "Zl", "Zp"):
        return False

    return character not in ("\r", "\n", "\t")


class TelnetInputParser(object):
    """Parse arbitrarily fragmented Telnet bytes into editable line events."""

    STATE_DATA = "data"
    STATE_IAC = "iac"
    STATE_OPTION = "option"
    STATE_SUBNEGOTIATION_OPTION = "subnegotiation_option"
    STATE_SUBNEGOTIATION = "subnegotiation"
    STATE_SUBNEGOTIATION_IAC = "subnegotiation_iac"

    def __init__(
        self,
        maximum_length,
        maximum_subnegotiation_length=DEFAULT_SUBNEGOTIATION_LIMIT
    ):
        self.maximum_length = 0
        self.set_maximum_length(maximum_length)
        self.characters = []
        self.state = self.STATE_DATA
        self.pending_option_command = None
        self.subnegotiation_option = None
        self.subnegotiation_data = bytearray()
        self.subnegotiation_overflowed = False
        self.maximum_subnegotiation_length = max(
            0,
            int(maximum_subnegotiation_length)
        )
        self.pending_cr = False
        self.decoder = self._new_decoder()

    def _new_decoder(self):
        return codecs.getincrementaldecoder("utf-8")("replace")

    @property
    def current_text(self):
        return "".join(self.characters)

    def set_maximum_length(self, maximum_length):
        if isinstance(maximum_length, bool):
            raise ValueError("maximum length must be an integer")

        maximum_length = int(maximum_length)

        if maximum_length < 0:
            raise ValueError("maximum length cannot be negative")

        self.maximum_length = maximum_length

        if hasattr(self, "characters"):
            del self.characters[maximum_length:]

    def reset_line(self):
        self.characters = []
        self.pending_cr = False
        self.decoder = self._new_decoder()

    def replace_current_text(self, text):
        """Replace editable text with filtered, bounded trusted completion."""
        if not isinstance(text, str):
            raise TypeError("replacement input must be text")

        characters = []

        for character in text:
            if not _allowed_input_character(character):
                continue

            if len(characters) >= self.maximum_length:
                break

            characters.append(character)

        self.characters = characters
        self.pending_cr = False
        self.decoder = self._new_decoder()
        return self.current_text

    def _append_decoded(self, text, events):
        accepted = []

        for character in text:
            if not _allowed_input_character(character):
                continue

            if len(self.characters) >= self.maximum_length:
                continue

            self.characters.append(character)
            accepted.append(character)

        if accepted:
            events.append(
                TextInputEvent("".join(accepted), self.current_text)
            )

    def _flush_decoder(self, events):
        decoded = self.decoder.decode(b"", final=True)
        self._append_decoded(decoded, events)
        self.decoder = self._new_decoder()

    def _finish_line(self, events):
        self._flush_decoder(events)
        text = self.current_text
        self.characters = []
        self.pending_cr = False
        events.append(LineInputEvent(text))

    def _backspace(self, events):
        pending_bytes, decoder_flag = self.decoder.getstate()

        if pending_bytes:
            self.decoder = self._new_decoder()
            return

        if self.characters:
            self.characters.pop()
            events.append(BackspaceInputEvent(self.current_text))

    def _process_data_byte(self, byte, events):
        if self.pending_cr:
            if byte in (0, 10):
                self._finish_line(events)
                return

            self._finish_line(events)

        if byte == 13:
            self.pending_cr = True
            return

        if byte == 10:
            self._finish_line(events)
            return

        if byte == 9:
            events.append(TabInputEvent(self.current_text))
            return

        if byte in (8, 127):
            self._backspace(events)
            return

        if byte < 32:
            return

        decoded = self.decoder.decode(bytes((byte,)), final=False)
        self._append_decoded(decoded, events)

    def feed(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Telnet input must be bytes")

        events = []

        for byte in data:
            if self.state == self.STATE_OPTION:
                events.append(
                    TelnetNegotiationEvent(self.pending_option_command, byte)
                )
                self.pending_option_command = None
                self.state = self.STATE_DATA
                continue

            if self.state == self.STATE_SUBNEGOTIATION_OPTION:
                self.subnegotiation_option = byte
                self.subnegotiation_data = bytearray()
                self.subnegotiation_overflowed = False
                self.state = self.STATE_SUBNEGOTIATION
                continue

            if self.state == self.STATE_SUBNEGOTIATION:
                if byte == IAC:
                    self.state = self.STATE_SUBNEGOTIATION_IAC
                elif not self.subnegotiation_overflowed:
                    if (
                        len(self.subnegotiation_data)
                        >= self.maximum_subnegotiation_length
                    ):
                        self.subnegotiation_overflowed = True
                        self.subnegotiation_data = bytearray()
                    else:
                        self.subnegotiation_data.append(byte)
                continue

            if self.state == self.STATE_SUBNEGOTIATION_IAC:
                if byte == SE:
                    if not self.subnegotiation_overflowed:
                        events.append(
                            TelnetSubnegotiationEvent(
                                self.subnegotiation_option,
                                bytes(self.subnegotiation_data)
                            )
                        )
                    self.subnegotiation_option = None
                    self.subnegotiation_data = bytearray()
                    self.subnegotiation_overflowed = False
                    self.state = self.STATE_DATA
                elif byte == IAC:
                    if not self.subnegotiation_overflowed:
                        if (
                            len(self.subnegotiation_data)
                            >= self.maximum_subnegotiation_length
                        ):
                            self.subnegotiation_overflowed = True
                            self.subnegotiation_data = bytearray()
                        else:
                            self.subnegotiation_data.append(IAC)
                    self.state = self.STATE_SUBNEGOTIATION
                else:
                    self.subnegotiation_overflowed = True
                    self.subnegotiation_data = bytearray()
                    self.state = self.STATE_SUBNEGOTIATION
                continue

            if self.state == self.STATE_IAC:
                if byte in (WILL, WONT, DO, DONT):
                    self.pending_option_command = byte
                    self.state = self.STATE_OPTION
                elif byte == SB:
                    self.state = self.STATE_SUBNEGOTIATION_OPTION
                elif byte == IAC:
                    self.state = self.STATE_DATA
                    self._process_data_byte(byte, events)
                else:
                    self.state = self.STATE_DATA
                continue

            if byte == IAC:
                self.state = self.STATE_IAC
                continue

            self._process_data_byte(byte, events)

        return events
