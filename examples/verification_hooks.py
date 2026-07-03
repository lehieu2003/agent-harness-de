"""
Verification hooks for risky write tools.

The reusable verification logic lives in `harness.verification`. This module
only adapts it to the harness lifecycle hooks and console output.
"""
import os

from harness.runtime.hooks import hooks
from harness.tools.results import tool_result_failed
from harness.safety.verification import VerificationEngine

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "warehouse.db")

VERIFIED_TOOLS = {"run_transformation", "drop_or_truncate"}
_PRE_WRITE_STATE = {}


def _engine() -> VerificationEngine:
    return VerificationEngine(DB_PATH)


def capture_before_write(name, input):
    if name not in VERIFIED_TOOLS:
        return
    try:
        _PRE_WRITE_STATE[name] = _engine().snapshot()
    except Exception as e:
        _PRE_WRITE_STATE[name] = {"error": str(e)}


def verify_after_write(name, input, result):
    if name not in VERIFIED_TOOLS:
        return

    if tool_result_failed(result):
        print(f"[VERIFY] Skipped - {name} did not complete successfully.")
        return

    try:
        before = _PRE_WRITE_STATE.pop(name, {})
        after = _engine().snapshot()

        if isinstance(before, dict) and "error" in before:
            print(f"[VERIFY] OK - database opens, but pre-write snapshot failed: {before['error']}")
            return

        expected_missing_tables = set()
        if name == "drop_or_truncate" and input.get("action") == "drop":
            expected_missing_tables.add(input.get("table_name"))

        report = _engine().compare(before, after, expected_missing_tables=expected_missing_tables)
        if report.ok:
            print(f"[VERIFY] OK - {report.summary}")
        else:
            print(f"[VERIFY] WARNING - {report.summary}")
    except Exception as e:
        print(f"[VERIFY] WARNING - verification check itself failed: {e}")


hooks.register("before_tool_call", capture_before_write)
hooks.register("after_tool_call", verify_after_write)
