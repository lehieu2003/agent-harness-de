"""
Entry point: a simple CLI chat loop using the harness.

Usage:
    python -m interfaces.cli                 # start a new session
    python -m interfaces.cli --resume abc123 # resume a saved session
"""
import argparse

import examples.tools  # noqa: F401 (registers tools as a side effect)
from harness import Agent
from harness.core.session import new_session_id, save_session, load_session


SYSTEM_PROMPT = """You are a helpful, general-purpose assistant.
Use tools when they help you give an accurate answer. Be concise."""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", type=str, default=None, help="Session ID to resume")
    parser.add_argument("--auto-approve", action="store_true", help="Skip permission prompts")
    args = parser.parse_args()

    if args.resume:
        session_id = args.resume
        messages = load_session(session_id)
        print(f"Resumed session {session_id} ({len(messages)} messages)")
    else:
        session_id = new_session_id()
        messages = []
        print(f"New session: {session_id}")

    agent = Agent(system_prompt=SYSTEM_PROMPT, auto_approve=args.auto_approve)

    print("Type 'exit' to quit.\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue

        reply = agent.run(user_input, messages=messages)
        messages = agent.last_messages
        save_session(session_id, messages)

        print(f"\nAgent: {reply}\n")

    print(f"Session saved as: {session_id} (resume with --resume {session_id})")


if __name__ == "__main__":
    main()
