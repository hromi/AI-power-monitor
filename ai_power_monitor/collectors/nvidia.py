import csv
import io
import logging
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from .base import Collector

logger = logging.getLogger(__name__)

GPU_QUERY_FIELDS = [
    "uuid",
    "index",
    "name",
    "temperature.gpu",
    "utilization.gpu",
    "utilization.memory",
    "memory.used",
    "memory.total",
    "power.draw",
    "power.limit",
    "fan.speed",
    "clocks.sm",
    "clocks.mem",
]

PROCESS_QUERY_FIELDS = ["pid", "gpu_uuid"]


class NvidiaSmiCollector(Collector):
    """Collects per-GPU metrics by shelling out to nvidia-smi.

    Kept dependency-free (no pynvml) so the daemon runs anywhere nvidia-smi
    is already installed. Swap in a pynvml-based collector later if lower
    per-sample overhead is needed.
    """

    name = "nvidia"

    def __init__(self, binary: str = "nvidia-smi", timeout: float = 5.0):
        self.binary = binary
        self.timeout = timeout

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def _run(self, args: List[str]) -> str:
        result = subprocess.run(
            [self.binary, *args],
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=True,
        )
        return result.stdout

    def _query_gpus(self) -> List[Dict[str, str]]:
        out = self._run(
            [
                f"--query-gpu={','.join(GPU_QUERY_FIELDS)}",
                "--format=csv,noheader,nounits",
            ]
        )
        rows = []
        for raw in csv.reader(io.StringIO(out)):
            if not raw:
                continue
            values = [v.strip() for v in raw]
            if len(values) != len(GPU_QUERY_FIELDS):
                logger.warning("Unexpected nvidia-smi GPU row: %r", raw)
                continue
            rows.append(dict(zip(GPU_QUERY_FIELDS, values)))
        return rows

    def _query_process_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        try:
            out = self._run(
                [
                    f"--query-compute-apps={','.join(PROCESS_QUERY_FIELDS)}",
                    "--format=csv,noheader,nounits",
                ]
            )
        except subprocess.CalledProcessError as exc:
            logger.debug("nvidia-smi compute-apps query failed: %s", exc)
            return counts
        for raw in csv.reader(io.StringIO(out)):
            if len(raw) < 2:
                continue
            gpu_uuid = raw[1].strip()
            counts[gpu_uuid] = counts.get(gpu_uuid, 0) + 1
        return counts

    @staticmethod
    def _to_number(value: str, cast=float) -> Optional[Any]:
        value = value.strip()
        if value in ("", "[N/A]", "N/A"):
            return None
        try:
            return cast(value)
        except ValueError:
            return None

    def collect(self) -> List[Dict[str, Any]]:
        gpu_rows = self._query_gpus()
        process_counts = self._query_process_counts()
        results = []
        for row in gpu_rows:
            uuid = row["uuid"]
            results.append(
                {
                    "gpu_index": self._to_number(row["index"], int),
                    "gpu_uuid": uuid,
                    "gpu_name": row["name"],
                    "temperature_c": self._to_number(row["temperature.gpu"]),
                    "utilization_gpu_pct": self._to_number(row["utilization.gpu"]),
                    "utilization_mem_pct": self._to_number(row["utilization.memory"]),
                    "memory_used_mib": self._to_number(row["memory.used"]),
                    "memory_total_mib": self._to_number(row["memory.total"]),
                    "power_draw_w": self._to_number(row["power.draw"]),
                    "power_limit_w": self._to_number(row["power.limit"]),
                    "fan_speed_pct": self._to_number(row["fan.speed"]),
                    "clock_sm_mhz": self._to_number(row["clocks.sm"]),
                    "clock_mem_mhz": self._to_number(row["clocks.mem"]),
                    "process_count": process_counts.get(uuid, 0),
                }
            )
        return results
