"""Testes da normalização determinística do relatório."""

from srag_poc.agent import normalize_report


def _report_with_quality_section(body: str = "A completude é descrita pelos indicadores.") -> str:
    return (
        "# Relatório Epidemiológico de SRAG\n"
        "## Indicadores epidemiológicos\n"
        "### Qualidade e completude dos dados\n"
        f"{body}\n"
    )


def _tools_with_duplicate_count(count: int) -> dict:
    return {
        "consultar_metricas": {
            "qualidade_e_completude": {
                "duplicidades_exatas_na_base_minimizada": count,
            },
        },
        "gerar_graficos": {"status": "error"},
    }


def test_normalize_report_adds_exact_duplicate_count_and_caveat():
    report = _report_with_quality_section()

    normalized = normalize_report(report, _tools_with_duplicate_count(7))

    assert "**Duplicidades exatas na base minimizada:** 7." in normalized
    assert "não comprova duplicações reais de pacientes ou notificações" in normalized
    assert "não foram removidos automaticamente" in normalized


def test_normalize_report_does_not_duplicate_already_correct_duplicate_note():
    report = _report_with_quality_section(
        "Foram encontradas 7 duplicidades exatas na base minimizada. "
        "Isso não comprova duplicações reais de pacientes/notificações; não foram removidas."
    )

    normalized = normalize_report(report, _tools_with_duplicate_count(7))

    assert normalized.count("duplicidades exatas") == 1
    assert "**Duplicidades exatas na base minimizada:** 7." not in normalized


def test_normalize_report_replaces_missing_count_but_preserves_existing_caveat():
    report = _report_with_quality_section(
        "Duplicidades exatas foram verificadas apenas nas colunas minimizadas; "
        "não comprovam duplicações reais de pacientes/notificações."
    )

    normalized = normalize_report(report, _tools_with_duplicate_count(0))

    assert "**Duplicidades exatas na base minimizada:** 0." in normalized
    assert normalized.count("não comprovam duplicações reais") == 1


def test_normalize_report_is_idempotent_for_duplicate_note():
    tools = _tools_with_duplicate_count(7)
    once = normalize_report(_report_with_quality_section(), tools)
    twice = normalize_report(once, tools)

    assert twice.count("**Duplicidades exatas na base minimizada:** 7.") == 1
    assert twice.count("não comprova duplicações reais de pacientes ou notificações") == 1


# Cobertura adicional da normalização metodológica de EVOLUCAO=3.
def test_normalize_report_explains_evolucao3_and_its_role_in_numerator():
    normalized = normalize_report(_report_with_quality_section(), _tools_with_duplicate_count(7))

    assert "EVOLUCAO=3 significa óbito por outras causas" in normalized
    assert "EVOLUCAO=2 e EVOLUCAO=3 compõem o numerador" in normalized
    assert "denominador inclui os desfechos conhecidos" in normalized
    assert "EVOLUCAO=1, EVOLUCAO=2 ou EVOLUCAO=3" in normalized
    assert "não deve ser interpretado como óbito atribuído à SRAG" in normalized


def test_normalize_report_adds_treatment_even_if_definition_already_exists():
    report = _report_with_quality_section("EVOLUCAO=3 significa óbito por outras causas.")

    normalized = normalize_report(report, _tools_with_duplicate_count(7))

    assert "EVOLUCAO=2 e EVOLUCAO=3 compõem o numerador" in normalized
    assert normalized.count("**Tratamento de EVOLUCAO=3:**") == 1


def test_normalize_report_does_not_duplicate_complete_evolucao3_explanation():
    report = _report_with_quality_section(
        "**Tratamento de EVOLUCAO=3:** `EVOLUCAO=3` significa óbito por outras causas. "
        "Na métrica de mortalidade por qualquer causa entre desfechos conhecidos, "
        "EVOLUCAO=2 e EVOLUCAO=3 compõem o numerador; o denominador inclui os desfechos "
        "conhecidos (EVOLUCAO=1, 2 ou 3). O grupo EVOLUCAO=2 é apresentado separadamente. "
        "EVOLUCAO=3 não deve ser interpretado como óbito atribuído à SRAG."
    )

    normalized = normalize_report(report, _tools_with_duplicate_count(7))

    assert normalized.count("**Tratamento de EVOLUCAO=3:**") == 1


def test_normalize_report_is_idempotent_for_evolucao3_explanation():
    tools = _tools_with_duplicate_count(7)
    once = normalize_report(_report_with_quality_section(), tools)
    twice = normalize_report(once, tools)

    assert twice.count("**Tratamento de EVOLUCAO=3:**") == 1
    assert twice.count("EVOLUCAO=2 e EVOLUCAO=3 compõem o numerador") == 1
