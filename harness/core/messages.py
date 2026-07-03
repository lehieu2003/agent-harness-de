"""
Message helpers.

These helpers keep chat message shapes in one place so the agent loop does not
hand-build protocol dictionaries throughout the code.
"""


def user_message(content: str) -> dict:
    return {"role": "user", "content": content}


def assistant_message(raw_message: dict) -> dict:
    return dict(raw_message)


def tool_result_message(tool_call_id: str, content: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }
