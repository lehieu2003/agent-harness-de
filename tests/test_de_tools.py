import json
import os
import sqlite3
import tempfile
import unittest

import de_tools
from harness.tools import execute_tool


class DataEngineerToolTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "warehouse.db")
        self._old_db_path = de_tools.DB_PATH
        de_tools.DB_PATH = self.db_path

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, amount REAL)")
        cur.execute("""
            CREATE TABLE pipeline_runs (
                run_id INTEGER PRIMARY KEY,
                pipeline_name TEXT,
                run_date TEXT,
                status TEXT,
                error_message TEXT
            )
        """)
        cur.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 10.0), (2, 20.0)])
        cur.execute(
            "INSERT INTO pipeline_runs VALUES (?, ?, ?, ?, ?)",
            (1, "daily_revenue", "2025-06-30", "failed", "anomaly detected"),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        de_tools.DB_PATH = self._old_db_path
        self.tmpdir.cleanup()

    def test_inspect_schema_returns_structured_table_list(self):
        result = de_tools.inspect_schema()

        self.assertTrue(result.ok)
        self.assertEqual(result.data["tables"], ["orders", "pipeline_runs"])
        self.assertEqual(result.summary, "Tables: orders, pipeline_runs")

    def test_inspect_schema_returns_structured_columns(self):
        result = de_tools.inspect_schema("orders")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["table"], "orders")
        self.assertEqual(result.data["columns"][0]["name"], "order_id")

    def test_run_query_returns_structured_rows(self):
        result = de_tools.run_query("SELECT order_id, amount FROM orders ORDER BY order_id")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["columns"], ["order_id", "amount"])
        self.assertEqual(result.data["rows"], [[1, 10.0], [2, 20.0]])

    def test_execute_tool_serializes_structured_result(self):
        payload = json.loads(execute_tool("run_query", {"sql": "SELECT COUNT(*) AS count FROM orders"}))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["columns"], ["count"])
        self.assertEqual(payload["data"]["rows"], [[2]])

    def test_profile_data_returns_structured_profile(self):
        result = de_tools.profile_data("orders")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["table"], "orders")
        self.assertEqual(result.data["total_rows"], 2)
        self.assertEqual(result.data["null_counts"]["amount"], 0)

    def test_validate_sql_returns_structured_query_plan(self):
        result = de_tools.validate_sql("SELECT * FROM orders")

        self.assertTrue(result.ok)
        self.assertIn("query_plan", result.data)

    def test_check_pipeline_status_returns_structured_runs(self):
        result = de_tools.check_pipeline_status("daily_revenue")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["pipeline_name"], "daily_revenue")
        self.assertEqual(result.data["runs"][0]["status"], "failed")

    def test_run_transformation_returns_structured_write_result(self):
        result = de_tools.run_transformation(
            "UPDATE orders SET amount = amount + 1 WHERE order_id = 1",
            "one row by primary key",
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.data["rows_affected"], 1)
        self.assertEqual(result.data["expected_row_impact"], "one row by primary key")

    def test_run_transformation_returns_structured_error(self):
        result = de_tools.run_transformation("UPDATE missing SET amount = 0 WHERE id = 1", "unknown")

        self.assertFalse(result.ok)
        self.assertIn("Transformation failed", result.summary)

    def test_drop_or_truncate_returns_structured_result(self):
        result = de_tools.drop_or_truncate("orders", "truncate")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["table"], "orders")
        self.assertEqual(result.data["action"], "truncate")

    def test_drop_or_truncate_rejects_invalid_action(self):
        result = de_tools.drop_or_truncate("orders", "delete")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "invalid_action")

    def test_execute_tool_serializes_write_result(self):
        payload = json.loads(execute_tool(
            "run_transformation",
            {
                "sql": "UPDATE orders SET amount = amount + 1 WHERE order_id = 1",
                "expected_row_impact": "one row by primary key",
            },
        ))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["rows_affected"], 1)


if __name__ == "__main__":
    unittest.main()
