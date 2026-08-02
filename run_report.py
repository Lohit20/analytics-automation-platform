"""End-to-end entrypoint for the FX business reporting pipeline.

Run manually:
    python run_report.py

Run on a schedule: see scheduling/README.md for cron / Task Scheduler / launchd setup.
Each run overwrites the CSV/Excel outputs in data/ and appends one row to the run log,
so this script is safe to re-run or schedule repeatedly (idempotent outputs).
"""

import datetime as dt
import os
import sys
import traceback

import pandas as pd

import config
from pipeline import extract, load, transform


def _log_run(status: str, detail: str = "") -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    entry = pd.DataFrame(
        [{"run_timestamp": dt.datetime.now().isoformat(timespec="seconds"), "status": status, "detail": detail}]
    )
    header = not os.path.exists(config.LOG_PATH)
    entry.to_csv(config.LOG_PATH, mode="a", header=header, index=False)


def main() -> int:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    try:
        print("Extracting FX rate history...")
        history_df = extract.fetch_historical_rates()

        print("Computing KPIs, volatility, and risk/cost-benefit model...")
        history_df = transform.add_kpis(history_df)
        kpi_df = transform.build_kpi_summary(history_df)

        print("Writing Power BI CSVs and Excel report...")
        load.write_csvs(history_df, kpi_df)
        load.write_excel_report(history_df, kpi_df)

        _log_run("success", f"{len(history_df)} rate rows, {len(kpi_df)} currencies")
        print(f"Done. Outputs written to {config.DATA_DIR}/")
        return 0
    except Exception as exc:  # noqa: BLE001 - top-level entrypoint, log and exit non-zero for scheduler visibility
        _log_run("failure", str(exc))
        print("Pipeline run failed:", exc, file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
