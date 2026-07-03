from harness.safety.permissions import RISKY_TOOLS
from harness.runtime.hooks import hooks
from harness.tools.registry import execute_tool, get_tool_schemas, register_tool

__all__ = ["Agent", "register_tool", "get_tool_schemas", "execute_tool", "RISKY_TOOLS", "hooks"]


def __getattr__(name):
    if name == "Agent":
        from .core import Agent
        return Agent
    raise AttributeError(name)
