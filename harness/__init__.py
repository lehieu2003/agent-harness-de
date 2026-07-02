from .tools import register_tool, get_tool_schemas, execute_tool
from .permissions import RISKY_TOOLS
from .hooks import hooks

__all__ = ["Agent", "register_tool", "get_tool_schemas", "execute_tool", "RISKY_TOOLS", "hooks"]


def __getattr__(name):
    if name == "Agent":
        from .core import Agent
        return Agent
    raise AttributeError(name)
