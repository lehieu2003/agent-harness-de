"""
Tools for the Data Engineer agent.

Design principle: read-only vs write is enforced IN CODE, not just via
the LLM's judgment or the approval prompt. A senior DE harness should
never rely on "the model probably won't run DROP TABLE" — it should be
structurally impossible for read tools to write, and structurally
required that write tools go through approval + verification.
"""
import sqlite3
import os

from harness.tools.registry import register_tool
from harness.safety.permissions import mark_risky
from harness.safety.sql_safety import validate_read_sql, validate_write_sql
from harness.tools.results import tool_error, tool_success
from harness.safety.verification import VerificationEngine

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "warehouse.db")
REQUIRED_WRITE_PLAN_FIELDS = {
    "expected_row_impact": "Expected row impact is required before a write.",
    "blast_radius": "Blast-radius estimate is required before a write.",
    "rollback_plan": "Rollback plan is required before a write.",
    "verification_plan": "Verification plan is required before a write.",
}


def _connect():
    if not os.path.exists(DB_PATH):
        raise RuntimeError("Database not found. Run `python -m scripts.db_setup` first.")
    return sqlite3.connect(DB_PATH)


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_names(cur) -> set[str]:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {r[0] for r in cur.fetchall()}


def _resolve_table_name(cur, table_name: str) -> str:
    if table_name not in _table_names(cur):
        raise ValueError(f"Table '{table_name}' not found.")
    return _quote_identifier(table_name)


def _validate_write_plan(**fields):
    missing = [
        name
        for name, message in REQUIRED_WRITE_PLAN_FIELDS.items()
        if not str(fields.get(name) or "").strip()
    ]
    if missing:
        return tool_error(
            summary="Missing write plan fields: " + ", ".join(missing) + ".",
            error="missing_write_plan",
            data={
                "missing_fields": missing,
                "required_fields": list(REQUIRED_WRITE_PLAN_FIELDS),
            },
        )
    return None


# ---------- Read-only tools (safe, no approval needed) ----------

@register_tool("inspect_schema", {
    "name": "inspect_schema",
    "description": "List all tables, or show columns/types for a specific table.",
    "input_schema": {
        "type": "object",
        "properties": {"table_name": {"type": "string", "description": "Leave empty to list all tables"}},
        "required": []
    }
})
def inspect_schema(table_name: str = ""):
    conn = _connect()
    cur = conn.cursor()
    if not table_name:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        conn.close()
        return tool_success(
            summary=f"Tables: {', '.join(tables)}",
            data={"tables": tables},
        )
    try:
        safe_table = _resolve_table_name(cur, table_name)
        cur.execute(f"PRAGMA table_info({safe_table})")
        cols = cur.fetchall()
        conn.close()
        columns = [{"name": c[1], "type": c[2]} for c in cols]
        return tool_success(
            summary="\n".join(f"{c['name']} ({c['type']})" for c in columns),
            data={"table": table_name, "columns": columns},
        )
    except ValueError as e:
        conn.close()
        return tool_error(summary=str(e), error="table_not_found")


@register_tool("run_query", {
    "name": "run_query",
    "description": "Run a READ-ONLY SQL query (SELECT only). Non-SELECT queries are rejected.",
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"]
    }
})
def run_query(sql: str):
    # Hard structural guard — not relying on the model to self-restrict.
    safety = validate_read_sql(sql)
    if not safety.ok:
        return tool_error(
            summary=safety.summary,
            error=safety.error or "unsafe_read_sql",
            data={"classification": safety.classification},
        )

    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        rows = cur.fetchmany(20)  # cap output — don't flood context with huge result sets
        col_names = [d[0] for d in cur.description] if cur.description else []
        total_hint = " (showing first 20 rows)" if len(rows) == 20 else ""
        conn.close()
        if not rows:
            return tool_success(
                summary="Query returned 0 rows.",
                data={"columns": col_names, "rows": [], "truncated": False},
            )
        header = " | ".join(col_names)
        body = "\n".join(" | ".join(str(v) for v in row) for row in rows)
        return tool_success(
            summary=f"{header}\n{body}{total_hint}",
            data={
                "columns": col_names,
                "rows": [list(row) for row in rows],
                "truncated": len(rows) == 20,
            },
        )
    except Exception as e:
        conn.close()
        return tool_error(summary=f"Query error: {e}", error=str(e))


