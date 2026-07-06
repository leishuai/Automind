"""Tests for warm_build module."""
import os
from pathlib import Path

import pytest

from orchestrator.warm_build import (
    detect_platform,
    get_warm_build_status,
    is_incremental_build_possible,
    should_trigger_warm_build,
    start_warm_build,
    wait_for_warm_build,
    WARM_BUILD_MAX_WAIT_SECONDS,
)
from orchestrator.state import read_runtime_state, write_runtime_state


def test_detect_platform_ios(tmp_path: Path) -> None:
    """Test iOS platform detection."""
    (tmp_path / "MyApp.xcodeproj").mkdir()
    (tmp_path / "ViewController.swift").write_text("class ViewController {}")
    
    os.environ["AUTOMIND_WORKSPACE_ROOT"] = str(tmp_path)
    platform = detect_platform(tmp_path / "task")
    assert platform == "ios", f"Expected 'ios' but got '{platform}'"


def test_detect_platform_android(tmp_path: Path) -> None:
    """Test Android platform detection."""
    (tmp_path / "build.gradle").write_text("apply plugin: 'com.android.application'")
    (tmp_path / "MainActivity.kt").write_text("class MainActivity : AppCompatActivity() {}")
    
    os.environ["AUTOMIND_WORKSPACE_ROOT"] = str(tmp_path)
    assert detect_platform(tmp_path / "task") == "android"


def test_detect_platform_web(tmp_path: Path) -> None:
    """Test Web platform detection."""
    (tmp_path / "package.json").write_text('{"name": "my-app"}')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("const App = () => <div>Hello</div>")
    
    os.environ["AUTOMIND_WORKSPACE_ROOT"] = str(tmp_path)
    assert detect_platform(tmp_path / "task") == "web"


def test_should_trigger_warm_build_skips_without_runtime_testcases(tmp_path: Path) -> None:
    """Test warm build is skipped when no runtime testcases exist."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "TestCases.md").write_text("""# Test Cases\n| ID | Requirement/AC | Type | Runtime level | Required? |\n|----|----------------|------|---------------|-----------|\n| TC-01 | R01 | Unit | unit | yes |""")
    
    should_trigger, reason = should_trigger_warm_build(task_dir)
    assert not should_trigger
    assert "no required runtime-level test cases" in reason


def test_should_trigger_warm_build_skips_without_platform(tmp_path: Path) -> None:
    """Test warm build is skipped when platform cannot be detected."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "TestCases.md").write_text("""# Test Cases\n| ID | Requirement/AC | Type | Runtime level | Required? |\n|----|----------------|------|---------------|-----------|\n| TC-01 | R01 | Functional | runtime | yes |""")
    
    os.environ["AUTOMIND_WORKSPACE_ROOT"] = str(tmp_path)
    should_trigger, reason = should_trigger_warm_build(task_dir)
    assert not should_trigger
    assert "cannot detect platform" in reason


def test_warm_build_status_initial_empty(tmp_path: Path) -> None:
    """Test warm build status is empty initially."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    
    status = get_warm_build_status(task_dir)
    assert status == {}


def test_warm_build_status_persisted_in_runtime_state(tmp_path: Path) -> None:
    """Test warm build status is persisted in runtime-state.json."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    
    write_runtime_state(task_dir, {
        "status": "ready",
        "nextAction": "run_generator",
        "warmBuild": {"status": "completed", "platform": "ios"},
    })
    
    status = get_warm_build_status(task_dir)
    assert status["status"] == "completed"
    assert status["platform"] == "ios"


def test_is_incremental_build_not_possible_without_warm_build(tmp_path: Path) -> None:
    """Test incremental build is not possible without warm build completion."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    
    write_runtime_state(task_dir, {
        "status": "ready",
        "nextAction": "run_generator",
        "warmBuild": {"status": "failed"},
    })
    
    possible, reason = is_incremental_build_possible(task_dir)
    assert not possible
    assert "warm build not completed" in reason


def test_is_incremental_build_possible_without_structural_changes(tmp_path: Path) -> None:
    """Test incremental build is possible when no structural files changed after warm build."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    os.environ["AUTOMIND_WORKSPACE_ROOT"] = str(tmp_path)
    # Podfile exists but was created before warm build started.
    (tmp_path / "Podfile").write_text("platform :ios")
    
    write_runtime_state(task_dir, {
        "status": "ready",
        "nextAction": "run_generator",
        "warmBuild": {
            "status": "completed",
            "platform": "ios",
            "startedAt": "2099-01-01T00:00:00",
        },
    })
    
    possible, reason = is_incremental_build_possible(task_dir)
    assert possible
    assert "FULL_INCREMENTAL" in reason


