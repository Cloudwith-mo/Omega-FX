# Export Recent Logs Tool

## Overview

`export_recent_logs.py` is a CLI utility to extract and analyze execution logs within a specific time window. It's useful for:

- Creating focused reports on recent trading activity
- Debugging recent trades
- Generating summaries for specific time periods
- Extracting data for analysis tools

## Quick export from any machine

1. `git pull`
2. `python scripts/run_export_bundle.py --days 30 --env demo`
3. Check `results/data_exports/` for `exec_log_last_30d_demo.csv` and `behavior_summary_last_30d_demo.txt` (absolute paths are printed).

## Usage

### Basic Examples

**Export last 48 hours:**
```bash
python scripts/export_recent_logs.py --hours 48 --env demo
```

**Export last 3 days:**
```bash
python scripts/export_recent_logs.py --days 3 --env demo
```

**Export with custom paths:**
```bash
python scripts/export_recent_logs.py \
  --hours 24 \
  --env live \
  --log-path results/mt5_live_exec_log.csv \
  --output-path results/custom_export.csv
```

**Include historical (simulated) data:**
```bash
python scripts/export_recent_logs.py --hours 48 --env demo --include-historical
```

## Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--hours` | float | None | Export logs from last N hours |
| `--days` | float | None | Export logs from last N days (converted to hours) |
| `--env` | str | demo | Environment label (demo, live, etc.) |
| `--log-path` | Path | Auto | Input log path (auto: `results/mt5_{env}_exec_log.csv`) |
| `--output-path` | Path | Auto | Output CSV path (auto: `results/mt5_exec_log_last_{window}_{env}.csv`) |
| `--include-historical` | flag | False | Include historical/simulated rows (not just live) |

## Output

### CSV File

The tool creates a filtered CSV file with the same structure as the input log, containing only rows within the specified time window.

**Default naming:**
- Last 48 hours: `mt5_exec_log_last_48h_demo.csv`
- Last 3 days: `mt5_exec_log_last_3d_demo.csv`

### Summary Report

Printed to stdout with:

```
======================================================================
EXPORTED RECENT LOGS
======================================================================

Output: results/mt5_exec_log_last_48h_demo.csv
Total rows: 127

Window:
  Start: 2025-11-19T14:16:58+00:00
  End:   2025-11-21T14:16:58+00:00

Events:
  OPEN trades:   45
  CLOSE trades:  42
  FILTER events: 8

Performance:
  Total P&L:  $1,247.50
  Avg P&L:    $29.70
  Win rate:   64.3%

Per-Strategy Trade Counts (CLOSE events):
  OMEGA_M15_TF1: 25
  OMEGA_MR_M15: 12
  OMEGA_SESSION_LDN_M15: 5

======================================================================
```

## Implementation Details

### Time Filtering

- Uses UTC timestamps for consistency
- Filters rows where: `window_start <= timestamp <= window_end`
- Window end = current time
- Window start = current time - hours

### Data Mode Filtering

By default, only `data_mode="live"` rows are included. Use `--include-historical` to include simulated/backtested trades.

### PnL Calculation

- Reads `pnl` field from CLOSE events
- Computes total, average, and win rate
- Handles missing/invalid PnL values gracefully

### Strategy Breakdown

- Counts OPEN and CLOSE events per `strategy_id`
- Uses `strategy_id` field from log rows
- Falls back to "unknown" if field is missing

## Testing

Run tests with:
```bash
pytest tests/test_export_recent_logs.py -v
```

Tests cover:
- Time-based filtering accuracy
- PnL calculation correctness
- Per-strategy count aggregation
- Edge cases (empty logs, missing fields)

## Integration with Existing Tools

This tool reuses:
- `_parse_timestamp()` from `run_daily_exec_report.py`
- `_safe_float()` from `run_daily_exec_report.py`
- CSV structure from autopilot execution logs

## Example Workflow

1. **Run autopilot** for a few days
2. **Export last 48h** to analyze recent performance:
   ```bash
   python scripts/export_recent_logs.py --hours 48 --env demo
   ```
3. **Review summary** for quick insights
4. **Import CSV** into spreadsheet/dashboard for deeper analysis

## Troubleshooting

**"ERROR: Log file not found"**
- Check that `results/mt5_{env}_exec_log.csv` exists
- Or specify custom path with `--log-path`

**"ERROR: Must specify either --hours or --days"**
- You must provide exactly one time window argument

**Empty output / no rows**
- Check that autopilot has been running recently
- Try increasing the time window
- Use `--include-historical` to include simulated data

## Future Enhancements

Potential additions:
- [ ] Filter by strategy ID
- [ ] Filter by symbol
- [ ] Export to JSON format
- [ ] Combine multiple log files
- [ ] Automatic chart generation
