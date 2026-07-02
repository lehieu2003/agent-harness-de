"""
Tool registry: define tools once with @register_tool, and the harness
automatically knows their schema (for the LLM) and how to execute them.
"""

from .tool_results import serialize_tool_result, tool_error

TOOL_REGISTRY = {}


def register_tool(name: str, schema: dict):
    """
    Decorator to register a function as a tool the agent can call.

    Example:
        @register_tool("get_weather", {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"]
            }
        })
        def get_weather(city: str) -> str:
            return f"Sunny in {city}"
    """
    def decorator(fn):
        TOOL_REGISTRY[name] = {"fn": fn, "schema": schema}
        return fn
    return decorator


def get_tool_schemas(allowed_tools: list[str] | None = None) -> list[dict]:
    """Returns internal tool schemas."""
    if allowed_tools is None:
        return [t["schema"] for t in TOOL_REGISTRY.values()]
    return [TOOL_REGISTRY[t]["schema"] for t in allowed_tools if t in TOOL_REGISTRY]


def execute_tool(name: str, tool_input: dict, allowed_tools: list[str] | None = None) -> str:
    """Look up and run a registered tool. Returns a JSON string result."""
    if allowed_tools is not None and name not in allowed_tools:
        return serialize_tool_result(tool_error(
            summary=f"Tool '{name}' is not allowed in this agent scope.",
            error="tool_not_allowed",
        ))
    if name not in TOOL_REGISTRY:
        return serialize_tool_result(tool_error(
            summary=f"Unknown tool '{name}'.",
            error="unknown_tool",
        ))
    try:
        result = TOOL_REGISTRY[name]["fn"](**tool_input)
        return serialize_tool_result(result)
    except Exception as e:
        return serialize_tool_result(tool_error(
            summary=f"Error running tool '{name}'.",
            error=str(e),
        ))
