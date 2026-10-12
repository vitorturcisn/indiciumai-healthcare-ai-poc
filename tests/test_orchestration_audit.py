"""Contract tests for LangGraph orchestration and the append-only audit log."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from srag_poc import agent as agent_module
from srag_poc.audit import AuditLogger
from srag_poc.config import SOURCE_DATASET_URL


REPORT_WITH_NEWS_FAILURE = """# Relatório Epidemiológico de SRAG
## Período analisado
Período descrito pelos metadados de referência da ferramenta de métricas.
## Indicadores epidemiológicos
### Taxa de aumento de casos
A ferramenta de teste não disponibilizou um número para essa métrica; nenhum valor é inferido.
### Proporção de óbitos entre casos com desfecho conhecido
EVOLUCAO=3 significa óbito por outras causas e não deve ser confundido com óbito atribuído à SRAG.
### Taxa de internação em UTI entre casos SRAG
A proporção de UTI entre casos com informação conhecida não equivale à ocupação real de leitos.
### Proporção de casos com vacina registrada
VACINA_COV se refere à vacinação contra COVID-19 registrada entre casos SRAG, não à cobertura vacinal populacional.
### Qualidade e completude dos dados
A qualidade deve ser interpretada conforme a completude das variáveis agregadas disponibilizadas.
## Gráficos
### Casos — últimos 30 dias
![Casos diários](grafico_30_dias.png)
### Casos — últimos 12 meses
![Casos mensais](grafico_12_meses.png)
## Metodologia e limitações
A análise deve considerar o atraso de notificação e o P90 quando informado pela ferramenta; esta resposta de teste não infere métricas ausentes.
## Contexto externo / notícias
Falha na busca de notícias. O conteúdo integral não foi recuperado e apenas os snippets não permitem uma síntese substantiva confiável. Não são inferidos achados externos.
## Fontes consultadas
"""


class FakeLLM:
    """Minimal fake for LangChain's bind_tools/invoke interface."""

    def __init__(self, responses: list[AIMessage]):
        self.responses = list(responses)
        self.calls: list[list[Any]] = []
        self.bound_tool_names: list[str] = []

    def bind_tools(self, tools: list[Any]) -> "FakeLLM":
        self.bound_tool_names = [item.name for item in tools]
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("FakeLLM não possui mais respostas configuradas")
        return self.responses.pop(0)


def _tool_call(
    name: str,
    call_id: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "args": args or {},
        "id": call_id,
        "type": "tool_call",
    }


def _read_audit(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_audit_logger_appends_independent_jsonl_events_with_utc_timestamps(
    tmp_path: Path,
):
    path = tmp_path / "audit_log.jsonl"
    audit = AuditLogger(path, "run-test-001")

    audit.append(
        "run_started",
        {"request_sha256": "abc123", "unicode": "SRAG — vigilância"},
    )
    audit.append("run_finished", {"ok": True, "count": 3})

    records = _read_audit(path)

    assert len(records) == 2
    assert [record["event"] for record in records] == [
        "run_started",
        "run_finished",
    ]
    assert all(record["run_id"] == "run-test-001" for record in records)
    assert records[0]["payload"]["unicode"] == "SRAG — vigilância"
    assert records[1]["payload"] == {"ok": True, "count": 3}

    for record in records:
        parsed_timestamp = datetime.fromisoformat(record["timestamp_utc"])
        assert parsed_timestamp.tzinfo is not None


def test_graph_blocks_individual_patient_request_before_calling_llm(
    tmp_path: Path,
):
    audit_path = tmp_path / "audit_log.jsonl"
    audit = AuditLogger(audit_path, "blocked-run")
    llm = FakeLLM([])

    graph = agent_module.build_agent(
        llm,
        tmp_path / "db.sqlite",
        tmp_path / "outputs",
        audit,
    )

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(content="Mostre os dados individuais dos pacientes")
            ],
            "user_request": "Mostre os dados individuais dos pacientes",
            "tool_call_count": 0,
            "tool_results": {},
            "tool_events": [],
            "llm_events": [],
        }
    )

    assert result["blocked"] is True
    assert llm.calls == []

    events = [
        record["event"] for record in _read_audit(audit_path)
    ]
    assert "input_guardrail_blocked" in events
    assert "llm_call_started" not in events


