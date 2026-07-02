"""
COMPONENT 4 (concrete instance): a "blast radius estimator" sub-agent.

Before the main Data Engineer agent proposes a write, it can delegate
to this sub-agent to independently investigate how many rows/tables
would be affected. Runs with READ-ONLY tools only, in its own isolated
context — so its investigation doesn't bloat the main conversation.
"""
from harness.subagents import make_subagent_tool

make_subagent_tool(
    name="estimate_blast_radius",
    description=(
        "Delegate to a specialized sub-agent that investigates how many rows/tables "
        "a proposed change would affect, using only read-only tools. "
        "Call this BEFORE run_transformation for any non-trivial write."
    ),
    allowed_tools=["inspect_schema", "run_query", "profile_data"],
    system_prompt=(
        "You are a data-impact analyst. Given a description of a proposed change, "
        "use inspect_schema, run_query, and profile_data to determine exactly how many "
        "rows and which tables would be affected. Report a precise row count estimate "
        "and any risk factors (e.g. foreign key dependents). Be concise."
    ),
)
