"""Conexões SQLite somente leitura para as ferramentas analíticas."""

from __future__ import annotations

from contextlib import contextmanager
import sqlite3
from pathlib import Path
from typing import Iterator


@contextmanager
def read_only_connection(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Abre um banco existente sem permitir escrita ou criação acidental."""
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Banco SQLite não encontrado: {path.name}")

    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        yield connection
    finally:
        connection.close()
