"""
Tools for the Data Engineer agent.

Design principle: read-only vs write is enforced IN CODE, not just via
the LLM's judgment or the approval prompt. A senior DE harness should
never rely on "the model probably won't run DROP TABLE" — it should be
structurally impossible for read tools to write, and structurally
required that write tools go through approval + verification.
"""
import sqlite3
import re
import os

from harness.tools import register_tool
from harness.permissions import mark_risky
from harness.tool_results import tool_error, tool_success

DB_PATH = os.path.join(os.path.dirname(__file__), "warehouse.db")

WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE)\b",
    re.IGNORECASE
)


def _connect():
    if not os.path.exists(DB_PATH):
        raise RuntimeError("Database not found. Run `python db_setup.py` first.")
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
    if WRITE_KEYWORDS.search(sql):
        return tool_error(
            summary=("REJECTED: run_query only allows SELECT statements. "
                     "Use run_transformation for writes (requires approval)."),
            error="write_sql_rejected",
        )
    if not sql.strip().upper().startswith("SELECT"):
        return tool_error(
            summary="REJECTED: query must start with SELECT.",
            error="non_select_sql_rejected",
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
            "expected_row_impact": {"type": "string", "description": "Your estimate of how many rows this affects, and why — shown to the user for approval."}
        },
        "required": ["sql", "expected_row_impact"]
    }
})
def run_transformation(sql: str, expected_row_impact: str):
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return f"Executed. Rows affected: {affected}. (Estimated: {expected_row_impact})"
    except Exception as e:
        conn.close()
        return f"Transformation failed: {e}"


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
    conn = _connect()
    cur = conn.cursor()
    try:
        safe_table = _resolve_table_name(cur, table_name)
        if action == "drop":
            cur.execute(f"DROP TABLE {safe_table}")
        else:
            cur.execute(f"DELETE FROM {safe_table}")
        conn.commit()
        conn.close()
        return f"{action.upper()} completed on {table_name}."
    except Exception as e:
        conn.close()
        return f"Failed: {e}"


mark_risky("run_transformation")
mark_risky("drop_or_truncate")
