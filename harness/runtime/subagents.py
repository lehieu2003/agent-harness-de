"""
COMPONENT 4: SUB-AGENTS

Lets the main agent spawn a fresh, isolated Agent instance to handle a
sub-task — with its own system prompt and a restricted toolset. This is
useful for:
  - Parallelizable work (research multiple topics at once)
  - Isolating risky reasoning from the main conversation's context
  - Giving a sub-task a narrower, more focused prompt than the main agent

Design choice: sub-agents get a SUBSET of tools (usually read-only),
never the full toolset — this keeps delegation safe by construction,
the same way permissions.py keeps writes safe by construction.
"""
from harness.tools.registry import register_tool


def make_subagent_tool(name: str, description: str, allowed_tools: list[str], system_prompt: str):
    """
    Factory that registers a new tool which, when called, spawns a fresh
    Agent scoped to `allowed_tools` and `system_prompt`, runs it on the
    given task, and returns its final answer as the tool result.

    This keeps sub-agents declarative: define once, the harness handles
    spinning up and tearing down the sub-agent instance.
    """
    @register_tool(name, {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {"task": {"type": "string", "description": "The sub-task to delegate"}},
            "required": ["task"]
        }
    })
    def _subagent_tool(task: str):
        # Local import avoids a circular import (core.py imports tools.py)
        from harness.core import Agent

        sub_agent = Agent(
            system_prompt=system_prompt,
            max_turns=8,
            auto_approve=True,
            allowed_tools=allowed_tools,
        )
        result = sub_agent.run(task)

        return f"[Sub-agent '{name}' result]\n{result}"

    return _subagent_tool
