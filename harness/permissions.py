"""
Permission layer: gate risky tool calls behind user confirmation.
"""

# Tool names that require explicit user approval before running.
# Add to this set as you add tools that touch real-world state
# (sending messages, deleting files, making purchases, etc.)
RISKY_TOOLS: set[str] = set()


def mark_risky(tool_name: str):
    """Call this to flag a tool as requiring approval."""
    RISKY_TOOLS.add(tool_name)


def request_approval(tool_name: str, tool_input: dict) -> bool:
    """
    Default approval flow: ask via terminal input.
    Swap this out for a UI prompt / API callback in a real app.
    """
    print(f"\n[PERMISSION REQUIRED] Agent wants to run: {tool_name}({tool_input})")
    answer = input("Approve? [y/N]: ").strip().lower()
    return answer == "y"
