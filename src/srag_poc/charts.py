"""Geração determinística dos gráficos da PoC."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def generate_charts(db_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        df = pd.read_sql_query("SELECT DATA_REFERENCIA, ORIGEM_DATA_REFERENCIA FROM casos_srag", connection)
    if df.empty:
        raise ValueError("Sem dados para gerar gráficos.")
    df["DATA_REFERENCIA"] = pd.to_datetime(df["DATA_REFERENCIA"], errors="coerce")
    df = df.dropna(subset=["DATA_REFERENCIA"])
    if df.empty:
        raise ValueError("Sem datas de referência válidas para gerar gráficos.")

    max_date = df["DATA_REFERENCIA"].max().normalize()
    min_30 = max_date - pd.Timedelta(days=29)
    daily = df.loc[df["DATA_REFERENCIA"].between(min_30, max_date), "DATA_REFERENCIA"].value_counts().sort_index()
    daily = daily.reindex(pd.date_range(min_30, max_date, freq="D"), fill_value=0)
    daily_path = output_dir / "grafico_30_dias.png"
    fig, ax = plt.subplots(figsize=(11, 5))
    daily.plot(ax=ax, marker="o")
    ax.set_title("Notificações/casos SRAG por data de referência - últimos 30 dias")
    ax.set_xlabel("Data de referência: início dos sintomas quando disponível; fallback para notificação")
    ax.set_ylabel("Número de casos")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(daily_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    month_last = max_date.to_period("M")
    month_periods = pd.period_range(end=month_last, periods=12, freq="M")
    df["MES"] = df["DATA_REFERENCIA"].dt.to_period("M")
    monthly = df.groupby("MES").size().reindex(month_periods, fill_value=0)
    monthly_path = output_dir / "grafico_12_meses.png"
    month_partial = max_date.day < max_date.days_in_month
    fig, ax = plt.subplots(figsize=(11, 5))
    monthly.index = monthly.index.astype(str)
    monthly.plot(ax=ax, kind="bar")
    title = "Notificações/casos SRAG por mês - últimos 12 meses"
    if month_partial:
        title += " (último mês parcial)"
    ax.set_title(title)
    ax.set_xlabel("Mês da data de referência")
    ax.set_ylabel("Número de casos")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(monthly_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    onset_share = float((df["ORIGEM_DATA_REFERENCIA"] == "DT_SIN_PRI").mean() * 100)
    return {
        "status": "success",
        "grafico_30_dias": str(daily_path),
        "grafico_12_meses": str(monthly_path),
        "grafico_30_dias_markdown": "![Casos diários de SRAG](grafico_30_dias.png)",
        "grafico_12_meses_markdown": "![Casos mensais de SRAG](grafico_12_meses.png)",
        "data_corte_graficos": max_date.strftime("%Y-%m-%d"),
        "periodo_30_dias": f"{min_30:%Y-%m-%d} a {max_date:%Y-%m-%d}",
        "periodo_12_meses": f"{month_periods[0]} a {month_periods[-1]}",
        "mes_final_parcial": month_partial,
        "percentual_com_data_inicio_sintomas": round(onset_share, 2),
        "aviso_atraso": "As observações mais recentes podem ser revisadas/subnotificadas; leia a série como provisória.",
    }
