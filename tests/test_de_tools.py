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
        cur.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 10.0), (2, 20.0)])
        conn.commit()
        conn.close()

    def tearDown(self):
        de_tools.DB_PATH = self._old_db_path
        self.tmpdir.cleanup()

    def test_inspect_schema_returns_structured_table_list(self):
        result = de_tools.inspect_schema()

        self.assertTrue(result.ok)
        self.assertEqual(result.data["tables"], ["orders"])
        self.assertEqual(result.summary, "Tables: orders")

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


if __name__ == "__main__":
    unittest.main()
