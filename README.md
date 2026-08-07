# AI Power Consumption Counter

A lightweight daemon that periodically samples GPU utilization, temperature,
power draw, memory usage, and process count, writing the results to
daily-rotated (and gzip-compressed) CSV files.

Currently supports NVIDIA GPUs via `nvidia-smi`. The collector interface
(`ai_power_monitor/collectors/base.py`) is designed to be extended with
additional platforms later (AMD `rocm-smi`, Intel GPUs, CPU power via RAPL,
etc.) — each new collector just implements `is_available()` and `collect()`.

## Requirements

- Python 3.8+
- `nvidia-smi` on `PATH` (ships with the NVIDIA driver)
- No third-party Python packages — standard library only

## Usage

```bash
# single test cycle, writing to ./data
python3 -m ai_power_monitor --once --output-dir ./data --log-level DEBUG

# run continuously, sampling every 10s
python3 -m ai_power_monitor --interval 10 --output-dir ./data
```

### CLI options

| Flag | Env var | Default | Description |
|---|---|---|---|
| `--interval` | `AIPM_INTERVAL` | `10` | Seconds between samples |
| `--output-dir` | `AIPM_OUTPUT_DIR` | `data` | Directory for daily CSV files |
| `--no-gzip` | `AIPM_NO_GZIP` | off | Skip gzip-compressing completed days |
| `--log-level` | `AIPM_LOG_LEVEL` | `INFO` | Python logging level |
| `--once` | — | off | Run a single sample and exit |

## Output format

One row per GPU per sample, written to `<output-dir>/YYYY-MM-DD.csv`:

```
timestamp_utc,timestamp_epoch,hostname,gpu_index,gpu_uuid,gpu_name,
temperature_c,utilization_gpu_pct,utilization_mem_pct,
memory_used_mib,memory_total_mib,power_draw_w,power_limit_w,
fan_speed_pct,clock_sm_mhz,clock_mem_mhz,process_count
```

At day rollover (and at startup, for any file left over from a previous day)
the previous day's `YYYY-MM-DD.csv` is compressed to `YYYY-MM-DD.csv.gz` and
the plain CSV is removed.

## Running as a systemd service

1. Create a dedicated user and install the code:

   ```bash
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin gpu-monitor
   sudo mkdir -p /opt/ai-power-monitor
   sudo cp -r ai_power_monitor /opt/ai-power-monitor/
   sudo chown -R gpu-monitor:gpu-monitor /opt/ai-power-monitor
   ```

2. Install the unit file:

   ```bash
   sudo cp systemd/ai-power-monitor.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now ai-power-monitor.service
   ```

   Data is written to `/var/lib/ai-power-monitor` (managed via systemd's
   `StateDirectory=`). Adjust `--interval`/paths in the unit file, or drop
   overrides into `/etc/default/ai-power-monitor` (referenced via
   `EnvironmentFile=`), e.g.:

   ```
   AIPM_INTERVAL=15
   ```

   Note: `AIPM_INTERVAL` etc. are only read as *argparse defaults*, so if you
   want to override via `/etc/default/ai-power-monitor` instead of editing
   `ExecStart` directly, drop the explicit `--interval`/`--output-dir` flags
   from the unit's `ExecStart` line.

3. Check status / logs:

   ```bash
   sudo systemctl status ai-power-monitor.service
   sudo journalctl -u ai-power-monitor.service -f
   ```

## Extending to other platforms

Add a new module under `ai_power_monitor/collectors/` implementing the
`Collector` interface (`is_available()`, `collect()`), then register it
alongside `NvidiaSmiCollector` in `daemon.main()`. Rows from different
collectors are merged into the same CSV schema, so add any new fields to
`FIELDNAMES` in `ai_power_monitor/daemon.py` as needed.
