# Advanced Harness Development Plan

This plan evolves the current Senior Data Engineer agent harness from a compact
demo into a stronger, testable, extensible agent runtime. The current harness
already has the 9 core components: loop, context management, tools, sub-agents,
built-in skills, session persistence, prompt assembly, hooks, and permissions.

## Current Baseline

The current architecture is:

```text
main.py / main_de.py
  -> Agent.run()
     -> build system prompt + skill instructions
     -> manage context
     -> call OpenAI with tool schemas
     -> execute tool calls with permissions
     -> fire lifecycle hooks
     -> save session
```

Important files:

- `harness/core.py` - main agent loop and OpenAI call.
- `harness/tools.py` - global tool registry and execution dispatch.
- `harness/context.py` - token estimation and message compaction.
- `harness/skills.py` - markdown skill loading and relevance matching.
- `harness/subagents.py` - scoped sub-agent tool creation.
- `harness/session.py` - session save/load.
- `harness/hooks.py` - lifecycle event registry.
- `harness/permissions.py` - risky-tool approval gate.
- `de_tools.py` - Senior Data Engineer warehouse tools.
- `verify.py` - post-write verification hooks.
- `tests/test_safety.py` - current safety tests.

## Target Architecture

Longer term, aim for this shape:

```text
CLI / UI
  -> Agent
     -> ModelClient
     -> PromptBuilder
     -> ContextManager
     -> SkillRouter
     -> ToolRegistry
     -> PermissionManager
     -> WarehouseClient
     -> VerificationEngine
     -> SessionStore
     -> ObservabilityLogger
     -> EvaluationSuite
```

The key goal is to keep `Agent.run()` small. The agent loop should orchestrate
components, not contain all model, prompt, tool, verification, and persistence
logic directly.

## Phase 1: Stabilize Core Boundaries

Goal: make the harness easier to extend without growing `harness/core.py`.

### Step 1.1: Extract model client

Create `harness/models.py`.

Responsibilities:

- Load `.env`.
- Validate `OPENAI_API_KEY`.
- Select model from `GPT_MODEL_MINI`, `GPT_MODEL_NANO`, or explicit override.
- Convert internal tool schemas to OpenAI function-tool schemas.
- Send chat completion requests.
- Return a small internal response object instead of raw SDK objects.

Suggested interface:

```python
class ModelClient:
    def complete(self, system: str, messages: list, tools: list[dict]) -> ModelResponse:
        ...
```

Verification:

```bash
python -m unittest discover -s tests
python -m py_compile main.py main_de.py harness/*.py
```

### Step 1.2: Extract prompt assembly

Create `harness/prompts.py`.

Responsibilities:

- Combine base system prompt with relevant skill blocks.
- Keep prompt-building logic out of `Agent.run()`.
- Make prompt assembly testable without calling the model.

Suggested interface:

```python
def build_system_prompt(base_prompt: str, user_message: str, use_skills: bool = True) -> str:
    ...
```

Tests to add:

- No skills matched returns the base prompt unchanged.
- Matched skills are appended under a clear heading.
- Skill routing can be disabled.

### Step 1.3: Add structured internal message helpers

Keep OpenAI message format at the boundary, but create helper functions for:

- user messages
- assistant messages
- tool result messages

This reduces format mistakes as the project grows.

Suggested file:

- `harness/messages.py`

## Phase 2: Structured Tool Results

Goal: make tool behavior easier for the model and tests to reason about.

### Step 2.1: Introduce a standard tool result envelope

Current tools return strings. Upgrade to a consistent shape:

```python
{
    "ok": True,
    "data": {},
    "warnings": [],
    "error": None,
}
```

Keep `execute_tool()` responsible for serializing the envelope to JSON before
passing it back to the model.

### Step 2.2: Update existing tools incrementally

Start with Data Engineer read-only tools:

- `inspect_schema`
- `run_query`
- `profile_data`
- `validate_sql`
- `check_pipeline_status`

Then update write tools:

- `run_transformation`
- `drop_or_truncate`

Tests to add:

- Successful tools return `ok=True`.
- Failed tools return `ok=False`.
- Tool exceptions are converted into structured errors.
- Tool results are JSON-serializable.

### Step 2.3: Preserve human-readable summaries

Add a `summary` field if needed:

```python
{
    "ok": True,
    "summary": "Query returned 3 rows.",
    "data": {"rows": [...]},
    "warnings": [],
    "error": None,
}
```

This gives the model a concise explanation plus structured data.

## Phase 3: Data Engineering Safety Layer

