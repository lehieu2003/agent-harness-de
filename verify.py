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


def verify_after_write(name, input, result):
    if name not in VERIFIED_TOOLS:
        return

    if "failed" in result.lower() or "error" in result.lower():
        print(f"[VERIFY] Skipped — {name} did not complete successfully.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        # Simple structural sanity check: DB still opens and has tables.
        if not tables:
            print("[VERIFY] ⚠️  WARNING: no tables found after write — possible data loss!")
        else:
            print(f"[VERIFY] OK — database still healthy, {len(tables)} tables present.")
    except Exception as e:
        print(f"[VERIFY] ⚠️  WARNING: verification check itself failed: {e}")
    finally:
        conn.close()


hooks.register("after_tool_call", verify_after_write)
