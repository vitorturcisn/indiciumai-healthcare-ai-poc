"""Guardrails de entrada e verificação de proveniência da saída."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from .config import SOURCE_DATASET_URL
from .news import allowed_url

BLOCKED_INPUT_PATTERNS = (
    r"\bcpf\b", r"\bnome completo\b", r"\bendereço residencial\b",
    r"\bdados individuais\b", r"\bregistro individual\b",
    r"\bprontuário\b", r"\bidentifique (?:o|a|um|uma) paciente\b",
    r"\bexiba (?:todos os )?registros\b", r"\bdados pessoais de pacientes\b",
)
INJECTION_PATTERNS = (
    r"ignore (?:todas as )?as instruções anteriores",
    r"ignore previous instructions", r"revele (?:o )?prompt do sistema",
    r"ignore o guardrail", r"exiba a base completa", r"select\s+\*\s+from",
)
REQUIRED_REPORT_ELEMENTS = (
    "Relatório Epidemiológico de SRAG",
    "Período analisado",
    "Indicadores epidemiológicos",
    "Taxa de aumento de casos",
    "Proporção de óbitos entre casos com desfecho conhecido",
    "Taxa de internação em UTI entre casos SRAG",
    "Proporção de casos com vacina registrada",
    "Qualidade e completude dos dados",
    "Gráficos",
    "Metodologia e limitações",
    "Contexto externo / notícias",
    "Fontes consultadas",
)
PERCENT_RE = re.compile(r"(?<![\w/])(-?\d+(?:[.,]\d+)?)\s*%")
URL_RE = re.compile(r"https?://[^\s<>\]\)\"']+", re.IGNORECASE)


def validate_user_request(request: str) -> str:
    normalized = " ".join(str(request or "").strip().split())
    if not normalized:
        raise ValueError("A solicitação não pode estar vazia.")
    if len(normalized) > 2000:
        raise ValueError("A solicitação excede o limite de 2.000 caracteres.")
    for pattern in BLOCKED_INPUT_PATTERNS + INJECTION_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            raise ValueError("Solicitação bloqueada pelo guardrail: consultas individualizadas, exposição de dados pessoais ou tentativa de sobrescrever instruções não são permitidas.")
    return normalized


def _pct_token(value: str) -> str:
    try:
        number = float(value.replace(",", "."))
        return f"{number:.2f}"
    except ValueError:
        return value


def _allowed_percentages(tool_results: dict[str, Any]) -> set[str]:
    serialized = json.dumps(tool_results, ensure_ascii=False, default=str)
    return {_pct_token(match.group(1)) for match in PERCENT_RE.finditer(serialized)}


def _number_aliases(token: str) -> set[str]:
    """Retorna representações equivalentes para contagens formatadas em pt/en."""
    token = token.strip()
    aliases: set[str] = set()
    try:
        aliases.add(f"{float(token.replace(',', '.')):.6f}".rstrip("0").rstrip("."))
    except ValueError:
        pass
    # Separadores de milhar em relatórios brasileiros e anglófonos.
    for normalized in (token.replace(".", "").replace(",", "."), token.replace(",", "")):
        try:
            aliases.add(f"{float(normalized):.6f}".rstrip("0").rstrip("."))
        except ValueError:
            pass
    return aliases


def _collect_grounded_numbers(value: Any, key: str = "") -> set[str]:
    """Coleta valores numéricos dos resultados de tools, sem confundir datas com contagens.

    Importante: chaves como ``casos_periodo_recente`` contêm CONTAGENS e não
    devem ser descartadas apenas porque incluem a palavra ``periodo``.
    """
    grounded: set[str] = set()
    key_lower = key.lower()
    ignored_fragments = ("url", "fonte", "query", "timestamp", "sha256", "path", "arquivo")

    if isinstance(value, dict):
        for child_key, child in value.items():
            grounded.update(_collect_grounded_numbers(child, str(child_key).lower()))
    elif isinstance(value, (list, tuple)):
        for child in value:
            grounded.update(_collect_grounded_numbers(child, key_lower))
    elif isinstance(value, bool) or value is None:
        return grounded
    elif isinstance(value, (int, float)):
        # Ignorar números que são componentes de metadados/data, mas preservar
        # contagens em chaves como casos_periodo_recente.
        if not any(fragment in key_lower for fragment in ignored_fragments) and not key_lower.startswith("data_"):
            grounded.update(_number_aliases(str(value)))
    elif isinstance(value, str):
        if any(fragment in key_lower for fragment in ignored_fragments):
            return grounded
        if key_lower.startswith("data_") or "periodo" in key_lower or "timestamp" in key_lower:
            return grounded
        if "%" in value:
            return grounded
        # Não converte datas em uma coleção de números avulsos.
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b", value):
            return grounded
        for match in re.finditer(r"(?<![\w/])-?\d+(?:[.,]\d+)?", value):
            grounded.update(_number_aliases(match.group(0)))
    return grounded


def _extract_report_urls(text: str) -> set[str]:
    """Extrai URLs inclusive quando um modelo emite '\\n' literal entre bullets."""
    normalized = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    normalized = normalized.replace("\n", "\n")
    found: set[str] = set()
    for item in URL_RE.findall(normalized):
        candidate = item.strip().rstrip(".,;:")
        # Evita incluir separadores de Markdown que tenham sido anexados após
        # uma sequência de nova linha escapada.
        candidate = re.split(r"\\[nr]", candidate, maxsplit=1)[0].rstrip("- \t.,;:")
        if candidate:
            found.add(candidate)
    return found


def _extract_report_section(text: str, section: str | None) -> str:
    """Retorna o corpo de uma seção Markdown de nível 2, sem seu título."""
    normalized = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    if section is None:
        return normalized
    main_sections = list(re.finditer(r"(?m)^##\s+(?!#)(.+?)\s*$", normalized))
    wanted = section.strip().casefold()
    for index, match in enumerate(main_sections):
        if match.group(1).strip().casefold() == wanted:
            end = main_sections[index + 1].start() if index + 1 < len(main_sections) else len(normalized)
            return normalized[match.end():end]
    return ""


def _report_numeric_tokens(text: str, section: str | None = "Indicadores epidemiológicos") -> list[str]:
    """Extrai números para validação de proveniência, por contexto semântico.

    Os indicadores e a metodologia são validados contra resultados agregados;
    números no contexto externo são validados contra títulos/resumos das fontes.
    Datas, semanas epidemiológicas, códigos e referências numeradas são
    metadados e não devem ser tratados como métricas novas. Percentuais são
    verificados separadamente em todo o relatório.
    """
    cleaned = _extract_report_section(text, section)
    cleaned = URL_RE.sub(" ", cleaned)

    date_patterns = (
        r"\b\d{4}-\d{2}-\d{2}(?:[T ][^\s]*)?\b",
        r"\b\d{4}-\d{2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
        r"\b\d{1,2}[/-]\d{1,2}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{1,2}\s+de\s+(?:janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+\d{4}\b",
    )
    for pattern in date_patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\b(?:EVOLUCAO|UTI|VACINA_COV)\s*=\s*\d+(?:[.,]\d+)?", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bCOVID\s*-\s*19\b", "COVID", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bP\s*-?\s*90\b", "P", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:19|20)\d{2}\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:SE|semana epidemiológica|semana epidemiologica)\s*\d+\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"grafico_30_dias|grafico_12_meses", " ", cleaned, flags=re.IGNORECASE)
    cleaned = PERCENT_RE.sub(" ", cleaned)
    cleaned = re.sub(r"(?m)^\s*\d+[.)]\s+", " ", cleaned)
    cleaned = re.sub(r"\[\s*\d{1,4}\s*\]", " ", cleaned)
    cleaned = re.sub(r"\(\s*(?:ref\.?\s*)?\d{1,4}\s*\)", " ", cleaned, flags=re.IGNORECASE)

    return [
        token for token in re.findall(r"(?<![\w/])-?\d+(?:[.,]\d+)?", cleaned)
        if token not in {"30", "12"}
    ]


def _allowed_urls(tool_results: dict[str, Any]) -> set[str]:
    allow = {SOURCE_DATASET_URL.rstrip("/")}
    metric = tool_results.get("consultar_metricas", {})
    if isinstance(metric, dict):
        source_url = metric.get("fonte")
        if isinstance(source_url, str) and urlparse(source_url).scheme == "https":
            allow.add(source_url.rstrip("/"))
    news = tool_results.get("buscar_noticias", {})
    for result in news.get("results", []) if isinstance(news, dict) else []:
        url = result.get("url")
        if isinstance(url, str) and allowed_url(url):
            allow.add(url.rstrip("/"))
    return allow

def validate_report(text: str, tool_results: dict[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    lower = text.lower()
    for required in REQUIRED_REPORT_ELEMENTS:
        if required.lower() not in lower:
            problems.append(f"Seção/conteúdo obrigatório ausente: {required}")

    required_tools = {"consultar_metricas", "gerar_graficos", "buscar_noticias"}
    missing_tools = sorted(required_tools - set(tool_results))
    if missing_tools:
        problems.append("Ferramentas obrigatórias não executadas: " + ", ".join(missing_tools))
    metric_result = tool_results.get("consultar_metricas", {})
    chart_result = tool_results.get("gerar_graficos", {})
    if isinstance(metric_result, dict) and metric_result.get("status") in {"error", "blocked"}:
        problems.append("A ferramenta de métricas falhou; o relatório não pode apresentar os indicadores como calculados.")
    if not isinstance(chart_result, dict) or chart_result.get("status") != "success":
        problems.append("A ferramenta de gráficos não terminou com sucesso.")
    news_result = tool_results.get("buscar_noticias", {})
    if isinstance(news_result, dict) and news_result.get("status") == "error":
        if not any(phrase in lower for phrase in ("falha na busca", "busca falhou", "não foi possível realizar a busca", "nao foi possivel realizar a busca")):
            problems.append("A busca de notícias falhou, mas o relatório não informa essa limitação.")

    for graph_name in ("grafico_30_dias.png", "grafico_12_meses.png"):
        if graph_name not in text:
            problems.append(f"Referência ao gráfico obrigatório ausente: {graph_name}")

    if "VACINA_COV" not in text and "covid-19" not in lower and "covid" not in lower:
        problems.append("O relatório não identifica claramente a variável de vacinação contra COVID-19.")
    if not any(phrase in lower for phrase in ("óbito por outras causas", "obito por outras causas")):
        problems.append("O relatório não esclarece o tratamento de EVOLUCAO=3 (óbito por outras causas).")

    quality_result = metric_result.get("qualidade_e_completude", {}) if isinstance(metric_result, dict) else {}
    duplicate_count = quality_result.get("duplicidades_exatas_na_base_minimizada") if isinstance(quality_result, dict) else None
    if duplicate_count is not None:
        if "duplicidades exatas" not in lower and "duplicações exatas" not in lower and "duplicacoes exatas" not in lower:
            problems.append("O relatório deve mencionar as duplicidades exatas encontradas na base minimizada.")
        if not any(phrase in lower for phrase in ("não equivalem a duplicações confirmadas", "nao equivalem a duplicacoes confirmadas", "não comprovam duplicações", "nao comprovam duplicacoes", "não comprova duplicações", "nao comprova duplicacoes", "não provam duplicação de pacientes", "nao provam duplicacao de pacientes")):
            problems.append("O relatório deve esclarecer que duplicidades na base minimizada não comprovam duplicações reais de pacientes/notificações.")

    allowed_pct = _allowed_percentages(tool_results)
    unsupported_percentages = []
    for match in PERCENT_RE.finditer(text):
        token = _pct_token(match.group(1))
        if token not in allowed_pct:
            unsupported_percentages.append(match.group(0))
    if unsupported_percentages:
        problems.append("Percentuais não encontrados nos resultados das ferramentas: " + ", ".join(sorted(set(unsupported_percentages))))

    grounded_numbers = _collect_grounded_numbers(tool_results)
    unsupported_numbers: list[str] = []

    # Métricas, período, gráficos e metodologia devem usar números dos
    # resultados analíticos. Isso evita confundir os números de notícias e
    # citações com os valores calculados pela base.
    for section in ("Período analisado", "Indicadores epidemiológicos", "Gráficos", "Metodologia e limitações"):
        for token in _report_numeric_tokens(text, section=section):
            if not (_number_aliases(token) & grounded_numbers):
                unsupported_numbers.append(token)

    # No contexto externo, qualquer número apresentado como fato precisa
    # estar presente em um título/resumo retornado pela ferramenta de notícias.
    grounded_news_numbers = _collect_grounded_numbers({"news": news_result})
    for token in _report_numeric_tokens(text, section="Contexto externo / notícias"):
        if not (_number_aliases(token) & grounded_news_numbers):
            unsupported_numbers.append(token)

    if unsupported_numbers:
        problems.append("Números sem proveniência nos resultados das ferramentas: " + ", ".join(sorted(set(unsupported_numbers))))

    allowed_urls = _allowed_urls(tool_results)
    used_urls = _extract_report_urls(text)
    unknown_urls = sorted(url for url in used_urls if url.rstrip("/") not in allowed_urls)
    if unknown_urls:
        problems.append("URLs sem proveniência nas ferramentas: " + ", ".join(unknown_urls))

    return {
        "ok": not problems,
        "problemas": problems,
        "percentuais_encontrados": [m.group(0) for m in PERCENT_RE.finditer(text)],
        "urls_encontradas": sorted(used_urls),
        "urls_sem_proveniencia": unknown_urls,
        "hash_relatorio_sha256": __import__("hashlib").sha256(text.encode("utf-8")).hexdigest(),
    }
