"""
Core agent loop. This is the heart of the harness:

    while not done:
        response = call_model(messages)
        if response wants a tool -> execute it, feed result back
        else -> done, return final answer

Everything else in this package (context, permissions, hooks, skills,
session) plugs into this loop.
"""
import json
import os

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .tools import get_tool_schemas, execute_tool
from .permissions import RISKY_TOOLS, request_approval
from .context import manage_context
from .hooks import hooks
from .skills import relevant_skills_block


def load_env_file(path: str | None = None):
    """Load simple KEY=VALUE pairs from .env without requiring another package."""
    env_path = path or os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


class Agent:
    def __init__(
        self,
        system_prompt: str = "You are a helpful, general-purpose assistant.",
        model: str | None = None,
        max_turns: int = 15,
        max_tokens: int = 4096,
        auto_approve: bool = False,
        use_skills: bool = True,
        allowed_tools: list[str] | None = None,
    ):
        load_env_file()
        if OpenAI is None:
            raise RuntimeError("The openai package is required to run Agent. Install requirements.txt first.")
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required. Add it to .env or your shell environment.")

        self.client = OpenAI()
        self.system_prompt = system_prompt
        self.model = model or os.getenv("GPT_MODEL_MINI") or os.getenv("GPT_MODEL_NANO") or "gpt-4.1-mini"
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.auto_approve = auto_approve
        self.use_skills = use_skills
        self.allowed_tools = allowed_tools

    def run(self, user_message: str, messages: list | None = None) -> str:
        """
        Run the agent loop on a user message.
        Pass `messages` (from a loaded session) to continue a conversation.
        """
        messages = list(messages) if messages else []
        messages.append({"role": "user", "content": user_message})

        # Component: built-in skills — inject relevant instructions
        system = self.system_prompt
        if self.use_skills:
            skills_block = relevant_skills_block(user_message)
            if skills_block:
                system = f"{system}\n\n# Relevant skill instructions\n{skills_block}"

        for turn in range(self.max_turns):
            # Component: context management
            messages = manage_context(messages)

            hooks.fire("before_turn", turn=turn, messages=messages)

            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "system", "content": system}, *messages],
                tools=self._openai_tool_schemas(),
            )

            hooks.fire("after_response", response=response)
            response_message = response.choices[0].message
            assistant_message = response_message.model_dump(exclude_none=True)
            messages.append(assistant_message)

            if not response_message.tool_calls:
                final_text = response_message.content or ""
                hooks.fire("on_end", final_output=final_text)
                self.last_messages = messages
                return final_text

            # Component: tool execution + permissions
            for tool_call in response_message.tool_calls:
                name = tool_call.function.name
                try:
                    tool_input = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError as e:
                    tool_input = {}
                    result = f"Error: invalid tool arguments JSON: {e}"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                    continue

                hooks.fire("before_tool_call", name=name, input=tool_input)

                if name in RISKY_TOOLS and not self.auto_approve:
                    approved = request_approval(name, tool_input)
                    if not approved:
                        result = "User denied permission for this action."
                    else:
                        result = execute_tool(name, tool_input, self.allowed_tools)
                else:
                    result = execute_tool(name, tool_input, self.allowed_tools)

                hooks.fire("after_tool_call", name=name, input=tool_input, result=result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        self.last_messages = messages
        return "[Max turns reached without a final answer]"

    def _openai_tool_schemas(self) -> list[dict]:
        schemas = []
        for schema in get_tool_schemas(self.allowed_tools):
            schemas.append({
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema.get("description", ""),
                    "parameters": schema.get("input_schema", {"type": "object", "properties": {}}),
                },
            })
        return schemas
