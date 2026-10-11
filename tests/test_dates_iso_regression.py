import pandas as pd

from srag_poc.dates import parse_brazilian_dates


def test_iso_timestamps_keep_month_and_day_in_correct_order():
    values = pd.Series([
        "2025-05-11T00:00:00.000Z",
        "2025-02-15T00:00:00.000Z",
        "2026-03-23T00:00:00.000Z",
    ])

    parsed = parse_brazilian_dates(values)

    assert parsed.tolist() == [
        pd.Timestamp("2025-05-11"),
        pd.Timestamp("2025-02-15"),
        pd.Timestamp("2026-03-23"),
    ]


def test_brazilian_and_iso_date_formats_are_both_supported():
    values = pd.Series([
        "01/02/2026",
        "2026-02-01",
        "31/12/2025",
        "2025-12-31T00:00:00.000Z",
        "31/12/2025 13:45:10",
        "invalid",
        "",
        None,
    ])

    parsed = parse_brazilian_dates(values)

    assert parsed.iloc[0] == pd.Timestamp("2026-02-01")
    assert parsed.iloc[1] == pd.Timestamp("2026-02-01")
    assert parsed.iloc[2] == pd.Timestamp("2025-12-31")
    assert parsed.iloc[3] == pd.Timestamp("2025-12-31")
    assert parsed.iloc[4] == pd.Timestamp("2025-12-31")
    assert parsed.iloc[5:].isna().all()
