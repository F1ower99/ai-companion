import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from companion.domain.errors import StorageError
from companion.infrastructure.sqlite.migrations import apply_migrations


def default_database_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "AICompanion" / "companion.sqlite3"


class SQLiteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = sqlite3.connect(self.path, timeout=5.0)
        except (OSError, sqlite3.Error) as error:
            raise StorageError("Local database unavailable.") from error

        try:
            try:
                handle.row_factory = sqlite3.Row
                handle.execute("PRAGMA foreign_keys = ON")
                handle.execute("PRAGMA busy_timeout = 5000")
                apply_migrations(handle)
            except sqlite3.Error as error:
                handle.rollback()
                raise StorageError("Local database unavailable.") from error

            try:
                yield handle
                handle.commit()
            except sqlite3.Error as error:
                handle.rollback()
                raise StorageError("Local database unavailable.") from error
            except BaseException:
                handle.rollback()
                raise
        finally:
            handle.close()

    def initialize(self) -> None:
        with self.connection():
            pass
