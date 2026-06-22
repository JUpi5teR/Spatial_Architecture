# coding: utf-8

"""Database initialisation script.

Run this script first to set up the database tables.

Usage:

    cd E:\Code\AI_exercise

    python scripts/init_db.py

If config/personal.json exists with PostgreSQL credentials, it will use PostgreSQL.

Otherwise, it falls back to SQLite (data/ai_exercise.db).

"""

from __future__ import annotations

import sys

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "front"))

from backend.database import Database, DBConfig

def main() -> None:

    config = DBConfig()

    print(f"Database engine: {config.engine}")

    if config.engine == "postgresql":

        print(f"  Host: {config.host}:{config.port}")

        print(f"  Database: {config.dbname}")

        print(f"  User: {config.user}")

    else:

        print(f"  SQLite path: {config.sqlite_path}")

    db = Database(config)

    db.connect()

    db.init_tables()

    print("Tables created successfully.")

    # Verify

    cur = db.execute("SELECT name FROM notebooks" if config.engine == "sqlite"

                     else "SELECT 1 FROM notebooks LIMIT 0")

    print("Verification: notebooks table exists.")

    cur.close()

    db.close()

    print("Database initialisation complete.")

if __name__ == "__main__":

    main()