def test_is_incremental_build_not_possible_with_structural_changes(tmp_path: Path) -> None:
    """Test incremental build is NOT possible when structural files changed after warm build."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    os.environ["AUTOMIND_WORKSPACE_ROOT"] = str(tmp_path)
    # Podfile modified after warm build started (startedAt in the past).
    (tmp_path / "Podfile").write_text("platform :ios")
    
    write_runtime_state(task_dir, {
        "status": "ready",
        "nextAction": "run_generator",
        "warmBuild": {
            "status": "completed",
            "platform": "ios",
            "startedAt": "2000-01-01T00:00:00",
        },
    })
    
    possible, reason = is_incremental_build_possible(task_dir)
    assert not possible
    assert "STRUCTURAL_CHANGES" in reason


def test_wait_for_warm_build_waits_on_pending(tmp_path: Path) -> None:
    """Test wait_for_warm_build treats pending as an in-flight (waitable) state."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    
    write_runtime_state(task_dir, {
        "status": "ready",
        "nextAction": "run_generator",
        "warmBuild": {"status": "pending", "platform": "ios"},
    })
    
    status = wait_for_warm_build(task_dir, max_wait=1)
    # Pending that never advances should time out, not be ignored.
    assert status["status"] == "timed_out"


def test_wait_for_warm_build_returns_immediately_if_completed(tmp_path: Path) -> None:
    """Test wait_for_warm_build returns immediately if already completed."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    
    write_runtime_state(task_dir, {
        "status": "ready",
        "nextAction": "run_generator",
        "warmBuild": {"status": "completed", "platform": "ios"},
    })
    
    status = wait_for_warm_build(task_dir, max_wait=1)
    assert status["status"] == "completed"


def test_wait_for_warm_build_returns_immediately_if_skipped(tmp_path: Path) -> None:
    """Test wait_for_warm_build returns immediately if skipped."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    
    write_runtime_state(task_dir, {
        "status": "ready",
        "nextAction": "run_generator",
        "warmBuild": {"status": "skipped", "reason": "no runtime testcases"},
    })
    
    status = wait_for_warm_build(task_dir, max_wait=1)
    assert status["status"] == "skipped"


def test_wait_for_warm_build_timeout(tmp_path: Path) -> None:
    """Test wait_for_warm_build times out after max_wait and marks timed_out."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    
    write_runtime_state(task_dir, {
        "status": "ready",
        "nextAction": "run_generator",
        "warmBuild": {"status": "running", "platform": "ios"},
    })
    
    status = wait_for_warm_build(task_dir, max_wait=1)
    assert status["status"] == "timed_out"
    assert status["platform"] == "ios"


def test_start_warm_build_returns_false_if_already_running(tmp_path: Path) -> None:
    """Test start_warm_build returns False if already running."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    
    write_runtime_state(task_dir, {
        "status": "ready",
        "nextAction": "run_generator",
        "warmBuild": {"status": "running"},
    })
    
    result = start_warm_build(task_dir)
    assert not result


def test_start_warm_build_restarts_stale_running_on_resume(tmp_path: Path) -> None:
    """Stale running/pending with no live worker thread (e.g. after a killed
    process on resume) must not block a restart; the guard should fall through
    to should_trigger instead of short-circuiting on the stale status."""
    from orchestrator.warm_build import _warm_build_thread_alive

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    os.environ["AUTOMIND_WORKSPACE_ROOT"] = str(tmp_path)

    # No live worker thread exists for this fresh task.
    assert not _warm_build_thread_alive(task_dir)

    write_runtime_state(task_dir, {
        "status": "ready",
        "nextAction": "run_generator",
        "warmBuild": {"status": "running", "platform": "ios"},
    })

    # With no runtime testcases the restart path resolves to "skipped", proving
    # it passed the stale-status guard rather than returning on status=running.
    result = start_warm_build(task_dir)
    assert not result
    assert get_warm_build_status(task_dir)["status"] == "skipped"
