"""
Lifecycle hooks: extension points to run custom code at key moments
in the agent loop, without modifying the core loop itself.

Available events:
  - before_turn(turn: int, messages: list)
  - after_response(response)
  - before_tool_call(name: str, input: dict)
  - after_tool_call(name: str, input: dict, result: str)
  - on_end(final_output)
"""


class HookManager:
    def __init__(self):
        self._hooks: dict[str, list] = {
            "before_turn": [],
            "after_response": [],
            "before_tool_call": [],
            "after_tool_call": [],
            "on_end": [],
        }

    def register(self, event: str, fn):
        if event not in self._hooks:
            raise ValueError(f"Unknown hook event: {event}")
        self._hooks[event].append(fn)

    def fire(self, event: str, **kwargs):
        for fn in self._hooks.get(event, []):
            fn(**kwargs)


hooks = HookManager()

# Example built-in hook: simple console logging. Comment out if too noisy.
hooks.register(
    "after_tool_call",
    lambda name, input, result: print(f"[TOOL] {name}({input}) -> {str(result)[:120]}")
)
