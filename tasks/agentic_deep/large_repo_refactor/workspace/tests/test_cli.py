import io
import unittest

from cli.main import main


class CliTests(unittest.TestCase):
    def test_demo(self):
        out = io.StringIO()
        self.assertEqual(main(["demo"], out=out), 0)
        self.assertEqual(out.getvalue().splitlines(), [
            "payment for ord-0002 declined: card declined",
            "ord-0001 shipped total=10798",
            "ord-0002 created total=24999",
            "notifications=7",
            "audit=27",
        ])

    def test_events_lists_every_event_with_subscriber_counts(self):
        out = io.StringIO()
        self.assertEqual(main(["events"], out=out), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 16)
        names = [line.split()[0] for line in lines]
        self.assertEqual(names[:4], ["customer.registered", "customer.upgraded", "cart.item_added", "order.created"])
        counts = {line.split()[0]: int(line.split()[1]) for line in lines}
        self.assertEqual(counts["order.created"], 6)
        self.assertEqual(counts["notification.sent"], 2)
        self.assertTrue(all(count >= 1 for count in counts.values()))

    def test_stock_and_report(self):
        out = io.StringIO()
        self.assertEqual(main(["stock"], out=out), 0)
        self.assertEqual(out.getvalue(), "(no stock)\n")
        out = io.StringIO()
        self.assertEqual(main(["report"], out=out), 0)
        self.assertEqual(out.getvalue(), "delivered=0 cancelled=0 captured_cents=0\nrevenue_cents=0\n")


if __name__ == "__main__":
    unittest.main()
