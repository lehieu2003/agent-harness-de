"""
Conservative SQL safety checks for warehouse tools.

This is intentionally simple and defensive. It is not a full SQL parser; it
blocks risky shapes before SQLite sees them, and it keeps the decision visible
to tests and approval prompts.
"""
from dataclasses import dataclass
import re


READ_ONLY = "read"
WRITE = "write"
DESTRUCTIVE = "destructive"
UNKNOWN = "unknown"

_FIRST_KEYWORD = re.compile(r"^\s*([a-zA-Z]+)\b")
_DANGEROUS_KEYWORDS = re.compile(
    r"\b(DROP|TRUNCATE|ALTER|CREATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SqlSafetyResult:
    ok: bool
    classification: str
    summary: str
    error: str | None = None


def _without_trailing_semicolon(sql: str) -> str:
    stripped = sql.strip()
    if stripped.endswith(";"):
        return stripped[:-1].strip()
    return stripped


def has_multiple_statements(sql: str) -> bool:
    body = _without_trailing_semicolon(sql)
    in_single = False
    in_double = False

    for char in body:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ";" and not in_single and not in_double:
            return True
    return False


def classify_sql(sql: str) -> str:
    match = _FIRST_KEYWORD.search(sql)
    if not match:
        return UNKNOWN

    keyword = match.group(1).upper()
    if keyword in {"SELECT", "WITH", "EXPLAIN"}:
        return READ_ONLY
    if keyword in {"INSERT", "UPDATE", "DELETE"}:
        return WRITE
    if keyword in {"DROP", "TRUNCATE", "ALTER", "CREATE", "REPLACE", "MERGE"}:
        return DESTRUCTIVE
    return UNKNOWN


def validate_read_sql(sql: str) -> SqlSafetyResult:
    if has_multiple_statements(sql):
        return SqlSafetyResult(False, UNKNOWN, "Rejected: multiple SQL statements are not allowed.", "multiple_statements")

    classification = classify_sql(sql)
    if classification != READ_ONLY:
        return SqlSafetyResult(False, classification, "Rejected: read tools only allow SELECT-style SQL.", "non_read_sql")

    if _DANGEROUS_KEYWORDS.search(sql):
        return SqlSafetyResult(False, DESTRUCTIVE, "Rejected: destructive SQL keyword detected.", "destructive_sql")

    return SqlSafetyResult(True, READ_ONLY, "SQL is read-only.")


def validate_write_sql(sql: str) -> SqlSafetyResult:
    if has_multiple_statements(sql):
        return SqlSafetyResult(False, UNKNOWN, "Rejected: multiple SQL statements are not allowed.", "multiple_statements")

    classification = classify_sql(sql)
    if classification == DESTRUCTIVE or _DANGEROUS_KEYWORDS.search(sql):
        return SqlSafetyResult(False, DESTRUCTIVE, "Rejected: destructive SQL must use a dedicated destructive tool.", "destructive_sql")

    if classification != WRITE:
        return SqlSafetyResult(False, classification, "Rejected: transformations only allow INSERT, UPDATE, or DELETE.", "non_write_sql")

    first_keyword = _FIRST_KEYWORD.search(sql).group(1).upper()
    if first_keyword in {"UPDATE", "DELETE"} and not re.search(r"\bWHERE\b", sql, re.IGNORECASE):
        return SqlSafetyResult(False, WRITE, "Rejected: UPDATE and DELETE require a WHERE clause.", "missing_where")

    return SqlSafetyResult(True, WRITE, "SQL is an allowed write.")
