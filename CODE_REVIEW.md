## Code Review: Senior Data Engineer Agent Harness

**Scope**: Whole codebase review. This workspace is not a Git repository, so there was no diff to inspect.

**Verification**: `python -m py_compile ...` passed for all Python files. No test files were present at review time.

### Findings

### HIGH: Sub-agent tool scoping is ineffective

**File**: `harness/subagents.py`, `harness/core.py`

**Issue**: `make_subagent_tool()` patches `harness.tools.get_tool_schemas`, but `harness/core.py` imports `get_tool_schemas` directly at module import time. `Agent.run()` keeps using the original function reference, so the sub-agent still receives the full global tool list.

**Why it matters**: The README and prompt say the blast-radius sub-agent is read-only, but in practice it can be offered risky write tools such as `run_transformation` and `drop_or_truncate`.

**Suggestion**: Move tool registry/scoping onto the `Agent` instance, or have `core.py` import the tools module dynamically. The better design is per-agent tool scoping.

### MEDIUM: Read-only SQL helper tools interpolate identifiers unsafely

**File**: `de_tools.py`

**Issue**: `inspect_schema()` and `profile_data()` insert `table_name` and column names directly into SQL strings.

**Why it matters**: SQLite parameter binding cannot bind identifiers, but this still needs validation. A model- or user-provided table name can break queries, inspect unexpected objects, or create expensive malformed SQL. In a real warehouse, this pattern becomes a serious injection risk.

**Suggestion**: Validate identifiers against `sqlite_master` first, then quote them safely. Do not execute SQL using raw model-provided identifier text.

### MEDIUM: Session IDs allow path traversal

**File**: `harness/session.py`

**Issue**: `session_id` is concatenated into a path without validation.

**Why it matters**: `python main_de.py --resume ..\somefile` can read outside `sessions/` if the path resolves to an existing JSON file. If save is ever exposed outside the CLI, it can also write outside the intended session directory.

**Suggestion**: Restrict session IDs to a safe regex such as `^[a-zA-Z0-9_-]+$`, resolve the final path, and assert it remains under `SESSIONS_DIR`.

### MEDIUM: Verification hook can report destructive changes as healthy

**File**: `verify.py`

**Issue**: The post-write verification only checks that the database still has at least one table.

**Why it matters**: `drop_or_truncate("orders")` would still report OK if other tables remain. For a Senior Data Engineer harness, that can falsely reassure the agent/user after data loss.

**Suggestion**: Capture expected table list, row counts, and schema before risky writes, then compare after execution. At minimum, verify the targeted table still exists unless the approved action was explicitly `drop`.

### LOW: No automated tests for the critical harness guarantees

**File**: codebase-wide

**Issue**: There are no tests covering tool permissioning, read-only SQL rejection, sub-agent scoping, session persistence, or verification behavior.

**Why it matters**: The most important promise in this project is safety by construction. The current sub-agent scoping bug is exactly the kind of regression a focused test would catch.

**Suggestion**: Add tests for sub-agent scoping, risky-tool approval behavior, read-only SQL rejection, session path validation, and write verification.

### Recommended Priority

1. Fix sub-agent scoping.
2. Harden SQL identifier handling.
3. Validate session IDs.
4. Strengthen write verification.
5. Add tests for the harness safety guarantees.
