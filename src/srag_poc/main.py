"""CLI da PoC. Exemplo: python -m srag_poc.main --csv data/INFLUD24.csv --csv data/INFLUD25.csv"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Sequence

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from . import __version__
from .agent import build_agent
from .audit import AuditLogger, sha256_text
from .config import AUDIT_PATH, DB_PATH, MODEL_NAME, OUTPUT_DIR, REPORT_PATH
from .guardrails import validate_user_request
from .ingestion import load_and_clean_csvs, write_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("srag_poc")
DEFAULT_REQUEST = "Gere o relatório epidemiológico nacional de SRAG com indicadores, gráficos de 30 dias e 12 meses, e contexto institucional recente."


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera relatório epidemiológico de SRAG com ferramentas determinísticas e LLM.")
    parser.add_argument("--csv", action="append", required=True, help="Caminho para um CSV DATASUS. Informe a flag repetidamente para combinar anos.")
    parser.add_argument("--request", default=DEFAULT_REQUEST, help="Solicitação do relatório; passa pelo guardrail de entrada.")
    parser.add_argument("--model", default=MODEL_NAME, help="Modelo Google Gemini com suporte a tool calling.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = uuid.uuid4().hex
    audit = AuditLogger(AUDIT_PATH, run_id)
    audit.append("run_started", {
        "app_version": __version__,
        "model": args.model,
        "request_sha256": sha256_text(args.request),
        "request_length": len(args.request),
        "csv_files": [Path(item).name for item in args.csv],
    })

    try:
        # Rejeita entrada insegura antes de ler os dados ou chamar serviços externos.
        try:
            safe_request = validate_user_request(args.request)
        except ValueError as exc:
            audit.append("input_guardrail_blocked", {"request_sha256": sha256_text(args.request), "reason": str(exc)})
            print(f"Solicitação bloqueada pelo guardrail: {exc}", file=sys.stderr)
            return 2
        csv_paths = [Path(item).expanduser().resolve() for item in args.csv]
        missing = [str(path) for path in csv_paths if not path.is_file()]
        if missing:
            raise FileNotFoundError("CSV(s) não encontrado(s): " + ", ".join(missing))

        logger.info("Carregando e minimizando %d arquivo(s) CSV.", len(csv_paths))
        frame, quality = load_and_clean_csvs(csv_paths)
        write_database(frame, DB_PATH, quality)
        audit.append("data_prepared", {
            "database_path": str(DB_PATH),
            "rows_after_cleaning": int(len(frame)),
            "quality_summary": quality,
        })

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError("Defina GOOGLE_API_KEY no ambiente antes de executar a PoC.")

        logger.info("Inicializando modelo %s com tool calling.", args.model)
        llm = ChatGoogleGenerativeAI(model=args.model, google_api_key=api_key)
        graph = build_agent(llm, DB_PATH, OUTPUT_DIR, audit)
        audit.append("orchestration_started", {"graph": "LangGraph", "tool_calling": True, "max_tool_calls": int(os.getenv("MAX_TOOL_CALLS", "6"))})

        result = graph.invoke(
            {
                "messages": [HumanMessage(content=safe_request)],
                "user_request": safe_request,
                "blocked": False,
                "tool_call_count": 0,
                "tool_results": {},
                "tool_events": [],
                "llm_events": [],
            },
            config={"recursion_limit": 30},
        )

        if result.get("blocked"):
            audit.append("run_blocked", {"reason": result.get("block_reason")})
            print(result.get("messages", [])[-1].content if result.get("messages") else "Solicitação bloqueada.")
            return 2

        validation = result.get("validation_result", {"ok": False, "problemas": ["Validação não executada."]})
        if not validation.get("ok"):
            audit.append("run_failed_validation", {"validation": validation})
            raise RuntimeError("Output Validator reprovou o relatório: " + "; ".join(validation.get("problemas", [])))

        final_report = result.get("final_report", "")
        if not final_report.strip():
            raise RuntimeError("O agente não produziu relatório final.")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(final_report, encoding="utf-8")
        audit.append("run_succeeded", {
            "report_path": str(REPORT_PATH),
            "report_sha256": sha256_text(final_report),
            "validation": validation,
            "tool_call_count": result.get("tool_call_count"),
        })
        print(final_report)
        print(f"\nRelatório: {REPORT_PATH}\nAuditoria JSONL: {AUDIT_PATH}\nQualidade: {Path(os.getenv('SRAG_QUALITY_PATH', OUTPUT_DIR / 'qualidade_dados.json'))}")
        return 0

    except Exception as exc:
        logger.exception("Falha na execução %s", run_id)
        audit.append("run_failed", {"error_type": type(exc).__name__, "error_message": str(exc)[:1000]})
        print(f"Falha: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
