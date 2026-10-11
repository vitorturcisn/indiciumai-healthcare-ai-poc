"""Configuração da aplicação; segredos são sempre lidos do ambiente."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "indicium-healthcare-ai-poc"
APP_VERSION = "2.0.0"
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
SOURCE_DATASET_URL = "https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026"
ALLOWED_NEWS_DOMAINS = ("gov.br", "fiocruz.br", "who.int")
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "6"))
MAX_NEWS_RESULTS = int(os.getenv("MAX_NEWS_RESULTS", "5"))
NEWS_TIME_LIMIT = os.getenv("NEWS_TIME_LIMIT", "m")

PROJECT_DIR = Path(os.getenv("SRAG_PROJECT_DIR", Path.cwd())).resolve()
OUTPUT_DIR = Path(os.getenv("SRAG_OUTPUT_DIR", PROJECT_DIR / "outputs")).resolve()
DB_PATH = Path(os.getenv("SRAG_DB_PATH", OUTPUT_DIR / "srag_dados.db")).resolve()
AUDIT_PATH = Path(os.getenv("SRAG_AUDIT_PATH", OUTPUT_DIR / "audit_log.jsonl")).resolve()
DATA_QUALITY_PATH = Path(os.getenv("SRAG_QUALITY_PATH", OUTPUT_DIR / "qualidade_dados.json")).resolve()
REPORT_PATH = Path(os.getenv("SRAG_REPORT_PATH", OUTPUT_DIR / "relatorio_final.md")).resolve()

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
