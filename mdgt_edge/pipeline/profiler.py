"""Thread-safe pipeline profiler for stage-by-stage timing collection."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _StageRecord:
    """Accumulated timing data for a single pipeline stage."""

    durations: list[float] = field(default_factory=list)
    _start_time: float | None = field(default=None, repr=False)


class PipelineProfiler:
    """Thread-safe profiler that collects per-stage timing statistics.

    Usage::

        profiler = PipelineProfiler()
        profiler.start("preprocessing")
        # ... do work ...
        profiler.stop("preprocessing")
        report = profiler.get_report()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stages: dict[str, _StageRecord] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, stage: str) -> None:
        """Begin timing *stage*. Thread-safe."""
        with self._lock:
            record = self._stages.setdefault(stage, _StageRecord())
            record._start_time = time.perf_counter()

    def stop(self, stage: str) -> float:
        """Stop timing *stage* and record the elapsed duration.

        Returns:
            Elapsed time in **milliseconds**.

        Raises:
            ValueError: If *stage* was never started or is not currently running.
        """
        end = time.perf_counter()
        with self._lock:
            record = self._stages.get(stage)
            if record is None or record._start_time is None:
                raise ValueError(
                    f"Stage '{stage}' was never started or is not currently running."
                )
            elapsed_ms = (end - record._start_time) * 1000.0
            record.durations.append(elapsed_ms)
            record._start_time = None
        return elapsed_ms

    def record(self, stage: str, duration_ms: float) -> None:
        """Manually record a duration (ms) for *stage*."""
        with self._lock:
            record = self._stages.setdefault(stage, _StageRecord())
            record.durations.append(duration_ms)

    def get_report(self) -> dict[str, dict[str, Any]]:
        """Return per-stage statistics.

        For each stage the report contains:
        ``count``, ``avg_ms``, ``min_ms``, ``max_ms``, ``p95_ms``,
        ``total_ms``.
        """
        with self._lock:
            report: dict[str, dict[str, Any]] = {}
            for name, rec in self._stages.items():
                durations = rec.durations
                if not durations:
                    report[name] = {
                        "count": 0,
                        "avg_ms": 0.0,
                        "min_ms": 0.0,
                        "max_ms": 0.0,
                        "p95_ms": 0.0,
                        "total_ms": 0.0,
                    }
                    continue
                sorted_d = sorted(durations)
                count = len(sorted_d)
                p95_idx = min(int(count * 0.95), count - 1)
                report[name] = {
                    "count": count,
                    "avg_ms": sum(sorted_d) / count,
                    "min_ms": sorted_d[0],
                    "max_ms": sorted_d[-1],
                    "p95_ms": sorted_d[p95_idx],
                    "total_ms": sum(sorted_d),
                }
            return report

    def reset(self) -> None:
        """Clear all recorded data."""
        with self._lock:
            self._stages.clear()

    def export_json(self, path: str | None = None) -> str:
        """Export the report as a JSON string.

        If *path* is given the JSON is also written to that file.
        """
        report = self.get_report()
        json_str = json.dumps(report, indent=2)
        if path is not None:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json_str)
        return json_str
