# Agent Harness — mapped to the 9 components

Every one of the 9 harness components has a dedicated file. This README
maps each component directly to its implementation.

| # | Component | File | What it does |
|---|---|---|---|
| 1 | **While loop** (required) | `harness/core.py` | `Agent.run()` — the loop: call model → check for tool_use → execute → feed back → repeat |
| 2 | **Context mgmt** (required) | `harness/context.py` | Token estimation + compaction so long conversations don't blow the context window |
| 3 | **Skills & tools** | `harness/tools.py` | Tool registry — `@register_tool` decorator, schema generation, execution dispatch |
| 4 | **Sub-agents** | `harness/subagents.py` + `de_subagents.py` | Spawns a fresh, scoped `Agent` instance to delegate a sub-task (e.g. blast-radius estimation) |
| 5 | **Built-in skills** | `harness/skills.py` + `skills/*.md` | Loads markdown instructions into the system prompt when relevant |
| 6 | **Session persist** | `harness/session.py` | Save/load conversation JSON to resume later |
| 7 | **Prompt assembly** | `harness/core.py` (`Agent.run`, system prompt build) + `main_de.py` (`SYSTEM_PROMPT`) | Combines system prompt + skills + tools + history into the API call |
| 8 | **Lifecycle hooks** | `harness/hooks.py` + `verify.py` | Extension points (`before_turn`, `after_tool_call`, etc.) — `verify.py` uses `after_tool_call` to sanity-check writes |
| 9 | **Permissions** | `harness/permissions.py` | Risky-tool allowlist + approval gate before execution |

## Two harness instances built on this base

### Generic assistant — `main.py`
Uses `example_tools.py` (time, calculator, a "risky" delete-note tool).

### Senior Data Engineer — `main_de.py`
Domain-specific instance using every component:
- `db_setup.py` — mock SQLite warehouse with a **planted data quality bug**
  (`orders.status='void'` rows inflating a revenue pipeline)
- `de_tools.py` — read tools (`inspect_schema`, `run_query`, `profile_data`,
  `validate_sql`, `check_pipeline_status`) + write tools (`run_transformation`,
  `drop_or_truncate`). **`run_query` structurally rejects non-SELECT SQL in
  code** — permission enforcement isn't just prompt-based trust.
- `de_subagents.py` — registers `estimate_blast_radius`, a sub-agent scoped to
  read-only tools, delegated to before any non-trivial write
- `verify.py` — after every write, checks the DB is still structurally healthy
- `skills/senior_de_mindset.md` — investigate-before-acting, blast-radius
  thinking, distrust-anomalies-until-verified habits
- `skills/schema_context.md` — warehouse schema + the `'void'` status gotcha

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
```

## Run the generic assistant

```bash
python main.py
python main.py --resume <session_id>
python main.py --auto-approve
```

## Run the Senior Data Engineer agent

```bash
python db_setup.py     # once — creates warehouse.db
python main_de.py
```

Try: *"Why did the daily_revenue pipeline fail yesterday? Investigate and
propose a fix."* — it checks `pipeline_runs`, queries `orders`, finds the
`'void'` anomaly, delegates to `estimate_blast_radius` for a precise row
count, then asks for approval before writing anything.

## Extending each component

**Add a tool** (component 3) — in a new `*_tools.py` file:
```python
from harness.tools import register_tool

@register_tool("your_tool", {
    "name": "your_tool",
    "description": "...",
    "input_schema": {"type": "object", "properties": {...}, "required": [...]}
})
def your_tool(...):
    return "result"
```
Mark it risky (component 9) if it writes/deletes/sends anything:
```python
from harness.permissions import mark_risky
mark_risky("your_tool")
```

**Add a sub-agent** (component 4):
```python
from harness.subagents import make_subagent_tool

make_subagent_tool(
    name="your_subagent",
    description="...",
    allowed_tools=["read_only_tool_1", "read_only_tool_2"],
    system_prompt="You are a specialist in ..."
)
```

**Add a skill** (component 5) — drop a `.md` file in `skills/`, first line
is the description used for relevance matching.

**Add a hook** (component 8):
```python
from harness.hooks import hooks
hooks.register("after_tool_call", lambda name, input, result: ...)
```

## Known limitations / next upgrades

- **Sub-agent tool scoping** (`harness/subagents.py`) currently patches the
  global `get_tool_schemas` function during a sub-agent's run — fine for a
  starter harness, but a production version should give each `Agent`
  instance its own tool registry instead of sharing one global registry.
- **Skill routing** (`harness/skills.py`) uses keyword matching — upgrade to
  an LLM call or embedding search once you have more than a handful of skills.
- **Context compaction** (`harness/context.py`) drops old messages with a
  placeholder — upgrade to real LLM-generated summarization.
- **Token estimation** is a char/4 approximation — swap for a real tokenizer.
- **Verification** (`verify.py`) only checks structural DB health — extend
  with row-count-before-vs-after comparisons, schema diffing, etc.
