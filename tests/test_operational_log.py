import io
import json
import unittest

from operational_log import MAX_FIELD_LENGTH, OperationalLogger


class OperationalLogTests(unittest.TestCase):
    def test_event_is_json_bounded_control_safe_and_secret_redacted(self):
        sink = io.StringIO()
        logger = OperationalLogger(sink=sink, time_source=lambda: 123.5)
        self.assertTrue(logger.emit(
            "auth.login_success",
            player="Test\033[31mFace",
            password="do not print me",
            api_key="also secret",
            detail="x" * (MAX_FIELD_LENGTH + 20)
        ))
        encoded = sink.getvalue()
        document = json.loads(encoded)
        self.assertEqual(document["event"], "auth.login_success")
        self.assertEqual(document["time"], 123.5)
        self.assertNotIn("\033", encoded)
        self.assertEqual(document["password"], "[redacted]")
        self.assertEqual(document["api_key"], "[redacted]")
        self.assertEqual(len(document["detail"]), MAX_FIELD_LENGTH)

    def test_exception_records_type_without_untrusted_message(self):
        sink = io.StringIO()
        logger = OperationalLogger(sink=sink)
        logger.exception(
            "npc.callback_error",
            RuntimeError("private player speech"),
            npc="Val"
        )
        encoded = sink.getvalue()
        self.assertIn("RuntimeError", encoded)
        self.assertNotIn("private player speech", encoded)

    def test_caller_cannot_replace_reserved_metadata(self):
        sink = io.StringIO()
        logger = OperationalLogger(sink=sink, time_source=lambda: 88.0)
        self.assertTrue(logger.emit(
            "server.test",
            time="forged",
            thread="forged",
            Invalid="discarded"
        ))
        document = json.loads(sink.getvalue())
        self.assertEqual(document["time"], 88.0)
        self.assertNotEqual(document["thread"], "forged")
        self.assertNotIn("Invalid", document)

    def test_field_count_and_total_line_are_bounded(self):
        sink = io.StringIO()
        logger = OperationalLogger(sink=sink)
        fields = {
            "field_{0:02d}".format(index): index
            for index in range(30)
        }
        self.assertTrue(logger.emit("server.test", **fields))
        document = json.loads(sink.getvalue())
        self.assertEqual(len(document) - 3, 16)

        oversized_sink = io.StringIO()
        oversized = OperationalLogger(sink=oversized_sink)
        self.assertFalse(oversized.emit("server.test", value=10 ** 4050))
        self.assertEqual(oversized_sink.getvalue(), "")

    def test_non_finite_timestamp_is_rejected(self):
        sink = io.StringIO()
        logger = OperationalLogger(sink=sink, time_source=lambda: float("inf"))
        self.assertFalse(logger.emit("server.test"))
        self.assertEqual(sink.getvalue(), "")

    def test_invalid_events_and_broken_sinks_cannot_break_caller(self):
        class BrokenSink(object):
            def write(self, text):
                raise OSError("disk full")

        self.assertFalse(OperationalLogger().emit("Bad Event", value=1))
        self.assertFalse(
            OperationalLogger(sink=BrokenSink()).emit("server.test", value=1)
        )


if __name__ == "__main__":
    unittest.main()
