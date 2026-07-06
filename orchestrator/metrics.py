"""Metrics collection for AutoMind task execution.

This module provides a lightweight, structured metrics system to track:
- Phase durations (Planning, Generator, Evaluator, Summary)
- LLM token consumption
- Build/compilation times
- Cache hit/miss statistics
- Iteration counts and retry behavior
- Resource usage (CPU, memory)

Metrics are stored in runtime-state.json under the "metrics" key and displayed
in the HTML report for human review.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from orchestrator.state import read_runtime_state, update_runtime_state

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None


class MetricsCollector:
    """Collect and manage metrics for a single AutoMind task."""

    def __init__(self, task_dir: Path):
        self.task_dir = task_dir
        self._timers: dict[str, float] = {}
        self._metrics: dict[str, dict] = {}
        self._start_time = time.time()

    def start_timer(self, name: str) -> None:
        """Start a timer with the given name."""
        self._timers[name] = time.time()

    def stop_timer(self, name: str) -> float | None:
        """Stop the timer and record the duration. Returns the duration in seconds."""
        if name not in self._timers:
            return None
        duration = time.time() - self._timers.pop(name)
        self._record_timing(name, duration)
        return duration

    def record_metric(self, name: str, value: int | float | str, unit: str = "") -> None:
        """Record a simple metric with optional unit."""
        if name not in self._metrics:
            self._metrics[name] = {"values": [], "unit": unit}
        self._metrics[name]["values"].append(value)
        if unit:
            self._metrics[name]["unit"] = unit

    def record_llm_tokens(self, prompt_tokens: int, completion_tokens: int, model: str = "") -> None:
        """Record LLM token consumption."""
        self.record_metric("llm_prompt_tokens", prompt_tokens, "tokens")
        self.record_metric("llm_completion_tokens", completion_tokens, "tokens")
        self.record_metric("llm_total_tokens", prompt_tokens + completion_tokens, "tokens")
        if model:
            self.record_metric("llm_model", model)

    def record_phase_duration(self, phase: str, duration: float) -> None:
        """Record a phase duration explicitly."""
        self._record_timing(f"phase_{phase.lower()}_duration", duration)

    def record_iteration(self, iteration: int) -> None:
        """Record an iteration number."""
        self.record_metric("iteration", iteration)

    def record_cache_hit(self, cache_type: str, tc_id: str) -> None:
        """Record a cache hit."""
        self.record_metric(f"cache_{cache_type}_hit", 1)

    def record_cache_miss(self, cache_type: str, tc_id: str) -> None:
        """Record a cache miss."""
        self.record_metric(f"cache_{cache_type}_miss", 1)

    def record_warm_build(self, duration: float, status: str, platform: str) -> None:
        """Record warm build metrics."""
        self._record_timing("warm_build_duration", duration)
        self.record_metric("warm_build_status", status)
        self.record_metric("warm_build_platform", platform)

    def record_resource_usage(self) -> None:
        """Record current resource usage (CPU, memory)."""
        if psutil is None:
            return
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            cpu_percent = process.cpu_percent()
            self.record_metric("cpu_usage", cpu_percent, "%")
            self.record_metric("memory_usage", round(memory_mb, 2), "MB")
        except Exception:
            pass

    def _record_timing(self, name: str, duration: float) -> None:
        """Internal: Record a timing metric."""
        if name not in self._metrics:
            self._metrics[name] = {"values": [], "unit": "seconds"}
        self._metrics[name]["values"].append(duration)

    def compute_aggregates(self) -> dict:
        """Compute aggregate statistics for all metrics."""
        result: dict = {}
        for name, data in self._metrics.items():
            values = data.get("values", [])
            unit = data.get("unit", "")
            if not values:
                continue
            
            if isinstance(values[0], (int, float)):
                numeric = [float(v) for v in values]
                result[name] = {
                    "min": min(numeric),
                    "max": max(numeric),
                    "avg": sum(numeric) / len(numeric),
                    "sum": sum(numeric),
                    "count": len(numeric),
                    "unit": unit,
                }
            else:
                result[name] = {
                    "last": values[-1],
                    "count": len(values),
                    "unit": unit,
                }
        return result

    def flush(self) -> None:
        """Write all metrics to runtime-state.json."""
        aggregates = self.compute_aggregates()
        metrics_data = {
            "collectedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "taskDuration": round(time.time() - self._start_time, 2),
            "aggregates": aggregates,
        }
        update_runtime_state(self.task_dir, metrics=metrics_data)


_metrics_instances: dict[str, MetricsCollector] = {}


def get_metrics(task_dir: Path) -> MetricsCollector:
    """Get or create a MetricsCollector for the given task directory."""
    key = str(task_dir)
    if key not in _metrics_instances:
        _metrics_instances[key] = MetricsCollector(task_dir)
    return _metrics_instances[key]


def read_metrics(task_dir: Path) -> dict:
    """Read metrics from runtime-state.json."""
    state = read_runtime_state(task_dir) or {}
    return state.get("metrics") or {}


def record_phase_start(task_dir: Path, phase: str) -> None:
    """Record the start of a phase."""
    get_metrics(task_dir).start_timer(f"phase_{phase.lower()}")


def record_phase_end(task_dir: Path, phase: str) -> None:
    """Record the end of a phase and compute duration."""
    collector = get_metrics(task_dir)
    duration = collector.stop_timer(f"phase_{phase.lower()}")
    if duration is not None:
        collector.record_phase_duration(phase, duration)


def record_llm_usage(task_dir: Path, prompt_tokens: int, completion_tokens: int, model: str = "") -> None:
    """Record LLM token usage."""
    get_metrics(task_dir).record_llm_tokens(prompt_tokens, completion_tokens, model)


def flush_metrics(task_dir: Path) -> None:
    """Flush all metrics to runtime-state.json."""
    get_metrics(task_dir).flush()
