import json
import unittest

from harness.tools.results import (
    serialize_tool_result,
    tool_error,
    tool_result_failed,
    tool_success,
)
from harness.tools.registry import execute_tool, register_tool


class ToolResultTests(unittest.TestCase):
    def test_success_result_serializes_to_json_envelope(self):
        payload = json.loads(serialize_tool_result(tool_success("ok", data={"rows": 1})))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"], "ok")
        self.assertEqual(payload["data"], {"rows": 1})
        self.assertEqual(payload["warnings"], [])
        self.assertIsNone(payload["error"])

    def test_error_result_serializes_to_json_envelope(self):
        payload = json.loads(serialize_tool_result(tool_error("failed", error="bad input")))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["summary"], "failed")
        self.assertEqual(payload["error"], "bad input")

    def test_plain_string_result_is_wrapped_for_backward_compatibility(self):
        payload = json.loads(serialize_tool_result("plain text"))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"], "plain text")
        self.assertEqual(payload["data"], {"text": "plain text"})

    def test_execute_tool_wraps_exceptions_as_structured_errors(self):
        @register_tool("explode_for_test", {
            "name": "explode_for_test",
            "description": "Raise an exception",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        })
        def explode_for_test():
            raise RuntimeError("boom")

        payload = json.loads(execute_tool("explode_for_test", {}))

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["summary"], "Error running tool 'explode_for_test'.")
        self.assertEqual(payload["error"], "boom")

    def test_tool_result_failed_reads_json_and_legacy_strings(self):
        self.assertTrue(tool_result_failed(serialize_tool_result(tool_error("failed", error="bad"))))
        self.assertFalse(tool_result_failed(serialize_tool_result(tool_success("ok"))))
        self.assertTrue(tool_result_failed("Transformation failed: bad SQL"))

    def test_tool_result_failed_reads_direct_tool_result_objects(self):
        self.assertTrue(tool_result_failed(tool_error("failed", error="bad")))
        self.assertFalse(tool_result_failed(tool_success("ok")))


if __name__ == "__main__":
    unittest.main()
