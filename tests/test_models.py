import os
import unittest
from unittest.mock import patch

from harness.core.models import ModelMessage, ModelResponse, ModelToolCall, openai_tool_schemas, select_model


class ModelBoundaryTests(unittest.TestCase):
    def test_select_model_prefers_explicit_model(self):
        with patch.dict(os.environ, {"GPT_MODEL_MINI": "mini", "GPT_MODEL_NANO": "nano"}, clear=False):
            self.assertEqual(select_model("custom"), "custom")

    def test_select_model_uses_mini_then_nano_then_default(self):
        with patch.dict(os.environ, {"GPT_MODEL_MINI": "mini", "GPT_MODEL_NANO": "nano"}, clear=True):
            self.assertEqual(select_model(), "mini")

        with patch.dict(os.environ, {"GPT_MODEL_NANO": "nano"}, clear=True):
            self.assertEqual(select_model(), "nano")

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(select_model(), "gpt-4.1-mini")

    def test_openai_tool_schema_conversion(self):
        converted = openai_tool_schemas([{
            "name": "run_query",
            "description": "Run SQL",
            "input_schema": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        }])

        self.assertEqual(converted[0]["type"], "function")
        self.assertEqual(converted[0]["function"]["name"], "run_query")
        self.assertEqual(converted[0]["function"]["parameters"]["required"], ["sql"])

    def test_model_response_shape_supports_tool_calls(self):
        response = ModelResponse(
            message=ModelMessage(
                content=None,
                tool_calls=[ModelToolCall(id="call_1", name="run_query", arguments='{"sql": "SELECT 1"}')],
                raw={"role": "assistant", "tool_calls": []},
            ),
            raw=object(),
        )

        self.assertEqual(response.message.tool_calls[0].name, "run_query")


if __name__ == "__main__":
    unittest.main()