@register_tool("profile_data", {
    "name": "profile_data",
    "description": "Get row count, null counts, and basic stats for a table's columns.",
    "input_schema": {
        "type": "object",
        "properties": {"table_name": {"type": "string"}},
        "required": ["table_name"]
    }
})
def profile_data(table_name: str):
    conn = _connect()
    cur = conn.cursor()
    try:
        safe_table = _resolve_table_name(cur, table_name)
        cur.execute(f"SELECT COUNT(*) FROM {safe_table}")
        total = cur.fetchone()[0]
        cur.execute(f"PRAGMA table_info({safe_table})")
        cols = [c[1] for c in cur.fetchall()]
        lines = [f"Total rows: {total}"]
        null_counts = {}
        for col in cols:
            safe_col = _quote_identifier(col)
            cur.execute(f"SELECT COUNT(*) FROM {safe_table} WHERE {safe_col} IS NULL")
            nulls = cur.fetchone()[0]
            null_counts[col] = nulls
            lines.append(f"  {col}: {nulls} nulls")
        conn.close()
        return tool_success(
            summary="\n".join(lines),
            data={
                "table": table_name,
                "total_rows": total,
                "null_counts": null_counts,
            },
        )
    except Exception as e:
        conn.close()
        return tool_error(summary=f"Error profiling table: {e}", error=str(e))


@register_tool("validate_sql", {
    "name": "validate_sql",
    "description": "Dry-run/validate SQL syntax without executing writes. Always call this before run_transformation.",
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"]
    }
})
def validate_sql(sql: str):
    safety = validate_read_sql(sql)
    if not safety.ok:
        safety = validate_write_sql(sql)
    if not safety.ok:
        return tool_error(
            summary=safety.summary,
            error=safety.error or "unsafe_sql",
            data={"classification": safety.classification},
        )

    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute("EXPLAIN QUERY PLAN " + sql)
        plan = cur.fetchall()
        conn.close()
        return tool_success(
            summary=f"Valid. Query plan: {plan}",
            data={"query_plan": [list(row) for row in plan]},
        )
    except Exception as e:
        conn.close()
        return tool_error(summary=f"Invalid SQL: {e}", error=str(e))


@register_tool("check_pipeline_status", {
    "name": "check_pipeline_status",
    "description": "Check recent pipeline run status and any error messages.",
    "input_schema": {
        "type": "object",
        "properties": {"pipeline_name": {"type": "string"}},
        "required": ["pipeline_name"]
    }
})
def check_pipeline_status(pipeline_name: str):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT run_date, status, error_message FROM pipeline_runs WHERE pipeline_name = ? ORDER BY run_id DESC LIMIT 5",
        (pipeline_name,)
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return tool_success(
            summary=f"No runs found for pipeline '{pipeline_name}'.",
            data={"pipeline_name": pipeline_name, "runs": []},
        )
    return tool_success(
        summary="\n".join(f"{r[0]} | {r[1]} | {r[2] or ''}" for r in rows),
        data={
            "pipeline_name": pipeline_name,
            "runs": [
                {"run_date": r[0], "status": r[1], "error_message": r[2]}
                for r in rows
            ],
        },
    )


# ---------- Write tools (risky — require approval + get verified) ----------

