import argparse
import logging
import os
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .collectors.nvidia import NvidiaSmiCollector
from .csv_writer import DailyCsvWriter

FIELDNAMES = [
    "timestamp_utc",
    "timestamp_epoch",
    "hostname",
    "gpu_index",
    "gpu_uuid",
    "gpu_name",
    "temperature_c",
    "utilization_gpu_pct",
    "utilization_mem_pct",
    "memory_used_mib",
    "memory_total_mib",
    "power_draw_w",
    "power_limit_w",
    "fan_speed_pct",
    "clock_sm_mhz",
    "clock_mem_mhz",
    "process_count",
]


class Daemon:
    def __init__(self, collectors, writer: DailyCsvWriter, interval: float):
        self.collectors = collectors
        self.writer = writer
        self.interval = interval
        self.hostname = socket.gethostname()
        self._stop = False

    def request_stop(self, *_args) -> None:
        self._stop = True

    def _poll_once(self) -> None:
        now = datetime.now(timezone.utc)
        rows = []
        for collector in self.collectors:
            try:
                metrics = collector.collect()
            except Exception:
                logging.exception("Collector %s failed", collector.name)
                continue
            for metric in metrics:
                rows.append(
                    {
                        "timestamp_utc": now.isoformat(),
                        "timestamp_epoch": int(now.timestamp()),
                        "hostname": self.hostname,
                        **metric,
                    }
                )
        if rows:
            self.writer.write_rows(rows, now=now.astimezone())
        else:
            logging.warning("No metrics collected this cycle")

    def run(self, run_once: bool = False) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        logging.info("ai-power-monitor started (interval=%ss)", self.interval)
        try:
            while not self._stop:
                start = time.monotonic()
                self._poll_once()
                if run_once:
                    break
                elapsed = time.monotonic() - start
                time.sleep(max(0.0, self.interval - elapsed))
        finally:
            self.writer.close()
            logging.info("ai-power-monitor stopped")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI power/GPU usage monitoring daemon")
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("AIPM_INTERVAL", 10)),
        help="Polling interval in seconds (default: 10)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.environ.get("AIPM_OUTPUT_DIR", "data")),
        help="Directory to write daily CSV files (default: ./data)",
    )
    parser.add_argument(
        "--no-gzip",
        action="store_true",
        default=os.environ.get("AIPM_NO_GZIP", "").lower() in ("1", "true", "yes"),
        help="Disable gzip compression of previous days' CSV files",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("AIPM_LOG_LEVEL", "INFO"),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single collection cycle and exit (for testing)",
    )
    return parser


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    collectors = []
    nvidia = NvidiaSmiCollector()
    if nvidia.is_available():
        collectors.append(nvidia)
    else:
        logging.error("nvidia-smi not found on PATH; no GPU metrics will be collected")

    if not collectors:
        logging.error("No collectors available, exiting")
        return 1

    writer = DailyCsvWriter(args.output_dir, FIELDNAMES, gzip_on_rollover=not args.no_gzip)
    daemon = Daemon(collectors, writer, args.interval)
    daemon.run(run_once=args.once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
