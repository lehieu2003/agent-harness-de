import unittest

from harness.safety.sql_safety import (
    DESTRUCTIVE,
    READ_ONLY,
    WRITE,
    classify_sql,
    has_multiple_statements,
    validate_read_sql,
    validate_write_sql,
)


class SqlSafetyTests(unittest.TestCase):
    def test_classifies_read_write_and_destructive_sql(self):
        self.assertEqual(classify_sql("SELECT * FROM orders"), READ_ONLY)
        self.assertEqual(classify_sql("UPDATE orders SET amount = 0 WHERE order_id = 1"), WRITE)
        self.assertEqual(classify_sql("DROP TABLE orders"), DESTRUCTIVE)

    def test_rejects_multiple_statements(self):
        self.assertTrue(has_multiple_statements("SELECT * FROM orders; DELETE FROM orders"))
        self.assertFalse(has_multiple_statements("SELECT ';' AS literal;"))

    def test_read_validation_allows_select(self):
        result = validate_read_sql("SELECT * FROM orders")

        self.assertTrue(result.ok)
        self.assertEqual(result.classification, READ_ONLY)

    def test_read_validation_rejects_write(self):
        result = validate_read_sql("DELETE FROM orders WHERE order_id = 1")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "non_read_sql")

    def test_write_validation_rejects_delete_without_where(self):
        result = validate_write_sql("DELETE FROM orders")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "missing_where")

    def test_write_validation_rejects_destructive_sql(self):
        result = validate_write_sql("DROP TABLE orders")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "destructive_sql")


if __name__ == "__main__":
    unittest.main()
