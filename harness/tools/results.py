"""
Structured tool results.

Tools can return plain strings, dicts, or ToolResult objects. The execution
layer normalizes every result into a JSON string before sending it back to the
model.
"""
from dataclasses import asdict, dataclass, field
import json
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    summary: str
    data: Any = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def tool_success(summary: str, data: Any = None, warnings: list[str] | None = None) -> ToolResult:
    return ToolResult(
        ok=True,
        summary=summary,
        data=data,
        warnings=warnings or [],
        error=None,
    )


def tool_error(summary: str, error: str, data: Any = None, warnings: list[str] | None = None) -> ToolResult:
    return ToolResult(
        ok=False,
        summary=summary,
        data=data,
        warnings=warnings or [],
        error=error,
    )


def normalize_tool_result(result) -> ToolResult:
    if isinstance(result, ToolResult):
        return result

    if isinstance(result, dict):
        return ToolResult(
            ok=bool(result.get("ok", True)),
            summary=str(result.get("summary", "")),
            data=result.get("data"),
            warnings=list(result.get("warnings", [])),
            error=result.get("error"),
        )

    return tool_success(summary=str(result), data={"text": str(result)})


def serialize_tool_result(result) -> str:
    normalized = normalize_tool_result(result)
    return json.dumps(asdict(normalized), default=str)


def tool_result_failed(result) -> bool:
    if isinstance(result, ToolResult):
        return not result.ok

    if isinstance(result, dict) and "ok" in result:
        return not bool(result["ok"])

    try:
        payload = json.loads(result)
    except (TypeError, json.JSONDecodeError):
        lowered = str(result).lower()
        return "failed" in lowered or "error" in lowered

    if isinstance(payload, dict) and "ok" in payload:
        return not bool(payload["ok"])

    return False
