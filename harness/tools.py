"""
Tool registry: define tools once with @register_tool, and the harness
automatically knows their schema (for the LLM) and how to execute them.
"""

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


def get_tool_schemas() -> list[dict]:
    """Returns tool schemas in the format the Anthropic API expects."""
    return [t["schema"] for t in TOOL_REGISTRY.values()]


def execute_tool(name: str, tool_input: dict) -> str:
    """Look up and run a registered tool. Returns a string result."""
    if name not in TOOL_REGISTRY:
        return f"Error: unknown tool '{name}'"
    try:
        result = TOOL_REGISTRY[name]["fn"](**tool_input)
        return str(result)
    except Exception as e:
        return f"Error running tool '{name}': {e}"
