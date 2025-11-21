# Monitoring Workflow

## Nightly Data Maintenance

Run the bundled maintenance (reports + exports + sanity checks) with:

```bash
python scripts/run_daily_maintenance.py
```

This will:
- Generate the latest 6h quarterly report (latest session)
- Generate the latest 24h daily report (latest session)
- Refresh the 30d demo export bundle (CSV + behavior summary)
- Run the 72h sanity checker for HFT/safety rails
- Print the key output paths and a one-line sanity status
