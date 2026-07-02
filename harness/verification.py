"""
Reusable database verification for write tools and lifecycle hooks.
"""
from dataclasses import dataclass, field
import sqlite3
from typing import Any


@dataclass(frozen=True)
class DbSnapshot:
    tables: set[str]
    row_counts: dict[str, int]
    schemas: dict[str, list[dict[str, Any]]]
    null_counts: dict[str, dict[str, int]]


@dataclass(frozen=True)
class VerificationReport:
    ok: bool
    summary: str
    missing_tables: list[str] = field(default_factory=list)
    added_tables: list[str] = field(default_factory=list)
    row_count_diffs: dict[str, dict[str, int]] = field(default_factory=dict)
    schema_diffs: dict[str, dict[str, Any]] = field(default_factory=dict)
    null_count_diffs: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "missing_tables": self.missing_tables,
            "added_tables": self.added_tables,
            "row_count_diffs": self.row_count_diffs,
            "schema_diffs": self.schema_diffs,
            "null_count_diffs": self.null_count_diffs,
            "warnings": self.warnings,
        }


class VerificationEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def snapshot(self, conn: sqlite3.Connection | None = None) -> DbSnapshot:
        should_close = conn is None
        conn = conn or sqlite3.connect(self.db_path)
        cur = conn.cursor()
        try:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cur.fetchall()}
            row_counts = {}
            schemas = {}
            null_counts = {}

            for table in sorted(tables):
                safe_table = self._quote_identifier(table)
                cur.execute(f"SELECT COUNT(*) FROM {safe_table}")
                row_counts[table] = cur.fetchone()[0]

                cur.execute(f"PRAGMA table_info({safe_table})")
                columns = [
                    {
                        "cid": col[0],
                        "name": col[1],
                        "type": col[2],
                        "notnull": col[3],
                        "default": col[4],
                        "pk": col[5],
                    }
                    for col in cur.fetchall()
                ]
                schemas[table] = columns

                table_null_counts = {}
                for column in columns:
                    safe_column = self._quote_identifier(column["name"])
                    cur.execute(f"SELECT COUNT(*) FROM {safe_table} WHERE {safe_column} IS NULL")
                    table_null_counts[column["name"]] = cur.fetchone()[0]
                null_counts[table] = table_null_counts

            return DbSnapshot(
                tables=tables,
                row_counts=row_counts,
                schemas=schemas,
                null_counts=null_counts,
            )
        finally:
            if should_close:
                conn.close()

    def compare(
        self,
        before: DbSnapshot,
        after: DbSnapshot,
        expected_missing_tables: set[str] | None = None,
    ) -> VerificationReport:
        expected_missing_tables = expected_missing_tables or set()
        missing_tables = sorted((before.tables - after.tables) - expected_missing_tables)
        expected_missing = sorted((before.tables - after.tables) & expected_missing_tables)
        added_tables = sorted(after.tables - before.tables)

        row_count_diffs = {}
        for table in sorted(before.tables & after.tables):
            before_count = before.row_counts[table]
            after_count = after.row_counts[table]
            if before_count != after_count:
                row_count_diffs[table] = {"before": before_count, "after": after_count}

        schema_diffs = {}
        for table in sorted(before.tables & after.tables):
            if before.schemas[table] != after.schemas[table]:
                schema_diffs[table] = {
                    "before": before.schemas[table],
                    "after": after.schemas[table],
                }

        null_count_diffs = {}
        for table in sorted(before.tables & after.tables):
            column_diffs = {}
            before_nulls = before.null_counts.get(table, {})
            after_nulls = after.null_counts.get(table, {})
            for column in sorted(set(before_nulls) | set(after_nulls)):
                before_count = before_nulls.get(column, 0)
                after_count = after_nulls.get(column, 0)
                if before_count != after_count:
                    column_diffs[column] = {"before": before_count, "after": after_count}
            if column_diffs:
                null_count_diffs[table] = column_diffs

        warnings = []
        if expected_missing:
            warnings.append(f"Expected dropped tables: {', '.join(expected_missing)}")
        if added_tables:
            warnings.append(f"Tables added: {', '.join(added_tables)}")
        if schema_diffs:
            warnings.append(f"Schema changed for: {', '.join(sorted(schema_diffs))}")

        if not after.tables:
            return VerificationReport(
                ok=False,
                summary="Verification failed: no tables found after write.",
                missing_tables=missing_tables,
                added_tables=added_tables,
                row_count_diffs=row_count_diffs,
                schema_diffs=schema_diffs,
                null_count_diffs=null_count_diffs,
                warnings=warnings,
            )

        if missing_tables:
            return VerificationReport(
                ok=False,
                summary=f"Verification failed: tables missing after write: {', '.join(missing_tables)}.",
                missing_tables=missing_tables,
                added_tables=added_tables,
                row_count_diffs=row_count_diffs,
                schema_diffs=schema_diffs,
                null_count_diffs=null_count_diffs,
                warnings=warnings,
            )

        parts = [f"database healthy, {len(after.tables)} tables present"]
        if row_count_diffs:
            changes = [
                f"{table}: {diff['before']} -> {diff['after']}"
                for table, diff in row_count_diffs.items()
            ]
            parts.append(f"row count changes: {'; '.join(changes)}")
        else:
            parts.append("no row-count changes detected")

        return VerificationReport(
            ok=True,
            summary="Verification OK: " + ", ".join(parts) + ".",
            missing_tables=missing_tables,
            added_tables=added_tables,
            row_count_diffs=row_count_diffs,
            schema_diffs=schema_diffs,
            null_count_diffs=null_count_diffs,
            warnings=warnings,
        )

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'
