"""
Context management: keep the conversation within a token budget.

Starts simple (rough char-based token estimate + truncate-oldest).
Swap `estimate_tokens` for a real tokenizer and `compact` for
LLM-based summarization when you need it.
"""


def estimate_tokens(messages: list) -> int:
    """Rough estimate: ~4 chars per token. Good enough to start."""
    total_chars = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                total_chars += len(str(block))
    return total_chars // 4


def compact(messages: list, keep_recent: int = 10) -> list:
    """
    Simplest possible strategy: keep the most recent N messages verbatim,
    drop the rest with a placeholder note.

    Upgrade path: replace the placeholder with an actual LLM-generated
    summary of the dropped messages.
    """
    if len(messages) <= keep_recent:
        return messages

    recent = messages[-keep_recent:]
    dropped_count = len(messages) - keep_recent
    placeholder = {
        "role": "user",
        "content": f"[{dropped_count} earlier messages omitted to save context space]"
    }
    return [placeholder] + recent


def manage_context(messages: list, max_tokens: int = 100_000, keep_recent: int = 10) -> list:
    """Call this at the start of each turn to keep context in budget."""
    if estimate_tokens(messages) < max_tokens:
        return messages
    return compact(messages, keep_recent=keep_recent)
