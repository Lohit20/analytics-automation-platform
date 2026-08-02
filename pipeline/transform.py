"""Transform raw FX rate history into KPI, cost-benefit, and risk-model outputs."""

import numpy as np
import pandas as pd

import config


def add_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """Add day-over-day % change and rolling volatility (risk proxy) per currency."""
    df = df.sort_values(["currency", "date"]).copy()
    df["pct_change"] = df.groupby("currency")["rate"].pct_change()
    df["rolling_volatility"] = (
        df.groupby("currency")["pct_change"]
        .rolling(window=config.ROLLING_WINDOW_DAYS, min_periods=2)
        .std()
        .reset_index(level=0, drop=True)
    )
    return df


def build_kpi_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Summarise each currency into headline KPIs plus a simple risk and cost-benefit model.

    Risk model: a parametric Value-at-Risk style estimate — expected worst-case
    adverse move in the exposure amount over the reporting window, at ~95% confidence,
    based on observed daily rate volatility.

    Cost-benefit model: compares the assumed cost of hedging the exposure (fixed bps
    fee) against the modelled downside risk if left unhedged, to flag whether hedging
    looks worthwhile for each currency pair.
    """
    rows = []
    for currency, group in df.groupby("currency"):
        latest_rate = group["rate"].iloc[-1]
        first_rate = group["rate"].iloc[0]
        period_change_pct = (latest_rate / first_rate) - 1
        daily_volatility = group["pct_change"].std()

        exposure = config.DEFAULT_EXPOSURE_AMOUNT
        value_at_risk = exposure * daily_volatility * config.VAR_CONFIDENCE_Z if pd.notna(daily_volatility) else np.nan
        hedge_cost = exposure * (config.HEDGE_COST_BPS / 10_000)
        hedge_recommended = bool(value_at_risk > hedge_cost) if pd.notna(value_at_risk) else False

        rows.append(
            {
                "currency": currency,
                "latest_rate": round(latest_rate, 5),
                "period_change_pct": round(period_change_pct * 100, 2),
                "daily_volatility_pct": round(daily_volatility * 100, 3) if pd.notna(daily_volatility) else None,
                "exposure_amount": exposure,
                "value_at_risk_95": round(value_at_risk, 2) if pd.notna(value_at_risk) else None,
                "hedge_cost": round(hedge_cost, 2),
                "hedge_recommended": hedge_recommended,
            }
        )

    return pd.DataFrame(rows).sort_values("value_at_risk_95", ascending=False).reset_index(drop=True)