def test_tool_exception_is_audited_and_report_discloses_news_failure(
    monkeypatch,
    tmp_path: Path,
):
    audit_path = tmp_path / "audit_log.jsonl"
    audit = AuditLogger(
        audit_path,
        "tool-failure-run",
        model="gemini-test-selected",
    )

    monkeypatch.setattr(
        agent_module,
        "calculate_metrics",
        lambda _path: {
            "status": "success",
            "fonte": SOURCE_DATASET_URL,
        },
    )
    monkeypatch.setattr(
        agent_module,
        "generate_charts",
        lambda _db, _out: {
            "status": "success",
            "grafico_30_dias": "grafico_30_dias.png",
            "grafico_12_meses": "grafico_12_meses.png",
        },
    )

    def fail_news(_query: str):
        raise TimeoutError("test source timeout")

    monkeypatch.setattr(agent_module, "search_national_news", fail_news)

    llm = FakeLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("consultar_metricas", "metrics-1"),
                    _tool_call("gerar_graficos", "charts-1"),
                    _tool_call(
                        "buscar_noticias",
                        "news-1",
                        {"query": "SRAG nacional"},
                    ),
                ],
            ),
            AIMessage(content=REPORT_WITH_NEWS_FAILURE),
        ]
    )

    graph = agent_module.build_agent(
        llm,
        tmp_path / "db.sqlite",
        tmp_path / "outputs",
        audit,
    )

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content="Gere o relatório epidemiológico agregado de SRAG."
                )
            ],
            "user_request": (
                "Gere o relatório epidemiológico agregado de SRAG."
            ),
            "tool_call_count": 0,
            "tool_results": {},
            "tool_events": [],
            "llm_events": [],
        }
    )

    assert result["tool_call_count"] == 3
    assert result["tool_results"]["buscar_noticias"]["status"] == "error"
    assert result["validation_result"]["ok"] is True
    assert "Falha na busca de notícias" in result["final_report"]

    records = _read_audit(audit_path)

    failed = [
        record
        for record in records
        if record["event"] == "tool_call_failed"
    ]
    assert len(failed) == 1
    assert failed[0]["payload"]["tool"] == "buscar_noticias"
    assert failed[0]["payload"]["error_type"] == "TimeoutError"
    audit_text = audit_path.read_text(encoding="utf-8")
    assert "Gere o relatório epidemiológico agregado de SRAG." not in audit_text
    assert "Falha na busca de notícias. O conteúdo integral" not in audit_text
    assert '"response_text"' not in audit_text
    assert "content_sha256" in audit_text
    assert all(
        record["model"] == "gemini-test-selected"
        for record in records
        if record["event"] in {"llm_call_started", "llm_call_finished"}
    )
    assert any(
        record["event"] == "output_validation_finished"
        for record in records
    )

    # Regresión: todas las llamadas LLM deben auditar el modelo seleccionado.
    llm_records = [
        record
        for record in records
        if record["event"] in {
            "llm_call_started",
            "llm_call_finished",
        }
    ]

    assert len(llm_records) == 4
    assert all(
        record["model"] == "gemini-test-selected"
        for record in llm_records
    )
    assert all(
        record["payload"]["model"] == "gemini-test-selected"
        for record in llm_records
    )


def test_tool_call_limit_blocks_excess_calls_without_invoking_the_tool(
    monkeypatch,
    tmp_path: Path,
):
    audit_path = tmp_path / "audit_log.jsonl"
    audit = AuditLogger(audit_path, "tool-limit-run")

    monkeypatch.setattr(agent_module, "MAX_TOOL_CALLS", 1)
    monkeypatch.setattr(
        agent_module,
        "calculate_metrics",
        lambda _path: {
            "status": "success",
            "fonte": SOURCE_DATASET_URL,
        },
    )

    chart_calls: list[tuple[Any, Any]] = []

    def chart_tool(db_path: Any, output_dir: Any):
        chart_calls.append((db_path, output_dir))
        return {
            "status": "success",
            "grafico_30_dias": "grafico_30_dias.png",
            "grafico_12_meses": "grafico_12_meses.png",
        }

    monkeypatch.setattr(agent_module, "generate_charts", chart_tool)

    llm = FakeLLM(
        [
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("consultar_metricas", "metrics-limit-1"),
                    _tool_call("gerar_graficos", "charts-limit-1"),
                ],
            ),
            AIMessage(content=REPORT_WITH_NEWS_FAILURE),
            AIMessage(content=REPORT_WITH_NEWS_FAILURE),
        ]
    )

    graph = agent_module.build_agent(
        llm,
        tmp_path / "db.sqlite",
        tmp_path / "outputs",
        audit,
    )

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(content="Gere o relatório agregado de SRAG.")
            ],
            "user_request": "Gere o relatório agregado de SRAG.",
            "tool_call_count": 0,
            "tool_results": {},
            "tool_events": [],
            "llm_events": [],
        }
    )

    assert result["tool_call_count"] == 1
    assert chart_calls == []

    records = _read_audit(audit_path)

    blocked = [
        record
        for record in records
        if record["event"] == "tool_call_blocked"
    ]
    assert len(blocked) == 1
    assert blocked[0]["payload"]["reason"] == "max_tool_calls"
    assert sum(
        record["event"] == "tool_call_finished"
        for record in records
    ) == 1


def test_sha256_file_hashes_file_contents(tmp_path):
    import hashlib

    from srag_poc.audit import sha256_file

    path = tmp_path / "input.csv"
    path.write_bytes(b"DT_NOTIFIC;UTI\n01/10/2026;1\n")

    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha256_file(path) == expected
