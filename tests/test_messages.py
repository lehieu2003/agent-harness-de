import unittest

from harness.core.messages import assistant_message, tool_result_message, user_message


class MessageHelperTests(unittest.TestCase):
    def test_user_message_shape(self):
        self.assertEqual(user_message("hello"), {"role": "user", "content": "hello"})

    def test_assistant_message_copies_raw_message(self):
        raw = {"role": "assistant", "content": "done"}
        copied = assistant_message(raw)

        self.assertEqual(copied, raw)
        self.assertIsNot(copied, raw)

    def test_tool_result_message_shape(self):
        self.assertEqual(
            tool_result_message("call_1", "result"),
            {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        )


if __name__ == "__main__":
    unittest.main()
