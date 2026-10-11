"""Auditoria append-only em JSONL para decisões, tools, prompts e uso de tokens."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import APP_NAME, APP_VERSION, MODEL_NAME


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


class AuditLogger:
    """Escreve eventos antes/depois das ações; cada evento é uma linha JSON independente."""

    def __init__(self, path: Path, run_id: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id

    def append(self, event: str, payload: dict[str, Any] | None = None) -> None:
        record = {
            "run_id": self.run_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "app": APP_NAME,
            "app_version": APP_VERSION,
            "model": MODEL_NAME,
            "event": event,
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
