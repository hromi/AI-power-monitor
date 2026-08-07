from abc import ABC, abstractmethod
from typing import Any, Dict, List


class Collector(ABC):
    """Base class for a device/platform metrics collector.

    Implementations query one platform (NVIDIA, AMD, Intel, CPU RAPL, ...)
    and return one dict of metrics per device for a single sampling instant.
    """

    name = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this collector's tooling is present on the host."""

    @abstractmethod
    def collect(self) -> List[Dict[str, Any]]:
        """Return a list of per-device metric dicts for one sample."""
