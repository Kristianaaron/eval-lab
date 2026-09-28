import unittest
from datetime import datetime, timedelta, timezone

from inventory.errors import ValidationError
from inventory.utils import UTC, format_timestamp, parse_timestamp


class ParseTimestampTests(unittest.TestCase):
    def test_zulu_suffix_is_utc(self):
        parsed = parse_timestamp("2024-03-01T10:00:00Z")
        self.assertEqual(parsed, datetime(2024, 3, 1, 10, 0, tzinfo=UTC))

    def test_naive_timestamp_is_interpreted_as_utc(self):
        parsed = parse_timestamp("2024-03-01T10:00:00")
        self.assertEqual(parsed.tzinfo, UTC)
        self.assertEqual(parsed.hour, 10)

    def test_explicit_offset_is_converted_to_utc(self):
        parsed = parse_timestamp("2024-03-01T10:00:00+02:00")
        self.assertEqual(parsed, datetime(2024, 3, 1, 8, 0, tzinfo=UTC))
        self.assertEqual(parsed.utcoffset(), timedelta(0))

    def test_invalid_text_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            parse_timestamp("yesterday")


class FormatTimestampTests(unittest.TestCase):
    def test_round_trip(self):
        original = datetime(2024, 3, 1, 8, 30, 15, tzinfo=timezone(timedelta(hours=-5)))
        self.assertEqual(format_timestamp(original), "2024-03-01T13:30:15Z")


if __name__ == "__main__":
    unittest.main()
