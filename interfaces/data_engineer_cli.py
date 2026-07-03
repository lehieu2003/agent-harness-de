"""
Senior Data Engineer agent — CLI entry point.

Setup:
    python -m scripts.db_setup              # create the mock warehouse (run once)
    python -m interfaces.data_engineer_cli  # start chatting with the agent

Try asking:
    "Why did the daily_revenue pipeline fail yesterday?"
    "Show me a profile of the orders table"
    "Fix the daily_revenue pipeline"   <- watch it ask for approval before writing
"""
import argparse

import examples.data_engineering_tools      # noqa: F401 — registers DE tools
import examples.data_engineering_subagents  # noqa: F401 — registers the blast-radius sub-agent
import examples.verification_hooks          # noqa: F401 — registers verification hook

from harness import Agent
from harness.core.session import new_session_id, save_session, load_session

SYSTEM_PROMPT = """You are a senior data engineer working inside a company's \
analytics warehouse. You have 8+ years of experience and you've been burned \
before by careless queries and silent data corruption — so you're careful, \
methodical, and you verify your own work.

You have access to tools to inspect schema, run read-only queries, profile \
data quality, check pipeline status, and (with approval) run transformations \
or destructive operations. Read-only tools are always safe to use freely — \
use them liberally to investigate before drawing conclusions.

Follow the senior engineer habits described in your skill instructions: \
investigate before acting, think about blast radius, distrust anomalies \
until verified, and communicate findings clearly and concisely.

For any non-trivial write (more than a handful of rows), delegate to the \
estimate_blast_radius sub-agent first to get an independent, precise row-count \
estimate before you propose the change to the user. Before calling \
run_transformation, provide expected_row_impact, blast_radius, rollback_plan, \
and verification_plan."""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", type=str, default=None)
    parser.add_argument("--auto-approve", action="store_true")
    args = parser.parse_args()

    if args.resume:
        session_id = args.resume
        messages = load_session(session_id)
        print(f"Resumed session {session_id} ({len(messages)} messages)")
    else:
        session_id = new_session_id()
        messages = []
        print(f"New session: {session_id}")

    agent = Agent(system_prompt=SYSTEM_PROMPT, auto_approve=args.auto_approve, max_turns=20)

    print("Senior Data Engineer agent ready. Type 'exit' to quit.\n")
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
