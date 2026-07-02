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

DB_PATH = os.path.join(os.path.dirname(__file__), "warehouse.db")

WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE)\b",
    re.IGNORECASE
)


def _connect():
    if not os.path.exists(DB_PATH):
        raise RuntimeError("Database not found. Run `python db_setup.py` first.")
    return sqlite3.connect(DB_PATH)


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
        return f"Tables: {', '.join(tables)}"
    cur.execute(f"PRAGMA table_info({table_name})")
    cols = cur.fetchall()
    conn.close()
    if not cols:
        return f"Table '{table_name}' not found."
    return "\n".join(f"{c[1]} ({c[2]})" for c in cols)


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
        return ("REJECTED: run_query only allows SELECT statements. "
                "Use run_transformation for writes (requires approval).")
    if not sql.strip().upper().startswith("SELECT"):
        return "REJECTED: query must start with SELECT."

    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        rows = cur.fetchmany(20)  # cap output — don't flood context with huge result sets
        col_names = [d[0] for d in cur.description] if cur.description else []
        total_hint = " (showing first 20 rows)" if len(rows) == 20 else ""
        conn.close()
        if not rows:
            return "Query returned 0 rows."
        header = " | ".join(col_names)
        body = "\n".join(" | ".join(str(v) for v in row) for row in rows)
        return f"{header}\n{body}{total_hint}"
    except Exception as e:
        conn.close()
        return f"Query error: {e}"


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
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        total = cur.fetchone()[0]
        cur.execute(f"PRAGMA table_info({table_name})")
        cols = [c[1] for c in cur.fetchall()]
        lines = [f"Total rows: {total}"]
        for col in cols:
            cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {col} IS NULL")
            nulls = cur.fetchone()[0]
            lines.append(f"  {col}: {nulls} nulls")
        conn.close()
        return "\n".join(lines)
    except Exception as e:
        conn.close()
        return f"Error profiling table: {e}"


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
        return f"Valid. Query plan: {plan}"
    except Exception as e:
        conn.close()
        return f"Invalid SQL: {e}"


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
        return f"No runs found for pipeline '{pipeline_name}'."
    return "\n".join(f"{r[0]} | {r[1]} | {r[2] or ''}" for r in rows)


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
        if action == "drop":
            cur.execute(f"DROP TABLE {table_name}")
        else:
            cur.execute(f"DELETE FROM {table_name}")
        conn.commit()
        conn.close()
        return f"{action.upper()} completed on {table_name}."
    except Exception as e:
        conn.close()
        return f"Failed: {e}"


mark_risky("run_transformation")
mark_risky("drop_or_truncate")
