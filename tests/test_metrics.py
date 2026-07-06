"""Unit tests for metrics collection."""
from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from orchestrator.metrics import (
    MetricsCollector,
    get_metrics,
    record_phase_start,
    record_phase_end,
    flush_metrics,
    read_metrics,
    psutil,
)
from orchestrator.state import read_runtime_state, update_runtime_state


class TestMetricsCollector:
    def test_start_and_stop_timer(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            collector = MetricsCollector(task_dir)
            collector.start_timer("test_timer")
            time.sleep(0.01)
            duration = collector.stop_timer("test_timer")
            assert duration is not None
            assert duration >= 0.01
            assert duration < 0.5

    def test_stop_nonexistent_timer(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            collector = MetricsCollector(task_dir)
            result = collector.stop_timer("nonexistent")
            assert result is None

    def test_record_metric(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            collector = MetricsCollector(task_dir)
            collector.record_metric("test_metric", 42, "units")
            collector.record_metric("test_metric", 48, "units")
            aggregates = collector.compute_aggregates()
            assert "test_metric" in aggregates
            assert aggregates["test_metric"]["sum"] == 90
            assert aggregates["test_metric"]["avg"] == 45
            assert aggregates["test_metric"]["count"] == 2
            assert aggregates["test_metric"]["unit"] == "units"

    def test_record_llm_tokens(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            collector = MetricsCollector(task_dir)
            collector.record_llm_tokens(100, 200, "test-model")
            aggregates = collector.compute_aggregates()
            assert aggregates["llm_prompt_tokens"]["sum"] == 100
            assert aggregates["llm_completion_tokens"]["sum"] == 200
            assert aggregates["llm_total_tokens"]["sum"] == 300

    def test_record_phase_duration(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            collector = MetricsCollector(task_dir)
            collector.record_phase_duration("planning", 15.5)
            aggregates = collector.compute_aggregates()
            assert aggregates["phase_planning_duration"]["sum"] == 15.5

    def test_record_cache_hit_miss(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            collector = MetricsCollector(task_dir)
            collector.record_cache_hit("ui_path", "TC-001")
            collector.record_cache_miss("ui_path", "TC-002")
            collector.record_cache_hit("ui_path", "TC-003")
            aggregates = collector.compute_aggregates()
            assert aggregates["cache_ui_path_hit"]["sum"] == 2
            assert aggregates["cache_ui_path_miss"]["sum"] == 1

    def test_record_warm_build(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            collector = MetricsCollector(task_dir)
            collector.record_warm_build(45.2, "completed", "ios")
            aggregates = collector.compute_aggregates()
            assert aggregates["warm_build_duration"]["sum"] == 45.2

    def test_record_resource_usage(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            collector = MetricsCollector(task_dir)
            collector.record_resource_usage()
            aggregates = collector.compute_aggregates()
            if psutil is None:
                assert aggregates == {}
            else:
                assert "cpu_usage" in aggregates or "memory_usage" in aggregates

    def test_flush_metrics(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            collector = MetricsCollector(task_dir)
            collector.record_phase_duration("planning", 10.0)
            collector.flush()
            state = read_runtime_state(task_dir)
            assert "metrics" in state
            assert state["metrics"]["taskDuration"] >= 0
            assert "aggregates" in state["metrics"]
            assert state["metrics"]["aggregates"]["phase_planning_duration"]["sum"] == 10.0


class TestMetricsModule:
    def test_get_metrics_singleton(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            collector1 = get_metrics(task_dir)
            collector2 = get_metrics(task_dir)
            assert collector1 is collector2

    def test_record_phase_start_end(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            record_phase_start(task_dir, "test")
            time.sleep(0.01)
            record_phase_end(task_dir, "test")
            aggregates = get_metrics(task_dir).compute_aggregates()
            assert aggregates["phase_test_duration"]["sum"] >= 0.01

    def test_flush_metrics_to_state(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            record_phase_start(task_dir, "test")
            time.sleep(0.01)
            record_phase_end(task_dir, "test")
            flush_metrics(task_dir)
            metrics = read_metrics(task_dir)
            assert "taskDuration" in metrics
            assert "aggregates" in metrics

    def test_read_empty_metrics(self):
        with TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            metrics = read_metrics(task_dir)
            assert metrics == {}
