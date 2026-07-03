"""
Example tools for the generic assistant entry point.
"""
from datetime import datetime

from harness.safety.permissions import mark_risky
from harness.tools.registry import register_tool


@register_tool("get_current_time", {
    "name": "get_current_time",
    "description": "Get the current local date and time.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
})
def get_current_time():
    return datetime.now().isoformat(timespec="seconds")


@register_tool("calculate", {
    "name": "calculate",
    "description": "Evaluate a simple arithmetic expression.",
    "input_schema": {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
})
def calculate(expression: str):
    allowed = set("0123456789+-*/(). ")
    if any(ch not in allowed for ch in expression):
        return "Rejected: only simple arithmetic characters are allowed."
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"Calculation error: {e}"


@register_tool("delete_note", {
    "name": "delete_note",
    "description": "Demo risky tool that pretends to delete a note by ID.",
    "input_schema": {
        "type": "object",
        "properties": {"note_id": {"type": "string"}},
        "required": ["note_id"],
    },
})
def delete_note(note_id: str):
    return f"Deleted note {note_id}."


mark_risky("delete_note")
