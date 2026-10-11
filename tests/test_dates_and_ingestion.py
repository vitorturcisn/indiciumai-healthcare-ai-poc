from pathlib import Path
import sqlite3

import pandas as pd

from srag_poc.dates import parse_brazilian_dates
from srag_poc.ingestion import load_and_clean_csvs, write_database


def test_parse_brazilian_and_iso_dates_are_unambiguous():
    values = pd.Series(["01/02/2026", "2026-02-01", "31/12/2025", "inválida"])
    parsed = parse_brazilian_dates(values)
    assert parsed.iloc[0] == pd.Timestamp("2026-02-01")
    assert parsed.iloc[1] == pd.Timestamp("2026-02-01")
    assert parsed.iloc[2] == pd.Timestamp("2025-12-31")
    assert pd.isna(parsed.iloc[3])


def _csv(path: Path) -> Path:
    data = pd.DataFrame([
        {"DT_NOTIFIC": "10/03/2026", "DT_SIN_PRI": "05/03/2026", "UTI": "1", "EVOLUCAO": "2", "VACINA_COV": "1", "NU_IDADE_N": "72", "CS_SEXO": "F"},
        {"DT_NOTIFIC": "11/03/2026", "DT_SIN_PRI": "06/03/2026", "UTI": "2", "EVOLUCAO": "3", "VACINA_COV": "2", "NU_IDADE_N": "81", "CS_SEXO": "M"},
        {"DT_NOTIFIC": "12/03/2026", "DT_SIN_PRI": "13/03/2026", "UTI": "7", "EVOLUCAO": "14", "VACINA_COV": "5", "NU_IDADE_N": "45", "CS_SEXO": "F"},
        {"DT_NOTIFIC": "data ruim", "DT_SIN_PRI": "07/03/2026", "UTI": "1", "EVOLUCAO": "1", "VACINA_COV": "1", "NU_IDADE_N": "24", "CS_SEXO": "F"},
    ])
    data.to_csv(path, sep=";", index=False)
    return path


def test_minimization_domain_rules_and_date_fallback(tmp_path):
    csv_path = _csv(tmp_path / "sample.csv")
    cleaned, quality = load_and_clean_csvs([csv_path])

    assert len(cleaned) == 3  # linha sem DT_NOTIFIC válida excluída
    assert "NU_IDADE_N" not in cleaned.columns
    assert "CS_SEXO" not in cleaned.columns
    assert "DATA_REFERENCIA" in cleaned.columns
    # A data de sintomas posterior à notificação é descartada e usa-se DT_NOTIFIC.
    row = cleaned.loc[cleaned["UTI"].isna()].iloc[0]
    assert row["DATA_REFERENCIA"] == row["DT_NOTIFIC"]
    assert pd.isna(row["EVOLUCAO"])
    assert pd.isna(row["VACINA_COV"])
    assert quality["registros_excluidos_por_data_notificacao_invalida"] == 1
    assert quality["datas_sintomas_posteriores_a_notificacao_descartadas"] == 1
    assert quality["variaveis"]["EVOLUCAO"]["codigo_9_desconhecido"] == 0
    assert quality["variaveis"]["EVOLUCAO"]["valores_fora_do_dominio_convertidos_em_nulo"] == 1


def test_sqlite_contains_only_minimized_analytic_columns(tmp_path, monkeypatch):
    csv_path = _csv(tmp_path / "sample.csv")
    cleaned, quality = load_and_clean_csvs([csv_path])
    db = tmp_path / "test.db"
    write_database(cleaned, db, quality)
    with sqlite3.connect(db) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(casos_srag)")}
    assert columns == {
        "DT_NOTIFIC", "DT_SIN_PRI", "UTI", "EVOLUCAO", "VACINA_COV",
        "DATA_REFERENCIA", "ORIGEM_DATA_REFERENCIA", "ATRASO_NOTIFICACAO_DIAS",
    }
    assert not ({"NU_IDADE_N", "CS_SEXO"} & columns)
