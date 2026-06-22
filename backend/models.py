# coding: utf-8

"""Data models for notebook and dataset management.



Provides CRUD operations for notebooks and datasets.

All database operations go through the Database layer.

"""

from __future__ import annotations



from dataclasses import dataclass, field

from datetime import datetime

from typing import Any, Optional



from backend.database import get_db

import sys as _sys
from pathlib import Path as _Path
_front = _Path(__file__).resolve().parent.parent / "front"
if str(_front) not in _sys.path:
    _sys.path.insert(0, str(_front))
del _sys, _Path, _front

from utils.logger import logger





# ====================================================================

# Data classes

# ====================================================================

@dataclass

class Notebook:

    id: int = 0

    name: str = ""

    created_at: str = ""

    updated_at: str = ""

    status: str = "active"

    deleted_at: Optional[str] = None



    @property

    def is_deleted(self) -> bool:

        return self.deleted_at is not None





@dataclass

class Dataset:

    id: int = 0

    notebook_id: int = 0

    name: str = ""

    upload_time: str = ""

    file_path: str = ""

    preview_image: Optional[str] = None

    ground_truth_path: Optional[str] = None

    results_path: Optional[str] = None

    train_log_path: Optional[str] = None

    status: str = "active"

    deleted_at: Optional[str] = None



    @property

    def is_deleted(self) -> bool:

        return self.deleted_at is not None





# ====================================================================

# Notebook CRUD

# ====================================================================

class NotebookManager:

    """Manages notebook lifecycle."""



    def __init__(self) -> None:

        self._db = get_db()



    def create(self, name: str) -> Notebook:

        cur = self._db.execute(

            "INSERT INTO notebooks (name) VALUES (?)" if self._is_sqlite()

            else "INSERT INTO notebooks (name) VALUES (%s)",

            (name,)

        )

        self._db.commit()

        nb_id = cur.lastrowid

        logger.info("Created notebook: id=%s name=%s", nb_id, name)

        return self.get_by_id(nb_id)



    def get_by_id(self, notebook_id: int) -> Optional[Notebook]:

        cur = self._db.execute(

            "SELECT * FROM notebooks WHERE id = ?" if self._is_sqlite()

            else "SELECT * FROM notebooks WHERE id = %s",

            (notebook_id,)

        )

        row = cur.fetchone()

        return self._row_to_notebook(row) if row else None



    def list_active(self) -> list[Notebook]:

        cur = self._db.execute(

            "SELECT * FROM notebooks WHERE deleted_at IS NULL ORDER BY updated_at DESC"

        )

        return [self._row_to_notebook(r) for r in cur.fetchall()]



    def list_trash(self) -> list[Notebook]:

        cur = self._db.execute(

            "SELECT * FROM notebooks WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"

        )

        return [self._row_to_notebook(r) for r in cur.fetchall()]



    def update_name(self, notebook_id: int, new_name: str) -> bool:

        self._db.execute(

            "UPDATE notebooks SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?" if self._is_sqlite()

            else "UPDATE notebooks SET name = %s, updated_at = NOW() WHERE id = %s",

            (new_name, notebook_id)

        )

        self._db.commit()

        return True



    def soft_delete(self, notebook_id: int) -> bool:

        self._db.execute(

            "UPDATE notebooks SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?" if self._is_sqlite()

            else "UPDATE notebooks SET deleted_at = NOW(), updated_at = NOW() WHERE id = %s",

            (notebook_id,)

        )

        self._db.commit()

        logger.info("Soft-deleted notebook: id=%s", notebook_id)

        return True



    def restore(self, notebook_id: int) -> bool:

        self._db.execute(

            "UPDATE notebooks SET deleted_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?" if self._is_sqlite()

            else "UPDATE notebooks SET deleted_at = NULL, updated_at = NOW() WHERE id = %s",

            (notebook_id,)

        )

        self._db.commit()

        logger.info("Restored notebook: id=%s", notebook_id)

        return True



    def permanent_delete(self, notebook_id: int) -> bool:

        self._db.execute(

            "DELETE FROM notebooks WHERE id = ?" if self._is_sqlite()

            else "DELETE FROM notebooks WHERE id = %s",

            (notebook_id,)

        )

        self._db.commit()

        logger.info("Permanently deleted notebook: id=%s", notebook_id)

        return True



    def touch(self, notebook_id: int) -> None:

        self._db.execute(

            "UPDATE notebooks SET updated_at = CURRENT_TIMESTAMP WHERE id = ?" if self._is_sqlite()

            else "UPDATE notebooks SET updated_at = NOW() WHERE id = %s",

            (notebook_id,)

        )

        self._db.commit()



    # ------------------------------------------------------------------

    # Internal

    # ------------------------------------------------------------------

    def _is_sqlite(self) -> bool:

        return getattr(self._db, "_cfg").engine == "sqlite"



    @staticmethod

    def _row_to_notebook(row: Any) -> Notebook:

        if isinstance(row, dict):

            return Notebook(

                id=row["id"], name=row["name"],

                created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),

                status=row.get("status", "active"), deleted_at=row.get("deleted_at"),

            )

        return Notebook(

            id=row[0], name=row[1],

            created_at=str(row[2]), updated_at=str(row[3]),

            status=row[4] if len(row) > 4 else "active",

            deleted_at=row[5] if len(row) > 5 else None,

        )





