"""
Model client boundary.

This module owns provider-specific API details so the core agent loop can stay
focused on orchestration.
"""
from dataclasses import dataclass
import os

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


@dataclass
class ModelToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class ModelMessage:
    content: str | None
    tool_calls: list[ModelToolCall]
    raw: dict


@dataclass
class ModelResponse:
    message: ModelMessage
    raw: object


def load_env_file(path: str | None = None):
    """Load simple KEY=VALUE pairs from .env without requiring another package."""
    env_path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
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


def select_model(explicit_model: str | None = None) -> str:
    return explicit_model or os.getenv("GPT_MODEL_MINI") or os.getenv("GPT_MODEL_NANO") or "gpt-4.1-mini"


def openai_tool_schemas(tool_schemas: list[dict]) -> list[dict]:
    schemas = []
    for schema in tool_schemas:
        schemas.append({
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema.get("description", ""),
                "parameters": schema.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return schemas


class OpenAIModelClient:
    def __init__(self, model: str | None = None, client=None):
        load_env_file()
        if client is None:
            if OpenAI is None:
                raise RuntimeError("The openai package is required to run Agent. Install requirements.txt first.")
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is required. Add it to .env or your shell environment.")
            client = OpenAI()

        self.client = client
        self.model = select_model(model)

    def complete(
        self,
        system: str,
        messages: list[dict],
        tool_schemas: list[dict],
        max_tokens: int,
    ) -> ModelResponse:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, *messages],
            tools=openai_tool_schemas(tool_schemas),
        )
        response_message = response.choices[0].message
        tool_calls = []
        for tool_call in response_message.tool_calls or []:
            tool_calls.append(ModelToolCall(
                id=tool_call.id,
                name=tool_call.function.name,
                arguments=tool_call.function.arguments or "{}",
            ))
        return ModelResponse(
            message=ModelMessage(
                content=response_message.content,
                tool_calls=tool_calls,
                raw=response_message.model_dump(exclude_none=True),
            ),
            raw=response,
        )