Goal: make writes safer and more senior-engineer-like.

### Step 3.1: Add a SQL safety module

Create `harness/sql_safety.py` or `de_sql_safety.py`.

Responsibilities:

- Classify SQL as read/write/destructive.
- Reject multiple statements unless explicitly allowed.
- Require `WHERE` for `UPDATE` and `DELETE`.
- Detect dangerous keywords.
- Parse table names where possible.

Start simple with conservative checks. Later, add a SQL parser library.

Tests to add:

- `SELECT` is allowed for read-only query.
- `DELETE FROM table` without `WHERE` is rejected.
- `DROP TABLE` is classified as destructive.
- Multiple statements are rejected.

### Step 3.2: Require write plan before write execution

Before `run_transformation`, require:

- SQL statement.
- Expected row impact.
- Blast-radius estimate.
- Rollback plan.
- Verification plan.

Potential schema:

```python
{
    "sql": "...",
    "expected_row_impact": "...",
    "blast_radius": "...",
    "rollback_plan": "...",
    "verification_plan": "..."
}
```

### Step 3.3: Add transaction support

For writes:

- Start transaction.
- Execute mutation.
- Run verification.
- Commit only if verification passes.
- Roll back if verification fails.

This is more realistic than verifying after commit.

### Step 3.4: Improve verification engine

Move verification logic from `verify.py` into a reusable class:

```python
class VerificationEngine:
    def snapshot(self) -> DbSnapshot:
        ...

    def compare(self, before: DbSnapshot, after: DbSnapshot) -> VerificationReport:
        ...
```

Checks to add:

- table existence
- row count diffs
- schema diffs
- null-count diffs
- distinct status/value checks
- domain-specific assertions for known pipelines

## Phase 4: Warehouse Abstraction

Goal: avoid hard-coding SQLite into data engineering tools.

### Step 4.1: Create `WarehouseClient`

Suggested file:

- `harness/warehouse.py`

Suggested interface:

```python
class WarehouseClient:
    def list_tables(self) -> list[str]:
        ...

    def describe_table(self, table_name: str) -> list[dict]:
        ...

    def run_read_query(self, sql: str) -> QueryResult:
        ...

    def run_write_query(self, sql: str) -> WriteResult:
        ...
```

### Step 4.2: Implement SQLite adapter

Move SQLite-specific logic from `de_tools.py` into:

- `harness/warehouse_sqlite.py`

Keep `de_tools.py` as tool wrappers around the adapter.

### Step 4.3: Add future adapters

After SQLite is cleanly abstracted, add adapters in this order:

1. Postgres
2. BigQuery
3. Snowflake
4. Databricks

Do not add all adapters at once. Add one adapter with tests before moving on.

## Phase 5: Better Context Management

Goal: preserve important state instead of dropping old messages.

### Step 5.1: Add real conversation summaries

Create `harness/memory.py`.

Instead of:

```text
[10 earlier messages omitted to save context space]
```

Store:

- user goal
- decisions made
- tools called
- data facts discovered
- open questions
- pending approvals
- warnings

### Step 5.2: Separate short-term and long-term memory

Short-term:

- recent raw messages
- latest tool calls

Long-term:

- durable summaries
- facts about warehouse schema
- previously approved operations
- known incidents

### Step 5.3: Add tests for compaction

Tests:

- Recent messages are preserved.
- Summary is inserted when history is long.
- Tool results are summarized without losing critical errors.
- Pending approvals are not dropped.

## Phase 6: Better Skill Routing

Goal: load the right skill reliably.

### Step 6.1: Improve metadata format

Give each skill frontmatter:

```markdown
---
name: senior_de_mindset
description: Senior data engineering investigation habits.
triggers:
  - pipeline failure
  - data quality
  - blast radius
---
```

### Step 6.2: Add deterministic trigger matching

Before embeddings or model routing, improve simple matching:

- exact phrase matching
- trigger list
- filename fallback
- case normalization

### Step 6.3: Add optional model-based routing

Later, let the model choose relevant skills from metadata.

Important rule:

- Skill routing should be inspectable. Log which skills were loaded and why.

## Phase 7: Observability and Audit Trail

Goal: make agent behavior debuggable and reviewable.

### Step 7.1: Add structured logging

Create `harness/observability.py`.

Log events:

- session started
- user message received
- model called
- model returned tool calls
- tool started
- tool completed
- permission requested
- permission approved/denied
- verification passed/failed
- final answer returned

Use JSON Lines:

```text
logs/sessions/<session_id>.jsonl
```