@register_tool("run_transformation", {
    "name": "run_transformation",
    "description": (
        "Execute a write query (INSERT/UPDATE/DELETE) against the warehouse. "
        "Requires approval. Always call validate_sql first. "
        "After this runs, a verification check will automatically run."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string"},
            "expected_row_impact": {"type": "string", "description": "Estimate how many rows this affects, and why."},
            "blast_radius": {"type": "string", "description": "Tables, rows, downstream jobs, and users that could be affected."},
            "rollback_plan": {"type": "string", "description": "Concrete rollback approach if the write is wrong."},
            "verification_plan": {"type": "string", "description": "Checks that prove the write behaved as intended."}
        },
        "required": ["sql", "expected_row_impact", "blast_radius", "rollback_plan", "verification_plan"]
    }
})
def run_transformation(
    sql: str,
    expected_row_impact: str = "",
    blast_radius: str = "",
    rollback_plan: str = "",
    verification_plan: str = "",
):
    plan_error = _validate_write_plan(
        expected_row_impact=expected_row_impact,
        blast_radius=blast_radius,
        rollback_plan=rollback_plan,
        verification_plan=verification_plan,
    )
    if plan_error:
        return plan_error

    safety = validate_write_sql(sql)
    if not safety.ok:
        return tool_error(
            summary=safety.summary,
            error=safety.error or "unsafe_write_sql",
            data={"classification": safety.classification},
        )

    conn = _connect()
    cur = conn.cursor()
    verifier = VerificationEngine(DB_PATH)
    try:
        before = verifier.snapshot(conn)
        cur.execute(sql)
        affected = cur.rowcount
        after = verifier.snapshot(conn)
        report = verifier.compare(before, after)
        if not report.ok:
            conn.rollback()
            conn.close()
            return tool_error(
                summary=report.summary + " Transaction rolled back.",
                error="verification_failed",
                data={"verification": report.to_dict()},
                warnings=report.warnings,
            )
        conn.commit()
        conn.close()
        return tool_success(
            summary=(
                f"Executed. Rows affected: {affected}. "
                f"(Estimated: {expected_row_impact}) {report.summary}"
            ),
            data={
                "rows_affected": affected,
                "write_plan": {
                    "expected_row_impact": expected_row_impact,
                    "blast_radius": blast_radius,
                    "rollback_plan": rollback_plan,
                    "verification_plan": verification_plan,
                },
                "verification": report.to_dict(),
            },
            warnings=report.warnings,
        )
    except Exception as e:
        conn.rollback()
        conn.close()
        return tool_error(summary=f"Transformation failed: {e}", error=str(e))


@register_tool("drop_or_truncate", {
    "name": "drop_or_truncate",
    "description": "DROP or DELETE ALL rows from a table. Extremely destructive — always requires explicit approval.",
    "input_schema": {
        "type": "object",
        "properties": {"table_name": {"type": "string"}, "action": {"type": "string", "enum": ["drop", "truncate"]}},
        "required": ["table_name", "action"]
    }
})
def drop_or_truncate(table_name: str, action: str):
    if action not in {"drop", "truncate"}:
        return tool_error(
            summary=f"Invalid destructive action '{action}'. Expected 'drop' or 'truncate'.",
            error="invalid_action",
            data={"table": table_name, "action": action},
        )

    conn = _connect()
    cur = conn.cursor()
    verifier = VerificationEngine(DB_PATH)
    try:
        before = verifier.snapshot(conn)
        safe_table = _resolve_table_name(cur, table_name)
        if action == "drop":
            cur.execute(f"DROP TABLE {safe_table}")
        else:
            cur.execute(f"DELETE FROM {safe_table}")
        after = verifier.snapshot(conn)
        expected_missing = {table_name} if action == "drop" else set()
        report = verifier.compare(before, after, expected_missing_tables=expected_missing)
        if not report.ok:
            conn.rollback()
            conn.close()
            return tool_error(
                summary=report.summary + " Transaction rolled back.",
                error="verification_failed",
                data={"table": table_name, "action": action, "verification": report.to_dict()},
                warnings=report.warnings,
            )
        conn.commit()
        conn.close()
        return tool_success(
            summary=f"{action.upper()} completed on {table_name}. {report.summary}",
            data={"table": table_name, "action": action, "verification": report.to_dict()},
            warnings=report.warnings,
        )
    except Exception as e:
        conn.rollback()
        conn.close()
        return tool_error(
            summary=f"Failed: {e}",
            error=str(e),
            data={"table": table_name, "action": action},
        )


mark_risky("run_transformation")
mark_risky("drop_or_truncate")
