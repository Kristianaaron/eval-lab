import io
import json
import tempfile
import unittest
from pathlib import Path

from ledger.cli import main


def run_cli(path, *argv, extra=()):
    out, err = io.StringIO(), io.StringIO()
    code = main([*extra, "--file", str(path), *argv], out=out, err=err)
    return code, out.getvalue(), err.getvalue()


class CliFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "books.json"
        run_cli(self.path, "open", "1000", "Cash", "asset")
        run_cli(self.path, "open", "4000", "Sales", "income")

    def tearDown(self):
        self.tmp.cleanup()

    def test_rate_command(self):
        code, out, err = run_cli(self.path, "rate", "eur", "1.08")
        self.assertEqual((code, out, err), (0, "rate EUR = 1.08\n", ""))
        self.assertEqual(json.loads(self.path.read_text())["rates"], {"EUR": "1.08"})
        code, _, err = run_cli(self.path, "rate", "USD", "1")
        self.assertEqual((code, err), (2, "error: cannot set a rate for the base currency\n"))
        code, _, err = run_cli(self.path, "rate", "EUR", "0")
        self.assertEqual((code, err), (2, "error: rate must be positive\n"))

    def test_post_with_currency_and_balance_conversion(self):
        run_cli(self.path, "rate", "EUR", "1.08")
        code, out, _ = run_cli(self.path, "post", "2024-01-25", "EUR sale", "1000:100:eur", "4000:-108")
        self.assertEqual((code, out), (0, "posted transaction 1\n"))
        self.assertEqual(run_cli(self.path, "balance", "1000")[1], "108.00\n")
        self.assertEqual(run_cli(self.path, "balance", "1000", "--currency", "EUR")[1], "100.00\n")
        code, _, err = run_cli(self.path, "balance", "1000", "--currency", "CHF")
        self.assertEqual((code, err), (2, "error: unknown currency: CHF\n"))
        code, _, err = run_cli(self.path, "post", "2024-01-26", "bad", "1000:1:EUR:x", "4000:-1")
        self.assertEqual((code, err), (2, "error: invalid posting '1000:1:EUR:x' (expected ACCOUNT:AMOUNT or ACCOUNT:AMOUNT:CURRENCY)\n"))
        code, _, err = run_cli(self.path, "post", "2024-01-26", "bad", "1000:1:CHF", "4000:-1")
        self.assertEqual((code, err), (2, "error: unknown currency: CHF\n"))

    def test_base_currency_option_applies_to_new_files_only(self):
        fresh = Path(self.tmp.name) / "eur.json"
        code, out, _ = run_cli(fresh, "open", "1000", "Cash", "asset", extra=["--base-currency", "eur"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(fresh.read_text())["base_currency"], "EUR")
        run_cli(fresh, "open", "4000", "Sales", "income", extra=["--base-currency", "gbp"])
        self.assertEqual(json.loads(fresh.read_text())["base_currency"], "EUR")
        self.assertEqual(json.loads(self.path.read_text())["base_currency"], "USD")

    def test_statement_command(self):
        run_cli(self.path, "post", "2024-01-02", "Opening float", "1000:1000", "4000:-1000")
        run_cli(self.path, "post", "2024-01-20", "Client payment", "1000:2,000", "4000:-2000")
        code, out, _ = run_cli(self.path, "statement", "1000", "2024-01-03", "2024-01-31")
        self.assertEqual(code, 0)
        self.assertEqual(out, (
            "Statement for 1000 Cash\n"
            "Period 2024-01-03 to 2024-01-31 (USD)\n"
            "Opening balance                                       1,000.00\n"
            "2024-01-20  Client payment                2,000.00    3,000.00\n"
            "Closing balance                                       3,000.00\n"
        ))
        code, _, err = run_cli(self.path, "statement", "1000", "2024-02-01", "2024-01-31")
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error: "))
        code, _, err = run_cli(self.path, "statement", "1000", "2024/01/01", "2024-01-31")
        self.assertEqual((code, err), (2, "error: invalid date: '2024/01/01' (expected YYYY-MM-DD)\n"))

    def test_export_command(self):
        run_cli(self.path, "post", "2024-01-02", "Opening float", "1000:1000", "4000:-1000")
        run_cli(self.path, "post", "2024-01-20", "Client, payment", "1000:2,000", "4000:-2000")
        code, out, _ = run_cli(self.path, "export")
        self.assertEqual(code, 0)
        self.assertEqual(out, (
            "transaction_id,date,memo,account,amount,currency\n"
            "1,2024-01-02,Opening float,1000,1000.00,USD\n"
            "1,2024-01-02,Opening float,4000,-1000.00,USD\n"
            '2,2024-01-20,"Client, payment",1000,2000.00,USD\n'
            '2,2024-01-20,"Client, payment",4000,-2000.00,USD\n'
        ))
        target = Path(self.tmp.name) / "out.csv"
        code, out, _ = run_cli(self.path, "export", "--start", "2024-01-10", "--out", str(target))
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(target.read_text(encoding="utf-8").splitlines(), [
            "transaction_id,date,memo,account,amount,currency",
            '2,2024-01-20,"Client, payment",1000,2000.00,USD',
            '2,2024-01-20,"Client, payment",4000,-2000.00,USD',
        ])

    def test_existing_commands_unchanged(self):
        run_cli(self.path, "post", "2024-01-02", "Opening float", "1000:1000", "4000:-1000")
        code, out, _ = run_cli(self.path, "trial-balance")
        self.assertEqual(out.splitlines(), [
            "Trial balance",
            "1000  Cash                        1,000.00",
            "4000  Sales                      -1,000.00",
            "Total                                 0.00",
        ])


if __name__ == "__main__":
    unittest.main()