### Step 7.2: Redact sensitive data

Never log:

- API keys
- secrets
- full `.env`
- credentials in SQL connection strings

### Step 7.3: Add session replay

Create a tool or command to inspect a past session:

```bash
python tools/replay_session.py <session_id>
```

## Phase 8: Evaluation Suite

Goal: measure whether the agent behaves like a Senior Data Engineer.

### Step 8.1: Create deterministic eval tasks

Suggested eval cases:

1. Detect `orders.status='void'` revenue anomaly.
2. Explain failed `daily_revenue` pipeline.
3. Refuse unsafe `DROP TABLE orders` without approval.
4. Require blast-radius estimation before write.
5. Propose SQL fix but ask approval before execution.
6. Detect missing `WHERE` in destructive SQL.
7. Summarize data quality profile.
8. Recover from invalid SQL.

### Step 8.2: Add mocked model tests

Do not rely on live API for CI.

Create fake model responses that:

- request tools
- return invalid tool JSON
- request disallowed tools
- return final answers

### Step 8.3: Add live smoke test separately

Live tests should be opt-in:

```bash
python scripts/smoke_openai_agent.py
```

Only run when `OPENAI_API_KEY` is present.

## Phase 9: Approval UX

Goal: make human approval clear enough for risky data operations.

### Step 9.1: Improve terminal approval prompt

For writes, show:

- tool name
- SQL
- affected tables
- estimated rows
- blast-radius summary
- rollback plan
- verification plan

### Step 9.2: Require typed confirmation for destructive operations

For `drop_or_truncate`, require the user to type:

```text
DROP orders
```

or:

```text
TRUNCATE orders
```

This prevents accidental `y` approvals.

### Step 9.3: Store approval records

Each approval record should include:

- timestamp
- session ID
- tool name
- input
- user decision
- verification result

## Phase 10: CLI and Developer Experience

Goal: make the project easier to run, test, and debug.

### Step 10.1: Add CLI commands

Potential commands:

```bash
python -m harness.cli chat-de
python -m harness.cli chat-generic
python -m harness.cli list-sessions
python -m harness.cli replay-session <session_id>
python -m harness.cli run-evals
```

### Step 10.2: Add Makefile or task script

For Windows compatibility, a Python task runner may be better:

```bash
python tasks.py test
python tasks.py compile
python tasks.py smoke
python tasks.py reset-db
```

### Step 10.3: Add README quickstart paths

Separate quickstarts:

- local tests without API key
- live OpenAI run
- Senior DE demo
- adding a new tool
- adding a new skill

## Recommended Implementation Order

Do not build everything at once. Use this order:

1. Extract `ModelClient` from `harness/core.py`.
2. Extract prompt assembly into `harness/prompts.py`.
3. Add structured tool result envelope.
4. Add SQL safety module.
5. Improve write approval schema and prompt.
6. Move SQLite logic into a warehouse adapter.
7. Add better verification engine.
8. Add observability JSONL logs.
9. Add mocked model evaluation tests.
10. Add real context summarization.
11. Improve skill metadata and routing.
12. Add Postgres adapter.
13. Add live smoke tests.
14. Add session replay tooling.

## Definition of Done for Each Phase

Each phase should include:

- Code change.
- Unit tests.
- README or docs update if user behavior changes.
- Fresh verification run.
- Commit with a clear message.

Minimum verification:

```bash
python -m unittest discover -s tests
python -m py_compile main.py main_de.py example_tools.py de_tools.py de_subagents.py verify.py db_setup.py harness/*.py tests/*.py
```

For live OpenAI behavior:

```bash
python db_setup.py
python main_de.py
```

Then ask:

```text
Why did the daily_revenue pipeline fail yesterday?
```

Expected high-level behavior:

1. Agent checks pipeline status.
2. Agent inspects schema.
3. Agent queries `orders`.
4. Agent identifies `void` orders as revenue anomaly candidates.
5. Agent uses blast-radius estimation before any non-trivial write.
6. Agent asks for approval before mutation.
7. Verification runs after write.

## Near-Term Milestone Proposal

Start with Milestone 1:

```text
Milestone 1: Core Runtime Refactor
```

Scope:

- `harness/models.py`
- `harness/prompts.py`
- `harness/messages.py`
- tests for model boundary and prompt assembly
- no behavior change to user-facing CLI

Why first:

This makes the rest of the advanced work safer. Once the model boundary,
prompt assembly, and message formatting are isolated, the harness can grow
without making `Agent.run()` fragile.
