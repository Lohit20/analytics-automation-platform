# Scheduling the Monthly Reporting Run

`run_report.py` is idempotent — every run re-extracts fresh data and overwrites
`data/*.csv` / `data/*.xlsx`, and appends one row to `data/pipeline_run_log.csv`.
That makes it safe to schedule on any cadence without cleanup logic.

## macOS (launchd) — included in this repo

`com.user.fxreport.plist` runs the pipeline on the 1st of every month at 07:00.

Install:

```bash
cp scheduling/com.user.fxreport.plist ~/Library/LaunchAgents/
# edit the plist first: replace /path/to/analytics-automation-platform with your actual path
launchctl load ~/Library/LaunchAgents/com.user.fxreport.plist
```

Check it's loaded: `launchctl list | grep fxreport`
Logs: `data/launchd_stdout.log` and `data/launchd_stderr.log`

## Linux / macOS (cron) — alternative

```bash
crontab -e
```

Add, to run at 07:00 on the 1st of every month:

```
0 7 1 * * cd /path/to/analytics-automation-platform && ./.venv/bin/python run_report.py >> data/cron.log 2>&1
```

## Windows (Task Scheduler) — alternative

```
schtasks /create /tn "FX Business Report" /tr "C:\path\to\analytics-automation-platform\.venv\Scripts\python.exe C:\path\to\analytics-automation-platform\run_report.py" /sc monthly /d 1 /st 07:00
```

## Why monthly + re-run safe, not a long-running service

The reporting cadence in the business use case (monthly management reporting) doesn't
need a persistent process — a scheduled one-shot script that regenerates the CSV/Excel
outputs is simpler to operate, easier to reason about on failure (check `pipeline_run_log.csv`),
and matches how the output is actually consumed (Power BI reads the CSVs on its own refresh
schedule, independent of when the Python job last ran).
