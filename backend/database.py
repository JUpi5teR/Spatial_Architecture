# coding: utf-8

"""Database connection layer.



Supports PostgreSQL (primary) and SQLite (local fallback).

Configuration is loaded from config/personal.json.

"""

from __future__ import annotations



import json

import sqlite3

from pathlib import Path

from typing import Any, Optional



try:

    import psycopg2

    import psycopg2.extras

    HAS_PSYCOPG2 = True

except ImportError:

    HAS_PSYCOPG2 = False



import sys as _sys
from pathlib import Path as _Path
_front = _Path(__file__).resolve().parent.parent / "front"
if str(_front) not in _sys.path:
    _sys.path.insert(0, str(_front))
del _sys, _Path, _front

from utils.logger import logger



_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_CONFIG_PATH = _PROJECT_ROOT / "config" / "personal.json"





class DBConfig:

    """Database configuration loaded from personal.json."""



    def __init__(self) -> None:

        self.engine: str = "sqlite"

        self.host: str = "localhost"

        self.port: int = 5432

        self.dbname: str = "ai_exercise"

        self.user: str = "postgres"

        self.password: str = ""

        self.sqlite_path: str = str(_PROJECT_ROOT / "data" / "ai_exercise.db")

        self._load()



    def _load(self) -> None:

        if not _CONFIG_PATH.exists():

            logger.warning("config/personal.json not found, using SQLite fallback")

            return



        try:

            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:

                data = json.load(f)

        except (json.JSONDecodeError, OSError) as exc:

            logger.warning("Failed to read config: %s, using SQLite fallback", exc)

            return



        db_cfg = data.get("database", {})

        if not db_cfg:

            return



        self.host = db_cfg.get("host", self.host)

        self.port = db_cfg.get("port", self.port)

        self.dbname = db_cfg.get("dbname", self.dbname)

        self.user = db_cfg.get("user", self.user)

        self.password = db_cfg.get("password", self.password)



        if HAS_PSYCOPG2 and self.password:

            self.engine = "postgresql"

        else:

            logger.info("PostgreSQL unavailable or no password; using SQLite")





_config: Optional[DBConfig] = None





def get_config() -> DBConfig:

    global _config

    if _config is None:

        _config = DBConfig()

    return _config





class Database:

    """Unified database interface (PostgreSQL or SQLite)."""



    def __init__(self, config: Optional[DBConfig] = None) -> None:

        self._cfg = config or get_config()

        self._conn: Any = None



    # ------------------------------------------------------------------

    # Connection

    # ------------------------------------------------------------------

    def connect(self) -> None:

        if self._cfg.engine == "postgresql":
            try:
                self._connect_pg()
                return
            except Exception as exc:
                logger.warning(
                    "PostgreSQL connection failed: %s. Falling back to SQLite.", exc
                )
                self._cfg.engine = "sqlite"
        self._connect_sqlite()



    def _connect_pg(self) -> None:

        if not HAS_PSYCOPG2:

            raise RuntimeError("psycopg2 not installed; run: pip install psycopg2-binary")

        self._conn = psycopg2.connect(

            host=self._cfg.host,

            port=self._cfg.port,

            dbname=self._cfg.dbname,

            user=self._cfg.user,

            password=self._cfg.password,

        )

        self._conn.autocommit = False

        logger.info("PostgreSQL connected: %s:%s/%s", self._cfg.host, self._cfg.port, self._cfg.dbname)



    def _connect_sqlite(self) -> None:

        db_path = Path(self._cfg.sqlite_path)

        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(db_path))

        self._conn.row_factory = sqlite3.Row

        logger.info("SQLite connected: %s", db_path)



    def close(self) -> None:

        if self._conn:

            self._conn.close()

            self._conn = None



    @property

    def connection(self) -> Any:

        if self._conn is None:

            self.connect()

        return self._conn



    # ------------------------------------------------------------------

    # Execution helpers

    # ------------------------------------------------------------------

    def execute(self, sql: str, params: Any = None) -> Any:

        conn = self.connection

        if self._cfg.engine == "postgresql":

            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        else:

            cur = conn.cursor()

        cur.execute(sql, params or ())

        return cur



    def commit(self) -> None:

        if self._conn:

            self._conn.commit()



    def rollback(self) -> None:

        if self._conn:

            self._conn.rollback()



    # ------------------------------------------------------------------

    # Table initialisation

    # ------------------------------------------------------------------

    def init_tables(self) -> None:

        if self._cfg.engine == "postgresql":

            self._init_tables_pg()

        else:

            self._init_tables_sqlite()



    def _init_tables_pg(self) -> None:

        sql = """

        CREATE TABLE IF NOT EXISTS notebooks (

            id              SERIAL PRIMARY KEY,

            name            VARCHAR(255) NOT NULL,

            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),

            updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),

            status          VARCHAR(32) NOT NULL DEFAULT 'active',

            deleted_at      TIMESTAMP

        );



        CREATE TABLE IF NOT EXISTS datasets (

            id              SERIAL PRIMARY KEY,

            notebook_id     INTEGER NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,

            name            VARCHAR(255) NOT NULL,

            upload_time     TIMESTAMP NOT NULL DEFAULT NOW(),

            file_path       TEXT NOT NULL,

            preview_image   TEXT,

            ground_truth_path TEXT,

            results_path    TEXT,

            train_log_path  TEXT,

            status          VARCHAR(32) NOT NULL DEFAULT 'active',

            deleted_at      TIMESTAMP

        );



        CREATE INDEX IF NOT EXISTS idx_datasets_notebook

            ON datasets(notebook_id);



        CREATE INDEX IF NOT EXISTS idx_notebooks_deleted

            ON notebooks(deleted_at)

            WHERE deleted_at IS NOT NULL;

        """

        self.connection.cursor().execute(sql)

        self.commit()

        logger.info("PostgreSQL tables initialised")



    def _init_tables_sqlite(self) -> None:

        sql = """

        CREATE TABLE IF NOT EXISTS notebooks (

            id              INTEGER PRIMARY KEY AUTOINCREMENT,

            name            TEXT NOT NULL,

            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            status          TEXT NOT NULL DEFAULT 'active',

            deleted_at      TIMESTAMP

        );



        CREATE TABLE IF NOT EXISTS datasets (

            id              INTEGER PRIMARY KEY AUTOINCREMENT,

            notebook_id     INTEGER NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,

            name            TEXT NOT NULL,

            upload_time     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            file_path       TEXT NOT NULL,

            preview_image   TEXT,

            ground_truth_path TEXT,

            results_path    TEXT,

            train_log_path  TEXT,

            status          TEXT NOT NULL DEFAULT 'active',

            deleted_at      TIMESTAMP

        );



        CREATE INDEX IF NOT EXISTS idx_datasets_notebook

            ON datasets(notebook_id);

        """

        self.connection.executescript(sql)

        self.commit()

        logger.info("SQLite tables initialised")





# ------------------------------------------------------------------

# Global database instance (singleton)

# ------------------------------------------------------------------

_db_instance: Optional[Database] = None





def get_db() -> Database:

    global _db_instance

    if _db_instance is None:

        _db_instance = Database()

        _db_instance.connect()

        _db_instance.init_tables()

    return _db_instance