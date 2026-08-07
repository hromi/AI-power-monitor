import csv
import gzip
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


class DailyCsvWriter:
    """Writes metric rows to a CSV file per calendar day.

    On rollover to a new day (and at startup, for any files left over from a
    previous run) the previous day's CSV is gzipped and the plain .csv is
    removed.
    """

    def __init__(self, output_dir: Path, fieldnames: List[str], gzip_on_rollover: bool = True):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.fieldnames = fieldnames
        self.gzip_on_rollover = gzip_on_rollover
        self._current_date: Optional[str] = None
        self._file = None
        self._writer: Optional[csv.DictWriter] = None
        if self.gzip_on_rollover:
            self._gzip_stale_files()

    def _path_for(self, date_str: str) -> Path:
        return self.output_dir / f"{date_str}.csv"

    def _gzip_stale_files(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        for path in sorted(self.output_dir.glob("*.csv")):
            if path.stem == today:
                continue
            self._gzip_file(path)

    @staticmethod
    def _gzip_file(path: Path) -> None:
        gz_path = path.with_suffix(path.suffix + ".gz")
        try:
            with open(path, "rb") as src, gzip.open(gz_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            path.unlink()
            logger.info("Compressed %s -> %s", path.name, gz_path.name)
        except OSError:
            logger.exception("Failed to compress %s", path)

    def _rotate_if_needed(self, now: datetime) -> None:
        date_str = now.strftime("%Y-%m-%d")
        if date_str == self._current_date:
            return
        if self._file is not None:
            prev_date = self._current_date
            self._file.close()
            if self.gzip_on_rollover:
                self._gzip_file(self._path_for(prev_date))
        path = self._path_for(date_str)
        write_header = not path.exists()
        self._file = open(path, "a", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.fieldnames)
        if write_header:
            self._writer.writeheader()
            self._file.flush()
        self._current_date = date_str

    def write_rows(self, rows: Iterable[Dict], now: Optional[datetime] = None) -> None:
        now = now or datetime.now()
        self._rotate_if_needed(now)
        for row in rows:
            self._writer.writerow(row)
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
