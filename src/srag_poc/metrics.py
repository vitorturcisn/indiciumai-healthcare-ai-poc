"""Indicadores reproduzíveis, com denominadores e limites explícitos."""

from __future__ import annotations

import math
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .config import SOURCE_DATASET_URL


def _pct(numerator: int, denominator: int) -> float | None:
    return round(100.0 * numerator / denominator, 2) if denominator else None


def _fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}%"


def _read_cases(db_path: Path) -> pd.DataFrame:
    with sqlite3.connect(db_path) as connection:
        frame = pd.read_sql_query("SELECT * FROM casos_srag", connection)

    for column in ("DATA_REFERENCIA", "DT_NOTIFIC", "DT_SIN_PRI"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")

    for column in ("UTI", "EVOLUCAO", "VACINA_COV"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    return frame


def reporting_delay_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Calcula atraso de notificação e ponto de corte conservador para a tendência.

    O P90 é estimado nas notificações dos últimos 180 dias com datas de sintomas
    e notificação válidas e atraso não negativo. Se a amostra for pequena, nenhum
    atraso é presumido: a tendência é reportada como N/A até existir evidência suficiente.
    """
    valid = df.dropna(subset=["DT_NOTIFIC", "DT_SIN_PRI"]).copy()
    valid["atraso_dias"] = (
        valid["DT_NOTIFIC"] - valid["DT_SIN_PRI"]
    ).dt.days
    valid = valid[valid["atraso_dias"].between(0, 365)]

    max_notification = df["DT_NOTIFIC"].max()

    if pd.notna(max_notification):
        recent_threshold = max_notification - pd.Timedelta(180, unit="D")
        recent = valid[valid["DT_NOTIFIC"] >= recent_threshold]
    else:
        recent = valid.iloc[0:0]

    if len(recent) >= 30:
        p90 = int(math.ceil(float(recent["atraso_dias"].quantile(0.90))))
        method = "percentil 90 dos atrasos nos últimos 180 dias (n >= 30)"
    else:
        # Não inventar um atraso de referência quando a amostra é insuficiente.
        p90 = None
        method = "não estimado: menos de 30 atrasos válidos recentes"

    data_max_ref = df["DATA_REFERENCIA"].max()

    cutoff = (
        data_max_ref - pd.Timedelta(p90, unit="D")
        if pd.notna(data_max_ref) and p90 is not None
        else pd.NaT
    )

    return {
        "p90_atraso_dias": p90,
        "metodo_estimativa": method,
        "amostra_atrasos_validos_recentes": int(len(recent)),
        "data_corte_tendencia": (
            cutoff.strftime("%Y-%m-%d") if pd.notna(cutoff) else None
        ),
        "observacao": (
            "A série mais recente pode estar subnotificada. Quando há pelo menos 30 atrasos válidos, "
            "a variação é calculada até um corte conservador que exclui os últimos P90 dias estimados; "
            "sem amostra suficiente, a variação fica N/A. Casos sem data de início dos sintomas "
            "continuam usando a data de notificação."
        ),
    }


def calculate_metrics(db_path: Path) -> dict[str, Any]:
    df = _read_cases(Path(db_path))

    if df.empty:
        raise ValueError("A tabela casos_srag não possui registros.")

    total = int(len(df))

    uti_known = df["UTI"].isin([1, 2])
    uti_yes = int((df["UTI"] == 1).sum())
    uti_denominator = int(uti_known.sum())

    # EVOLUCAO=3 é óbito por outras causas. A métrica é explicitamente
    # mortalidade por qualquer causa entre desfechos conhecidos.
    outcome_known = df["EVOLUCAO"].isin([1, 2, 3])
    deaths_any_cause = int(df["EVOLUCAO"].isin([2, 3]).sum())
    outcomes_denominator = int(outcome_known.sum())
    deaths_srag_only = int((df["EVOLUCAO"] == 2).sum())
    deaths_other_cause = int((df["EVOLUCAO"] == 3).sum())

    vaccination_known = df["VACINA_COV"].isin([1, 2])
    vaccination_yes = int((df["VACINA_COV"] == 1).sum())
    vaccination_denominator = int(vaccination_known.sum())

    delay = reporting_delay_summary(df)
    cutoff = pd.to_datetime(delay["data_corte_tendencia"], errors="coerce")

    recent_start = (
        cutoff - pd.Timedelta(29, unit="D")
        if pd.notna(cutoff)
        else pd.NaT
    )
    previous_end = (
        cutoff - pd.Timedelta(30, unit="D")
        if pd.notna(cutoff)
        else pd.NaT
    )
    previous_start = (
        cutoff - pd.Timedelta(59, unit="D")
        if pd.notna(cutoff)
        else pd.NaT
    )

    if pd.notna(cutoff):
        dates = df["DATA_REFERENCIA"]
        recent_count = int(
            dates.between(recent_start, cutoff, inclusive="both").sum()
        )
        previous_count = int(
            dates.between(previous_start, previous_end, inclusive="both").sum()
        )

        observed_start = dates.min()
        previous_window_complete = (
            pd.notna(observed_start) and observed_start <= previous_start
        )
    else:
        recent_count = previous_count = 0
        previous_window_complete = False

    variation = (
        round(100.0 * (recent_count - previous_count) / previous_count, 2)
        if previous_count > 0 and previous_window_complete
        else None
    )

    max_reference = df["DATA_REFERENCIA"].max()
    min_reference = df["DATA_REFERENCIA"].min()

    quality = {}

    for column in ("UTI", "EVOLUCAO", "VACINA_COV"):
        raw = df[column]
        known_codes = {
            "UTI": [1, 2],
            "EVOLUCAO": [1, 2, 3],
            "VACINA_COV": [1, 2],
        }[column]

        quality[column] = {
            "conhecidos": int(raw.isin(known_codes).sum()),
            "desconhecidos_ou_nulos": int((~raw.isin(known_codes)).sum()),
            "completude_percentual": _fmt_pct(
                _pct(int(raw.isin(known_codes).sum()), total)
            ),
        }

    # Esta contagem compara apenas as colunas minimizadas armazenadas. Como
    # identificadores de notificação/paciente não são retidos, ela não prova
    # duplicação de notificação ou de paciente e não deve acionar deduplicação.
    quality["duplicidades_exatas_na_base_minimizada"] = int(df.duplicated().sum())
    quality["interpretacao_duplicidades"] = (
        "Duplicidades exatas calculadas somente nas colunas analíticas minimizadas; "
        "não equivalem a duplicações confirmadas de pacientes/notificações e não foram removidas."
    )

    return {
        "fonte": SOURCE_DATASET_URL,
        "periodo_dados": {
            "inicio_referencia": (
                min_reference.strftime("%Y-%m-%d")
                if pd.notna(min_reference)
                else None
            ),
            "fim_referencia": (
                max_reference.strftime("%Y-%m-%d")
                if pd.notna(max_reference)
                else None
            ),
            "inicio_notificacao": df["DT_NOTIFIC"].min().strftime("%Y-%m-%d"),
            "fim_notificacao": df["DT_NOTIFIC"].max().strftime("%Y-%m-%d"),
            "total_casos_com_notificacao_valida": total,
            "definicao_data_referencia": (
                "DT_SIN_PRI; fallback para DT_NOTIFIC quando a data de sintomas não é válida."
            ),
        },
        "taxa_aumento_casos": {
            "valor": _fmt_pct(variation),
            "variacao_percentual_numerica": variation,
            "casos_periodo_recente": recent_count,
            "casos_periodo_anterior": previous_count,
            "periodo_recente": (
                f"{recent_start:%Y-%m-%d} a {cutoff:%Y-%m-%d}"
                if pd.notna(cutoff)
                else None
            ),
            "periodo_anterior": (
                f"{previous_start:%Y-%m-%d} a {previous_end:%Y-%m-%d}"
                if pd.notna(cutoff)
                else None
            ),
            "atraso_notificacao": delay,
            "interpretacao": (
                "N/A quando a janela anterior não é completa ou não há casos na janela de comparação."
            ),
        },
        "mortalidade_qualquer_causa_desfechos_conhecidos": {
            "valor": _fmt_pct(_pct(deaths_any_cause, outcomes_denominator)),
            "obitos_total": deaths_any_cause,
            "obitos_evolucao_2": deaths_srag_only,
            "obitos_evolucao_3_outras_causas": deaths_other_cause,
            "desfechos_conhecidos": outcomes_denominator,
            "regra": (
                "Numerador = EVOLUCAO 2 ou 3; denominador = EVOLUCAO 1, 2 ou 3. "
                "EVOLUCAO=3 é óbito por outras causas."
            ),
        },
        "taxa_internacao_uti_entre_casos_srag": {
            "valor": _fmt_pct(_pct(uti_yes, uti_denominator)),
            "internacoes_uti": uti_yes,
            "casos_com_informacao_uti": uti_denominator,
            "regra": (
                "UTI=1 / (UTI=1 ou UTI=2); códigos ignorados e inválidos não entram no denominador."
            ),
        },
        "proporcao_casos_com_vacina_covid_registrada": {
            "valor": _fmt_pct(_pct(vaccination_yes, vaccination_denominator)),
            "casos_com_vacina_covid_registrada": vaccination_yes,
            "casos_com_informacao_vacinal": vaccination_denominator,
            "regra": (
                "VACINA_COV=1 / (VACINA_COV=1 ou VACINA_COV=2). "
                "Refere-se a vacinação COVID-19 registrada nos casos, não à cobertura vacinal populacional."
            ),
        },
        "qualidade_e_completude": quality,
        "limitacoes": [
            "O banco SIVEP-Gripe contém notificações/casos SRAG; não fornece denominador da população geral.",
            "A proporção de internação em UTI entre casos não representa ocupação real de leitos de UTI.",
            "VACINA_COV é informação de vacinação contra COVID-19 entre os casos, não cobertura vacinal da população.",
            "EVOLUCAO=3 (óbito por outras causas) é incluído no indicador de mortalidade por qualquer causa; o numerador de EVOLUCAO=2 também é apresentado separadamente.",
            "As datas mais recentes são provisórias devido ao atraso de notificação e à possibilidade de revisão dos registros pelo Ministério da Saúde.",
        ],
    }