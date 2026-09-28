import unittest
from datetime import datetime, timedelta, timezone

from inventory.errors import ValidationError
from inventory.repository import InMemoryRepository
from inventory.service import InventoryService
from inventory.utils import UTC, format_timestamp, parse_timestamp


class ParseTimestampHiddenTests(unittest.TestCase):
    def test_positive_offset(self):
        self.assertEqual(
            parse_timestamp("2024-03-01T10:00:00+02:00"), datetime(2024, 3, 1, 8, 0, tzinfo=UTC)
        )

    def test_negative_offset_crossing_midnight(self):
        parsed = parse_timestamp("2024-03-01T22:30:00-05:00")
        self.assertEqual(parsed, datetime(2024, 3, 2, 3, 30, tzinfo=UTC))
        self.assertEqual(parsed.tzinfo, UTC)

    def test_result_is_always_utc_tzinfo(self):
        for text in ("2024-03-01T10:00:00Z", "2024-03-01T10:00:00", "2024-03-01T10:00:00+09:00"):
            self.assertEqual(parse_timestamp(text).utcoffset(), timedelta(0), text)

    def test_naive_is_utc(self):
        self.assertEqual(parse_timestamp("2024-03-01 10:00:00"), datetime(2024, 3, 1, 10, tzinfo=UTC))

    def test_invalid(self):
        with self.assertRaises(ValidationError):
            parse_timestamp("")
        with self.assertRaises(ValidationError):
            parse_timestamp("2024-13-01T00:00:00Z")

    def test_format_round_trip_with_offset(self):
        text = "2024-03-01T10:00:00+02:00"
        self.assertEqual(format_timestamp(parse_timestamp(text)), "2024-03-01T08:00:00Z")


class MovementsSinceHiddenTests(unittest.TestCase):
    def setUp(self):
        self.service = InventoryService(InMemoryRepository())
        self.service.add_product("A1", "Alpha", "1.00")
        self.service.receive("A1", 1, at="2024-03-01T07:00:00Z", reference="early")
        self.service.receive("A1", 2, at="2024-03-01T10:00:00+02:00", reference="offset")  # 08:00Z
        self.service.receive("A1", 3, at="2024-03-01T09:30:00Z", reference="late")

    def test_offset_movement_sorts_by_true_instant(self):
        rows = self.service.movements_since("2024-03-01T00:00:00Z")
        self.assertEqual([m.reference for m in rows], ["early", "offset", "late"])

    def test_cutoff_with_offset_is_honoured(self):
        # 09:00+01:00 == 08:00Z -> includes the 08:00Z movement (inclusive) and the later one
        rows = self.service.movements_since("2024-03-01T09:00:00+01:00")
        self.assertEqual([m.reference for m in rows], ["offset", "late"])

    def test_datetime_cutoff_in_other_zone(self):
        cutoff = datetime(2024, 3, 1, 4, 0, tzinfo=timezone(timedelta(hours=-5)))  # 09:00Z
        rows = self.service.movements_since(cutoff)
        self.assertEqual([m.reference for m in rows], ["late"])


if __name__ == "__main__":
    unittest.main()
