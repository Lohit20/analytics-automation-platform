"""Extract live and historical FX rate data from the Frankfurter API (ECB-sourced, free, no API key)."""

import datetime as dt

import pandas as pd
import requests

import config


def _get(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_latest_rates() -> dict:
    """Pull the most recent FX rates for the configured currency pairs."""
    payload = _get(
        f"{config.API_BASE_URL}/latest",
        {"from": config.BASE_CURRENCY, "to": ",".join(config.TARGET_CURRENCIES)},
    )
    return payload


def fetch_historical_rates(days: int = config.HISTORY_DAYS) -> pd.DataFrame:
    """Pull a rolling window of daily FX rates and return a tidy long-format DataFrame."""
    end_date = dt.date.today()
    start_date = end_date - dt.timedelta(days=days)

    payload = _get(
        f"{config.API_BASE_URL}/{start_date.isoformat()}..{end_date.isoformat()}",
        {"from": config.BASE_CURRENCY, "to": ",".join(config.TARGET_CURRENCIES)},
    )

    records = []
    for date_str, rates in payload["rates"].items():
        for currency, rate in rates.items():
            records.append({"date": date_str, "currency": currency, "rate": rate})

    df = pd.DataFrame.from_records(records)
    df["date"] = pd.to_datetime(df["date"])
    df["base_currency"] = payload["base"]
    df = df.sort_values(["currency", "date"]).reset_index(drop=True)
    return df
