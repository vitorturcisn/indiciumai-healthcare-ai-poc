"""Ingestão, limpeza de domínios e minimização do SIVEP-Gripe."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .config import DATA_QUALITY_PATH, SOURCE_DATASET_URL
from .dates import parse_brazilian_dates

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("DT_NOTIFIC", "UTI", "EVOLUCAO", "VACINA_COV")
OPTIONAL_DATE_COLUMNS = ("DT_SIN_PRI",)
MINIMIZED_COLUMNS = ("DT_NOTIFIC", "DT_SIN_PRI", "UTI", "EVOLUCAO", "VACINA_COV")

# Os domínios vêm do dicionário do SIVEP-Gripe. 9 significa ignorado/desconhecido.
VALID_CODES: dict[str, set[int]] = {
    "UTI": {1, 2, 9},
    "EVOLUCAO": {1, 2, 3, 9},
    "VACINA_COV": {1, 2, 9},
}
UNKNOWN_CODE = 9


def read_csv_robust(path: Path) -> pd.DataFrame:
    """Lê CSV DATASUS (separador ';') com os encodings comuns."""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(path, sep=";", low_memory=False, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Não foi possível decodificar o CSV: {path}") from last_error


def _normalize_code_column(series: pd.Series, valid_codes: set[int]) -> tuple[pd.Series, dict[str, int]]:
    """Normaliza códigos numéricos e converte códigos fora do domínio em NA."""
    raw = series.copy()
    numeric = pd.to_numeric(raw, errors="coerce")
    malformed = int((raw.notna() & numeric.isna()).sum())
    non_integer = numeric.notna() & (numeric % 1 != 0)
    out_of_domain = numeric.notna() & (~numeric.isin(valid_codes) | non_integer)
    unknown = int((numeric == UNKNOWN_CODE).sum())
    valid_or_unknown = numeric.isin(valid_codes) & ~non_integer
    clean = numeric.where(valid_or_unknown, pd.NA).astype("Int64")
    quality = {
        "codigo_9_desconhecido": unknown,
        "valores_fora_do_dominio_convertidos_em_nulo": int(out_of_domain.sum()) + malformed,
        "valores_malformados_nao_numericos": malformed,
    }
    return clean, quality


def load_and_clean_csvs(paths: Iterable[Path]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Lê múltiplos CSVs e mantém apenas as colunas necessárias à PoC.

    DT_SIN_PRI é usada como data epidemiológica de referência quando válida.
    Se ausente/inválida ou posterior à notificação, usa DT_NOTIFIC como fallback.
    Os dados individuais nunca são enviados ao LLM.
    """
    frames: list[pd.DataFrame] = []
    source_files: list[str] = []
    for path in paths:
        frame = read_csv_robust(Path(path))
        missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
        if missing:
            raise KeyError(f"{Path(path).name}: colunas obrigatórias ausentes: {missing}")
        # DT_SIN_PRI é opcional para manter compatibilidade com snapshots antigos.
        selected = [column for column in MINIMIZED_COLUMNS if column in frame.columns]
        subset = frame[selected].copy()
        if "DT_SIN_PRI" not in subset:
            subset["DT_SIN_PRI"] = pd.NA
        frames.append(subset[list(MINIMIZED_COLUMNS)])
        source_files.append(Path(path).name)

    if not frames:
        raise ValueError("Informe ao menos um CSV de entrada.")

    raw = pd.concat(frames, ignore_index=True)
    rows_raw = len(raw)
    quality: dict[str, Any] = {
        "fonte": SOURCE_DATASET_URL,
        "arquivos": source_files,
        "total_registros_brutos": int(rows_raw),
        "variaveis": {},
    }

    raw["DT_NOTIFIC"] = parse_brazilian_dates(raw["DT_NOTIFIC"])
    raw["DT_SIN_PRI"] = parse_brazilian_dates(raw["DT_SIN_PRI"])

    invalid_notification = int(raw["DT_NOTIFIC"].isna().sum())

    # Auditar domínios em todas as linhas recebidas, inclusive as que depois
    # serão excluídas por data inválida; assim o relatório não esconde problemas.
    for column, valid_codes in VALID_CODES.items():
        clean, code_quality = _normalize_code_column(raw[column], valid_codes)
        raw[column] = clean
        code_quality.update({
            "nulos_apos_normalizacao_na_fonte": int(raw[column].isna().sum()),
            "codigos_validos_conhecidos_na_fonte": int(raw[column].isin(valid_codes - {UNKNOWN_CODE}).sum()),
        })
        quality["variaveis"][column] = code_quality

    raw = raw.dropna(subset=["DT_NOTIFIC"]).copy()
    raw["DT_SIN_PRI_ORIGINAL"] = raw["DT_SIN_PRI"]

    symptom_after_notification = (
        raw["DT_SIN_PRI"].notna() & (raw["DT_SIN_PRI"] > raw["DT_NOTIFIC"])
    )
    symptom_inconsistent_count = int(symptom_after_notification.sum())
    raw.loc[symptom_after_notification, "DT_SIN_PRI"] = pd.NaT

    use_symptom_date = raw["DT_SIN_PRI"].notna()
    raw["DATA_REFERENCIA"] = raw["DT_SIN_PRI"].where(use_symptom_date, raw["DT_NOTIFIC"])
    raw["ORIGEM_DATA_REFERENCIA"] = use_symptom_date.map({True: "DT_SIN_PRI", False: "DT_NOTIFIC"})
    raw["ATRASO_NOTIFICACAO_DIAS"] = (raw["DT_NOTIFIC"] - raw["DT_SIN_PRI"]).dt.days.where(use_symptom_date)

    # Remover coluna auxiliar sem reter informação desnecessária.
    raw = raw.drop(columns=["DT_SIN_PRI_ORIGINAL"])
    for column in ("DT_NOTIFIC", "DT_SIN_PRI", "DATA_REFERENCIA"):
        raw[column] = raw[column].dt.strftime("%Y-%m-%d")

    quality.update({
        "total_registros_com_data_notificacao_valida": int(len(raw)),
        "registros_excluidos_por_data_notificacao_invalida": invalid_notification,
        "datas_sintomas_posteriores_a_notificacao_descartadas": symptom_inconsistent_count,
        "registros_com_data_referencia_sintomas": int((raw["ORIGEM_DATA_REFERENCIA"] == "DT_SIN_PRI").sum()),
        "registros_com_fallback_para_notificacao": int((raw["ORIGEM_DATA_REFERENCIA"] == "DT_NOTIFIC").sum()),
        "percentual_com_data_referencia_sintomas": round(
            100 * (raw["ORIGEM_DATA_REFERENCIA"] == "DT_SIN_PRI").mean(), 2
        ) if len(raw) else None,
        "duplicidades_exatas_na_base_minimizada": int(raw.duplicated().sum()),
        "data_inicio_referencia": raw["DATA_REFERENCIA"].min() if len(raw) else None,
        "data_fim_referencia": raw["DATA_REFERENCIA"].max() if len(raw) else None,
        "data_inicio_notificacao": raw["DT_NOTIFIC"].min() if len(raw) else None,
        "data_fim_notificacao": raw["DT_NOTIFIC"].max() if len(raw) else None,
        "definicao_data_referencia": "DT_SIN_PRI quando válida; caso contrário, DT_NOTIFIC.",
    })
    return raw, quality


def write_database(df: pd.DataFrame, db_path: Path, quality: dict[str, Any]) -> None:
    """Persiste somente a base minimizada, qualidade e metadados."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        df.to_sql("casos_srag", connection, if_exists="replace", index=False)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_casos_data_ref ON casos_srag(DATA_REFERENCIA)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_casos_dt_notific ON casos_srag(DT_NOTIFIC)")
        pd.DataFrame([
            {"variavel": column, **values}
            for column, values in quality["variaveis"].items()
        ]).to_sql("qualidade_dados", connection, if_exists="replace", index=False)
        meta = {
            "fonte": SOURCE_DATASET_URL,
            "arquivos": ",".join(quality.get("arquivos", [])),
            "total_registros_brutos": quality.get("total_registros_brutos"),
            "total_registros_validos": len(df),
            "data_inicio_referencia": quality.get("data_inicio_referencia"),
            "data_fim_referencia": quality.get("data_fim_referencia"),
        }
        pd.DataFrame([meta]).to_sql("metadata", connection, if_exists="replace", index=False)
    DATA_QUALITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_QUALITY_PATH.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Persistidos %s registros minimizados em %s", len(df), db_path)
