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

from .models import OpenAIModelClient
from .tools import get_tool_schemas, execute_tool
from .permissions import RISKY_TOOLS, request_approval
from .context import manage_context
from .hooks import hooks
from .skills import relevant_skills_block


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
        model_client=None,
    ):
        self.system_prompt = system_prompt
        self.model_client = model_client or OpenAIModelClient(model=model)
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

            response = self.model_client.complete(
                system=system,
                messages=messages,
                tool_schemas=get_tool_schemas(self.allowed_tools),
                max_tokens=self.max_tokens,
            )

            hooks.fire("after_response", response=response)
            messages.append(response.message.raw)

            if not response.message.tool_calls:
                final_text = response.message.content or ""
                hooks.fire("on_end", final_output=final_text)
                self.last_messages = messages
                return final_text

            # Component: tool execution + permissions
            for tool_call in response.message.tool_calls:
                name = tool_call.name
                try:
                    tool_input = json.loads(tool_call.arguments or "{}")
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
