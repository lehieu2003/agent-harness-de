import os
import sqlite3
import tempfile
import unittest

from harness.safety.verification import VerificationEngine


class VerificationEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "warehouse.db")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, amount REAL)")
        cur.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 10.0), (2, None)])
        conn.commit()
        conn.close()
        self.engine = VerificationEngine(self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_compare_reports_row_and_null_count_diffs(self):
        conn = sqlite3.connect(self.db_path)
        before = self.engine.snapshot(conn)
        conn.execute("UPDATE orders SET amount = 20 WHERE order_id = 2")
        after = self.engine.snapshot(conn)
        conn.rollback()
        conn.close()

        report = self.engine.compare(before, after)

        self.assertTrue(report.ok)
        self.assertEqual(report.null_count_diffs["orders"]["amount"], {"before": 1, "after": 0})

    def test_compare_fails_unexpected_missing_table(self):
        conn = sqlite3.connect(self.db_path)
        before = self.engine.snapshot(conn)
        conn.execute("DROP TABLE orders")
        after = self.engine.snapshot(conn)
        conn.rollback()
        conn.close()

        report = self.engine.compare(before, after)

        self.assertFalse(report.ok)
        self.assertEqual(report.missing_tables, ["orders"])

    def test_compare_allows_expected_missing_table(self):
        conn = sqlite3.connect(self.db_path)
        before = self.engine.snapshot(conn)
        conn.execute("DROP TABLE orders")
        after = self.engine.snapshot(conn)
        conn.rollback()
        conn.close()

        report = self.engine.compare(before, after, expected_missing_tables={"orders"})

        self.assertFalse(report.ok)
        self.assertIn("no tables found", report.summary)

    def test_compare_reports_schema_diffs(self):
        conn = sqlite3.connect(self.db_path)
        before = self.engine.snapshot(conn)
        conn.execute("ALTER TABLE orders ADD COLUMN status TEXT")
        after = self.engine.snapshot(conn)
        conn.rollback()
        conn.close()

        report = self.engine.compare(before, after)

        self.assertTrue(report.ok)
        self.assertIn("orders", report.schema_diffs)
        self.assertTrue(any("Schema changed" in warning for warning in report.warnings))


if __name__ == "__main__":
    unittest.main()
