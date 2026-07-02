"""
Core agent loop. This is the heart of the harness:

    while not done:
        response = call_model(messages)
        if response wants a tool -> execute it, feed result back
        else -> done, return final answer

Everything else in this package (context, permissions, hooks, skills,
session) plugs into this loop.
"""
from anthropic import Anthropic

from .tools import get_tool_schemas, execute_tool
from .permissions import RISKY_TOOLS, request_approval
from .context import manage_context
from .hooks import hooks
from .skills import relevant_skills_block


class Agent:
    def __init__(
        self,
        system_prompt: str = "You are a helpful, general-purpose assistant.",
        model: str = "claude-sonnet-4-6",
        max_turns: int = 15,
        max_tokens: int = 4096,
        auto_approve: bool = False,
        use_skills: bool = True,
    ):
        self.client = Anthropic()
        self.system_prompt = system_prompt
        self.model = model
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.auto_approve = auto_approve
        self.use_skills = use_skills

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

            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                tools=get_tool_schemas(),
                messages=messages,
            )

            hooks.fire("after_response", response=response)
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                final_text = self._extract_text(response.content)
                hooks.fire("on_end", final_output=final_text)
                self.last_messages = messages
                return final_text

            # Component: tool execution + permissions
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                hooks.fire("before_tool_call", name=block.name, input=block.input)

                if block.name in RISKY_TOOLS and not self.auto_approve:
                    approved = request_approval(block.name, block.input)
                    if not approved:
                        result = "User denied permission for this action."
                    else:
                        result = execute_tool(block.name, block.input)
                else:
                    result = execute_tool(block.name, block.input)

                hooks.fire("after_tool_call", name=block.name, input=block.input, result=result)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

        self.last_messages = messages
        return "[Max turns reached without a final answer]"

    @staticmethod
    def _extract_text(content_blocks) -> str:
        return "\n".join(b.text for b in content_blocks if b.type == "text")
