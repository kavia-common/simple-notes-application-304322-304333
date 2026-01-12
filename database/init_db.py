#!/usr/bin/env python3
"""Initialize/migrate SQLite database for the database container.

This script is designed to be safe to run multiple times (idempotent).
It will:
- Read the SQLite DB file path from db_connection.txt (required).
- Connect to that database file.
- Create the required `notes` table if it does not exist.
- Keep existing unrelated tables intact (no drops / destructive changes).
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Optional


def _read_db_path_from_db_connection_txt(file_path: str) -> str:
    """Read the DB file path from db_connection.txt.

    Expects a line like:
      # File path: /absolute/path/to/myapp.db

    Falls back to parsing:
      # Connection string: sqlite:////absolute/path/to/myapp.db

    Raises:
        FileNotFoundError: if db_connection.txt does not exist.
        ValueError: if a DB path cannot be derived.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"Required file '{file_path}' not found. Cannot determine SQLite DB path."
        )

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Prefer the explicit "File path:" entry
    m = re.search(r"^\s*#\s*File\s+path:\s*(.+?)\s*$", content, flags=re.MULTILINE)
    if m:
        candidate = m.group(1).strip()
        if candidate:
            return candidate

    # Fallback to parsing the connection string
    m = re.search(
        r"^\s*#\s*Connection\s+string:\s*sqlite:(/{1,4}.+?)\s*$",
        content,
        flags=re.MULTILINE,
    )
    if m:
        conn_str_path = m.group(1).strip()
        # Convert sqlite:////abs/path to /abs/path (keep absolute paths)
        candidate = conn_str_path
        while candidate.startswith("//"):
            candidate = candidate[1:]
        candidate = candidate.strip()
        if candidate:
            return candidate

    raise ValueError(
        f"Could not parse SQLite DB file path from '{file_path}'. "
        "Expected a '# File path: ...' or '# Connection string: sqlite:////...'."
    )


def _ensure_parent_dir_exists(db_path: str) -> None:
    """Ensure the directory for the db file exists."""
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _execute_one_statement(cursor: sqlite3.Cursor, sql: str) -> None:
    """Execute exactly one SQL statement.

    This enforces the container rule of one-statement-at-a-time execution.
    """
    statement = sql.strip().rstrip(";").strip() + ";"
    cursor.execute(statement)


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    """Return True if a table exists."""
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cursor.fetchone() is not None


# PUBLIC_INTERFACE
def init_and_migrate() -> str:
    """Initialize/migrate the SQLite database to include the notes schema.

    Returns:
        The resolved absolute path to the SQLite database file used.
    """
    # CRITICAL: Always read the DB path from db_connection.txt per requirements.
    db_connection_file = os.path.join(os.path.dirname(__file__), "db_connection.txt")
    db_path = _read_db_path_from_db_connection_txt(db_connection_file)
    db_path = os.path.abspath(db_path)

    _ensure_parent_dir_exists(db_path)

    print("Starting SQLite init/migration...")
    print(f"Using database file: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Create the required notes table if missing (idempotent).
        # Execute as ONE statement (no multi-line/multi-statement scripts).
        if not _table_exists(cursor, "notes"):
            print("Creating missing table: notes")
            _execute_one_statement(
                cursor,
                (
                    "CREATE TABLE IF NOT EXISTS notes ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "title TEXT NOT NULL, "
                    "content TEXT NOT NULL, "
                    "created_at TEXT NOT NULL, "
                    "updated_at TEXT NOT NULL"
                    ")"
                ),
            )
            conn.commit()
        else:
            print("Table already exists: notes (no action)")

        # Minimal stats (non-destructive)
        cursor.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        table_count = cursor.fetchone()[0]
        print(f"Database tables (excluding sqlite_ internal): {table_count}")

        return db_path
    finally:
        conn.close()


def main() -> None:
    """CLI entrypoint for init/migration."""
    try:
        db_path = init_and_migrate()
        print("SQLite init/migration complete.")
        print(f"Database path: {db_path}")
        print("Script completed successfully.")
    except Exception as e:
        # Fail loud so CI/previews clearly show migration issues.
        print(f"ERROR: SQLite init/migration failed: {e}")
        raise


if __name__ == "__main__":
    main()
