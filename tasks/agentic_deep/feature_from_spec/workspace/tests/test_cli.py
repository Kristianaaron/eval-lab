import io
import tempfile
import unittest
from pathlib import Path

from ledger.cli import main


class CliTests(unittest.TestCase):
    def run_cli(self, path, *argv):
        out, err = io.StringIO(), io.StringIO()
        code = main(["--file", str(path), *argv], out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "books.json"
            self.assertEqual(self.run_cli(path, "open", "1000", "Cash", "asset")[0], 0)
            self.assertEqual(self.run_cli(path, "open", "4000", "Sales", "income")[0], 0)
            code, out, _ = self.run_cli(path, "post", "2024-01-20", "Client payment", "1000:2,000", "4000:-2000")
            self.assertEqual((code, out), (0, "posted transaction 1\n"))
            code, out, _ = self.run_cli(path, "balance", "1000")
            self.assertEqual((code, out), (0, "2,000.00\n"))
            code, out, _ = self.run_cli(path, "trial-balance", "--as-of", "2024-01-31")
            self.assertEqual(out.splitlines()[0], "Trial balance as of 2024-01-31")
            code, _, err = self.run_cli(path, "post", "2024-01-21", "Bad", "1000:5", "4000:-4")
            self.assertEqual(code, 2)
            self.assertTrue(err.startswith("error: transaction does not balance"))
            code, _, err = self.run_cli(path, "post", "2024-13-01", "Bad date", "1000:5", "4000:-5")
            self.assertEqual((code, err), (2, "error: invalid date: '2024-13-01' (expected YYYY-MM-DD)\n"))
            code, _, err = self.run_cli(path, "post", "2024-01-21", "Bad posting", "1000", "4000:-5")
            self.assertEqual(code, 2)
            self.assertIn("expected ACCOUNT:AMOUNT", err)


if __name__ == "__main__":
    unittest.main()
