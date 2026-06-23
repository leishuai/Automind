from __future__ import annotations

from orchestrator.main import script_command_no_screenshot_reason


def test_script_command_adds_no_screenshot_reason_for_non_ui_runtime_tc() -> None:
    reason = script_command_no_screenshot_reason({
        "id": "TC-F01",
        "type": "Functional",
        "runtimeLevel": "runtime",
        "preconditions": "python3 available",
        "command": "python3 -m pytest",
        "steps": "run command and assert exit code/stdout",
        "expectedEvidence": "commands.md, env.json, script-command.log",
    })

    assert reason
    assert "non-UI" in reason
    assert "exit code" in reason


def test_script_command_keeps_screenshot_gate_for_ui_runtime_tc() -> None:
    reason = script_command_no_screenshot_reason({
        "id": "TC-F01",
        "type": "Functional App/UI",
        "runtimeLevel": "runtime",
        "preconditions": "browser available",
        "command": "npm run e2e",
        "steps": "launch page, click target, assert visible state",
        "expectedEvidence": "screenshot, trace, logs",
    })

    assert reason is None