# ====================================================================

# Dataset CRUD

# ====================================================================

class DatasetManager:

    """Manages dataset lifecycle within a notebook."""



    def __init__(self) -> None:

        self._db = get_db()



    def create(

        self,

        notebook_id: int,

        name: str,

        file_path: str,

        preview_image: Optional[str] = None,

        ground_truth_path: Optional[str] = None,

        results_path: Optional[str] = None,

        train_log_path: Optional[str] = None,

    ) -> Dataset:

        cur = self._db.execute(

            (

                "INSERT INTO datasets (notebook_id, name, file_path, preview_image, "

                "ground_truth_path, results_path, train_log_path) "

                "VALUES (?, ?, ?, ?, ?, ?, ?)"

            ) if self._is_sqlite() else (

                "INSERT INTO datasets (notebook_id, name, file_path, preview_image, "

                "ground_truth_path, results_path, train_log_path) "

                "VALUES (%s, %s, %s, %s, %s, %s, %s)"

            ),

            (notebook_id, name, file_path, preview_image, ground_truth_path, results_path, train_log_path)

        )

        self._db.commit()

        ds_id = cur.lastrowid

        logger.info("Created dataset: id=%s notebook=%s name=%s", ds_id, notebook_id, name)

        return self.get_by_id(ds_id)



    def get_by_id(self, dataset_id: int) -> Optional[Dataset]:

        cur = self._db.execute(

            "SELECT * FROM datasets WHERE id = ?" if self._is_sqlite()

            else "SELECT * FROM datasets WHERE id = %s",

            (dataset_id,)

        )

        row = cur.fetchone()

        return self._row_to_dataset(row) if row else None



    def list_by_notebook(self, notebook_id: int) -> list[Dataset]:

        cur = self._db.execute(

            "SELECT * FROM datasets WHERE notebook_id = ? AND deleted_at IS NULL ORDER BY upload_time DESC" if self._is_sqlite()

            else "SELECT * FROM datasets WHERE notebook_id = %s AND deleted_at IS NULL ORDER BY upload_time DESC",

            (notebook_id,)

        )

        return [self._row_to_dataset(r) for r in cur.fetchall()]



    def list_all_active(self) -> list[Dataset]:

        cur = self._db.execute(

            "SELECT d.*, n.name AS notebook_name FROM datasets d "

            "LEFT JOIN notebooks n ON d.notebook_id = n.id "

            "WHERE d.deleted_at IS NULL ORDER BY d.upload_time DESC"

        )

        return [self._row_to_dataset(r) for r in cur.fetchall()]



    def update_name(self, dataset_id: int, new_name: str) -> bool:

        self._db.execute(

            "UPDATE datasets SET name = ? WHERE id = ?" if self._is_sqlite()

            else "UPDATE datasets SET name = %s WHERE id = %s",

            (new_name, dataset_id)

        )

        self._db.commit()

        return True



    def soft_delete(self, dataset_id: int) -> bool:

        self._db.execute(

            "UPDATE datasets SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?" if self._is_sqlite()

            else "UPDATE datasets SET deleted_at = NOW() WHERE id = %s",

            (dataset_id,)

        )

        self._db.commit()

        return True



    def permanent_delete(self, dataset_id: int) -> bool:

        self._db.execute(

            "DELETE FROM datasets WHERE id = ?" if self._is_sqlite()

            else "DELETE FROM datasets WHERE id = %s",

            (dataset_id,)

        )

        self._db.commit()

        return True



    def count_by_notebook(self, notebook_id: int) -> int:

        cur = self._db.execute(

            "SELECT COUNT(*) FROM datasets WHERE notebook_id = ? AND deleted_at IS NULL" if self._is_sqlite()

            else "SELECT COUNT(*) FROM datasets WHERE notebook_id = %s AND deleted_at IS NULL",

            (notebook_id,)

        )

        row = cur.fetchone()

        if isinstance(row, dict):

            return row.get("count", 0) or row.get("COUNT(*)", 0)

        return row[0] if row else 0



    # ------------------------------------------------------------------

    # Internal

    # ------------------------------------------------------------------

    def _is_sqlite(self) -> bool:

        return getattr(self._db, "_cfg").engine == "sqlite"



    @staticmethod

    def _row_to_dataset(row: Any) -> Dataset:

        if isinstance(row, dict):

            return Dataset(

                id=row["id"], notebook_id=row["notebook_id"], name=row["name"],

                upload_time=str(row["upload_time"]), file_path=row["file_path"],

                preview_image=row.get("preview_image"),

                ground_truth_path=row.get("ground_truth_path"),

                results_path=row.get("results_path"),

                train_log_path=row.get("train_log_path"),

                status=row.get("status", "active"), deleted_at=row.get("deleted_at"),

            )

        return Dataset(

            id=row[0], notebook_id=row[1], name=row[2],

            upload_time=str(row[3]), file_path=row[4],

            preview_image=row[5] if len(row) > 5 else None,

            ground_truth_path=row[6] if len(row) > 6 else None,

            results_path=row[7] if len(row) > 7 else None,

            train_log_path=row[8] if len(row) > 8 else None,

            status=row[9] if len(row) > 9 else "active",

            deleted_at=row[10] if len(row) > 10 else None,

        )