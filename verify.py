"""
Verification hook: after any risky write tool runs, automatically do a
sanity check and print a warning if something looks off.

This is the difference between an agent that just "executes what it
decided" and one that behaves like a senior engineer who double-checks
their own work before calling it done.
"""
import sqlite3
import os

from harness.hooks import hooks

DB_PATH = os.path.join(os.path.dirname(__file__), "warehouse.db")

VERIFIED_TOOLS = {"run_transformation", "drop_or_truncate"}
_PRE_WRITE_STATE = {}


def _snapshot_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        row_counts = {}
        for table in tables:
            safe_table = '"' + table.replace('"', '""') + '"'
            cur.execute(f"SELECT COUNT(*) FROM {safe_table}")
            row_counts[table] = cur.fetchone()[0]
        return {"tables": set(tables), "row_counts": row_counts}
    finally:
        conn.close()


def capture_before_write(name, input):
    if name not in VERIFIED_TOOLS:
        return
    try:
        _PRE_WRITE_STATE[name] = _snapshot_db()
    except Exception as e:
        _PRE_WRITE_STATE[name] = {"error": str(e)}


def verify_after_write(name, input, result):
    if name not in VERIFIED_TOOLS:
        return

    if "failed" in result.lower() or "error" in result.lower():
        print(f"[VERIFY] Skipped — {name} did not complete successfully.")
        return

    try:
        before = _PRE_WRITE_STATE.pop(name, {})
        after = _snapshot_db()
        tables = after["tables"]
        if not tables:
            print("[VERIFY] ⚠️  WARNING: no tables found after write — possible data loss!")
            return

        if "error" in before:
            print(f"[VERIFY] OK — database opens, but pre-write snapshot failed: {before['error']}")
            return

        missing_tables = before.get("tables", set()) - tables
        if missing_tables:
            expected_drop = (
                name == "drop_or_truncate"
                and input.get("action") == "drop"
                and input.get("table_name") in missing_tables
                and len(missing_tables) == 1
            )
            if not expected_drop:
                print(f"[VERIFY] ⚠️  WARNING: tables missing after write: {', '.join(sorted(missing_tables))}")
                return

        row_changes = []
        before_counts = before.get("row_counts", {})
        for table in sorted(tables & set(before_counts)):
            before_count = before_counts[table]
            after_count = after["row_counts"][table]
            if before_count != after_count:
                row_changes.append(f"{table}: {before_count} -> {after_count}")

        if row_changes:
            print(f"[VERIFY] OK — database healthy. Row count changes: {'; '.join(row_changes)}")
        else:
            print(f"[VERIFY] OK — database healthy, {len(tables)} tables present, no row-count changes detected.")
    except Exception as e:
        print(f"[VERIFY] ⚠️  WARNING: verification check itself failed: {e}")


hooks.register("before_tool_call", capture_before_write)
hooks.register("after_tool_call", verify_after_write)
