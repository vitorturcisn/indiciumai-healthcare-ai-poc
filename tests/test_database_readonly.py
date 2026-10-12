import sqlite3

import pytest

from srag_poc.database import read_only_connection


def test_read_only_connection_allows_select_and_rejects_insert(tmp_path):
    db_path = tmp_path / "existing.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE sample (value INTEGER)")
        connection.execute("INSERT INTO sample (value) VALUES (1)")

    with read_only_connection(db_path) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO sample (value) VALUES (2)")


def test_missing_database_is_not_created(tmp_path):
    db_path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        with read_only_connection(db_path):
            pass
    assert not db_path.exists()
