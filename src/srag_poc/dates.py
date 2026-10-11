"""Leitura explícita e auditável das datas dos CSVs do SIVEP-Gripe."""

from __future__ import annotations

import pandas as pd


def parse_brazilian_dates(values: pd.Series) -> pd.Series:
    """Converte datas brasileiras e ISO para datetime sem fuso e normalizado.

    Os CSVs do DATASUS podem conter datas brasileiras (dd/mm/aaaa), datas ISO
    (aaaa-mm-dd) e timestamps ISO como ``2025-05-11T00:00:00.000Z``. Cada
    família é interpretada explicitamente. Não usar ``dayfirst=True`` como
    fallback genérico: ele pode inverter mês e dia de timestamps ISO.

    Valores vazios, sentinelas e datas inválidas resultam em ``NaT``.
    """
    text = values.astype("string").str.strip()
    null_tokens = {"", "NA", "NAN", "NULL", "NAT", "NONE"}
    text = text.mask(text.str.upper().isin(null_tokens), pd.NA)

    # ISO8601 interpreta tanto datas simples como timestamps com T, frações
    # de segundo e timezone. Convertemos para UTC e removemos o fuso para que
    # a saída tenha o mesmo dtype das datas brasileiras sem fuso.
    parsed_iso = pd.to_datetime(
        text,
        format="ISO8601",
        errors="coerce",
        utc=True,
    ).dt.tz_convert(None)

    # Formatos brasileiros explícitos; sem inferência global do formato.
    parsed_br = pd.to_datetime(text, format="%d/%m/%Y", errors="coerce")
    for fmt in (
        "%d/%m/%Y %H:%M:%S.%f",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ):
        candidate = pd.to_datetime(text, format=fmt, errors="coerce")
        parsed_br = parsed_br.fillna(candidate)

    result = parsed_iso.fillna(parsed_br)
    return result.dt.normalize()
