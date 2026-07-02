import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import de_tools
import verify
from harness.core import Agent
from harness.models import ModelMessage, ModelResponse, ModelToolCall
from harness.session import load_session, save_session
from harness.subagents import make_subagent_tool
from harness.tools import execute_tool, get_tool_schemas


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "warehouse.db")
        self._old_de_db_path = de_tools.DB_PATH
        self._old_verify_db_path = verify.DB_PATH
        de_tools.DB_PATH = self.db_path
        verify.DB_PATH = self.db_path

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT)")
        cur.execute("CREATE TABLE orders (order_id INTEGER PRIMARY KEY, amount REAL)")
        cur.executemany("INSERT INTO customers VALUES (?, ?)", [(1, "A"), (2, "B")])
        cur.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 10.0), (2, 20.0)])
        conn.commit()
        conn.close()

    def tearDown(self):
        de_tools.DB_PATH = self._old_de_db_path
        verify.DB_PATH = self._old_verify_db_path
        self.tmpdir.cleanup()

    def test_scoped_tool_schemas_and_execution_reject_unallowed_tool(self):
        schemas = get_tool_schemas(["inspect_schema"])

        self.assertEqual([schema["name"] for schema in schemas], ["inspect_schema"])
        payload = json.loads(
            execute_tool("drop_or_truncate", {"table_name": "orders", "action": "drop"}, ["inspect_schema"])
        )
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "tool_not_allowed")

    def test_subagent_passes_allowed_tools_to_agent(self):
        captured = {}

        class FakeAgent:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def run(self, task):
                return f"ran {task}"

        make_subagent_tool(
            name="test_scoped_subagent",
            description="test subagent",
            allowed_tools=["inspect_schema", "run_query"],
            system_prompt="test prompt",
        )

        with patch("harness.core.Agent", FakeAgent):
            result = execute_tool("test_scoped_subagent", {"task": "count rows"})

        payload = json.loads(result)
        self.assertIn("ran count rows", payload["summary"])
        self.assertEqual(captured["allowed_tools"], ["inspect_schema", "run_query"])

    def test_session_id_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            load_session("..\\outside")

        with self.assertRaises(ValueError):
            save_session("../outside", [])

    def test_run_query_rejects_write_sql(self):
        result = de_tools.run_query("SELECT * FROM orders; DELETE FROM orders")

        self.assertIn("REJECTED", result)

    def test_profile_data_rejects_unknown_injected_table_name(self):
        result = de_tools.profile_data("orders; DROP TABLE customers")

        self.assertIn("not found", result)
        self.assertIn("customers", de_tools.inspect_schema())

    def test_verification_reports_row_count_changes(self):
        tool_input = {"table_name": "orders", "action": "truncate"}

        verify.capture_before_write("drop_or_truncate", tool_input)
        result = de_tools.drop_or_truncate("orders", "truncate")

        output = io.StringIO()
        with redirect_stdout(output):
            verify.verify_after_write("drop_or_truncate", tool_input, result)

        self.assertIn("orders: 2 -> 0", output.getvalue())

    def test_agent_uses_injected_model_client_without_api_key(self):
        class FakeModelClient:
            def __init__(self):
                self.calls = []

            def complete(self, system, messages, tool_schemas, max_tokens):
                self.calls.append({
                    "system": system,
                    "messages": messages,
                    "tool_schemas": tool_schemas,
                    "max_tokens": max_tokens,
                })
                return ModelResponse(
                    message=ModelMessage(
                        content="done",
                        tool_calls=[],
                        raw={"role": "assistant", "content": "done"},
                    ),
                    raw=object(),
                )

        fake_client = FakeModelClient()
        agent = Agent(system_prompt="test system", model_client=fake_client, use_skills=False)

        self.assertEqual(agent.run("hello"), "done")
        self.assertEqual(fake_client.calls[0]["system"], "test system")
        self.assertEqual(fake_client.calls[0]["messages"][0]["content"], "hello")

    def test_agent_sends_assembled_prompt_to_model_client(self):
        class FakeModelClient:
            def __init__(self):
                self.system = None

            def complete(self, system, messages, tool_schemas, max_tokens):
                self.system = system
                return ModelResponse(
                    message=ModelMessage(
                        content="done",
                        tool_calls=[],
                        raw={"role": "assistant", "content": "done"},
                    ),
                    raw=object(),
                )

        fake_client = FakeModelClient()
        agent = Agent(system_prompt="base", model_client=fake_client, use_skills=True)

        with patch("harness.prompts.relevant_skills_block", return_value="skill block"):
            agent.run("pipeline failed")

        self.assertIn("base", fake_client.system)
        self.assertIn("skill block", fake_client.system)

    def test_agent_appends_tool_result_message(self):
        class FakeModelClient:
            def __init__(self):
                self.call_count = 0

            def complete(self, system, messages, tool_schemas, max_tokens):
                self.call_count += 1
                if self.call_count == 1:
                    return ModelResponse(
                        message=ModelMessage(
                            content=None,
                            tool_calls=[
                                ModelToolCall(
                                    id="call_1",
                                    name="inspect_schema",
                                    arguments="{}",
                                )
                            ],
                            raw={
                                "role": "assistant",
                                "tool_calls": [{
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "inspect_schema", "arguments": "{}"},
                                }],
                            },
                        ),
                        raw=object(),
                    )
                return ModelResponse(
                    message=ModelMessage(
                        content="done",
                        tool_calls=[],
                        raw={"role": "assistant", "content": "done"},
                    ),
                    raw=object(),
                )

        agent = Agent(
            system_prompt="base",
            model_client=FakeModelClient(),
            use_skills=False,
            allowed_tools=["inspect_schema"],
        )

        self.assertEqual(agent.run("list tables"), "done")
        tool_message = next(m for m in agent.last_messages if m.get("role") == "tool")
        tool_payload = json.loads(tool_message["content"])

        self.assertEqual(tool_message["tool_call_id"], "call_1")
        self.assertEqual(tool_payload["summary"], de_tools.inspect_schema())
        self.assertIn({
            "role": "tool",
            "tool_call_id": "call_1",
            "content": tool_message["content"],
        }, agent.last_messages)


if __name__ == "__main__":
    unittest.main()
