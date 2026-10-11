import pandas as pd

from srag_poc.ingestion import load_and_clean_csvs, write_database
from srag_poc.metrics import calculate_metrics


def test_evolucao_3_is_in_all_cause_mortality_and_vaccine_is_covid(tmp_path):
    rows = []
    # Cria 90 dias para permitir janelas de tendência; 1 cura, 1 óbito, 1 óbito por outras causas.
    for day in range(1, 91):
        day_str = pd.Timestamp("2026-01-01") + pd.Timedelta(days=day - 1)
        evolucao = {1: "1", 2: "2", 3: "3"}.get(day, "1")
        rows.append({
            "DT_NOTIFIC": day_str.strftime("%d/%m/%Y"),
            "DT_SIN_PRI": (day_str - pd.Timedelta(days=5)).strftime("%d/%m/%Y"),
            "UTI": "1" if day % 2 else "2",
            "EVOLUCAO": evolucao,
            "VACINA_COV": "1" if day % 3 else "2",
        })
    csv_path = tmp_path / "sample.csv"
    pd.DataFrame(rows).to_csv(csv_path, sep=";", index=False)
    cleaned, quality = load_and_clean_csvs([csv_path])
    db_path = tmp_path / "sample.db"
    write_database(cleaned, db_path, quality)

    metrics = calculate_metrics(db_path)
    mortality = metrics["mortalidade_qualquer_causa_desfechos_conhecidos"]
    assert mortality["obitos_evolucao_2"] == 1
    assert mortality["obitos_evolucao_3_outras_causas"] == 1
    assert mortality["obitos_total"] == 2
    assert mortality["desfechos_conhecidos"] == 90
    assert "COVID-19" in metrics["proporcao_casos_com_vacina_covid_registrada"]["regra"]
    assert metrics["taxa_aumento_casos"]["atraso_notificacao"]["p90_atraso_dias"] >= 0


def test_metrics_expose_duplicates_only_after_minimization(tmp_path):
    rows = [
        {
            "DT_NOTIFIC": "15/01/2026",
            "DT_SIN_PRI": "10/01/2026",
            "UTI": "1",
            "EVOLUCAO": "1",
            "VACINA_COV": "2",
        },
        {
            "DT_NOTIFIC": "15/01/2026",
            "DT_SIN_PRI": "10/01/2026",
            "UTI": "1",
            "EVOLUCAO": "1",
            "VACINA_COV": "2",
        },
    ]
    csv_path = tmp_path / "duplicates.csv"
    pd.DataFrame(rows).to_csv(csv_path, sep=";", index=False)
    cleaned, quality = load_and_clean_csvs([csv_path])
    db_path = tmp_path / "duplicates.db"
    write_database(cleaned, db_path, quality)

    metrics = calculate_metrics(db_path)
    quality_metrics = metrics["qualidade_e_completude"]
    assert quality_metrics["duplicidades_exatas_na_base_minimizada"] == 1
    assert "não equivalem" in quality_metrics["interpretacao_duplicidades"]
