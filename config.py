"""Configuration for the FX business reporting pipeline."""

BASE_CURRENCY = "USD"
TARGET_CURRENCIES = ["EUR", "GBP", "JPY", "INR", "AUD"]

API_BASE_URL = "https://api.frankfurter.app"

HISTORY_DAYS = 90

# Risk model assumptions
ROLLING_WINDOW_DAYS = 7          # window for rolling volatility
VAR_CONFIDENCE_Z = 1.65          # ~95% one-tailed z-score for simple VaR
DEFAULT_EXPOSURE_AMOUNT = 100_000  # notional exposure per currency, in BASE_CURRENCY, for cost-benefit modelling
HEDGE_COST_BPS = 25              # assumed cost of hedging, in basis points of exposure

DATA_DIR = "data"
CSV_RATES_PATH = f"{DATA_DIR}/fx_rates_history.csv"
CSV_KPI_PATH = f"{DATA_DIR}/fx_kpi_summary.csv"
EXCEL_REPORT_PATH = f"{DATA_DIR}/business_reporting_dashboard.xlsx"
LOG_PATH = f"{DATA_DIR}/pipeline_run_log.csv"
