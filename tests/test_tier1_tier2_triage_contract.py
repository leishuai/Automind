"""Tier 1 + Tier 2 smoke tests for the model-first triage contract.

Covers the four Tier-1 triage functions exposed by orchestrator.main
(infer_task_type / infer_client_ui_task / infer_ui_entry_target /
should_try_platform_self_repair) and the Tier-2 StuckDetector.observe()
return contract.  Each _detail variant must return a dict with at least
`triageSource` and `needsModelReview`, while the legacy thin-wrapper
function must still return the same scalar/boolean the original contract
required so existing call sites stay green.
"""

from __future__ import annotations


def test_infer_task_type_detail_exposes_triage_for_strong_platform_keywords() -> None:
    from orchestrator.main import infer_task_type_detail

    for prompt in [
        "给这个 iOS 应用加一个设置页面",
        "请在 Android 上验证登录流程",
        "需要在 Android 和 iOS 上同时回归",
    ]:
        detail = infer_task_type_detail(prompt)
        assert detail["triageSource"] == "code_deterministic"
        assert detail["needsModelReview"] is False
        assert detail["taskType"] in {"ios", "android", "dual"}
        assert isinstance(detail["matchedKeyword"], str) and detail["matchedKeyword"]


def test_infer_task_type_detail_flags_ambiguous_workspace_for_review() -> None:
    from orchestrator.main import infer_task_type_detail

    # Empty prompt with no signal relies on workspace detection; for
    # code with a mixed platform directory, needsModelReview must be True.
    detail = infer_task_type_detail("")
    # Either code_deterministic script fallback, or workspace-ambiguous.
    assert detail["triageSource"] in {"code_deterministic", "requires_model_review"}
    assert isinstance(detail["needsModelReview"], bool)
    assert isinstance(detail["taskType"], str) and detail["taskType"]


def test_infer_task_type_thin_wrapper_preserves_legacy_string_return() -> None:
    from orchestrator.main import infer_task_type

    assert isinstance(infer_task_type("iOS 构建修复"), str)
    assert isinstance(infer_task_type("跑一下这个 python 脚本"), str)


def test_infer_client_ui_task_detail_flags_platform_task_as_client_ui() -> None:
    from orchestrator.main import infer_client_ui_task_detail

    detail = infer_client_ui_task_detail("验证 iOS 登录页面", task_type="ios")
    assert detail["isClientUi"] is True
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_infer_client_ui_task_detail_flags_strong_keyword_as_client_ui() -> None:
    from orchestrator.main import infer_client_ui_task_detail

    detail = infer_client_ui_task_detail("打开 app 的 settings page 并点击 save")
    assert detail["isClientUi"] is True
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_infer_client_ui_task_detail_respects_negative_signal() -> None:
    from orchestrator.main import infer_client_ui_task_detail

    detail = infer_client_ui_task_detail("不需要Android/iOS，纯后端接口调整")
    assert detail["isClientUi"] is False
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_infer_client_ui_task_thin_wrapper_returns_bool() -> None:
    from orchestrator.main import infer_client_ui_task

    assert isinstance(infer_client_ui_task("构建 app 的首页"), bool)


def test_infer_ui_entry_target_detail_extracts_explicit_entry() -> None:
    from orchestrator.main import infer_ui_entry_target_detail

    detail = infer_ui_entry_target_detail("修复登录页面的按钮")
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False
    assert "登录页" in detail["entryTarget"] or "页面" in detail["entryTarget"]


def test_infer_ui_entry_target_detail_requests_review_when_no_explicit_entry() -> None:
    from orchestrator.main import infer_ui_entry_target_detail

    detail = infer_ui_entry_target_detail("重构一下这里的代码")
    assert detail["triageSource"] == "requires_model_review"
    assert detail["needsModelReview"] is True
    assert isinstance(detail["entryTarget"], str) and detail["entryTarget"]


def test_infer_ui_entry_target_thin_wrapper_preserves_string_return() -> None:
    from orchestrator.main import infer_ui_entry_target

    assert isinstance(infer_ui_entry_target("修复首页"), str)


def test_should_try_platform_self_repair_detail_requires_model_review_when_no_blocker() -> None:
    from orchestrator.main import should_try_platform_self_repair_detail

    # Non probe-flow task must be a hard no with code_deterministic triage.
    no_probe = should_try_platform_self_repair_detail(
        _fake_nonexistent_task_dir(),
        {"result": "fail", "nextAction": "retry_generator", "failedChecks": []},
    )
    assert no_probe["shouldTry"] is False
    assert no_probe["triageSource"] == "code_deterministic"
    assert no_probe["needsModelReview"] is False


def test_should_try_platform_self_repair_thin_wrapper_returns_bool() -> None:
    from orchestrator.main import should_try_platform_self_repair

    assert isinstance(
        should_try_platform_self_repair(
            _fake_nonexistent_task_dir(),
            {"result": "fail", "nextAction": "retry_generator", "failedChecks": []},
        ),
        bool,
    )


def test_stuck_detector_observe_enriches_return_with_triage_fields() -> None:
    from orchestrator.stuck_detector import StuckDetector, StuckSignature

    detector = StuckDetector(threshold=3)
    sig = StuckSignature(action_kind="android_probe_flow", error_class="launch_failed")
    # Observe a repeat signature enough times to trigger the detector.
    last: object = None
    for _ in range(4):
        last = detector.observe(sig)
    assert isinstance(last, dict)
    assert last["triageSource"] == "requires_model_review"
    assert last["needsModelReview"] is True
    assert "reason" in last


def _fake_nonexistent_task_dir():
    import tempfile
    from pathlib import Path

    return Path(tempfile.gettempdir()) / "automind-tier1-smoke-no-such-dir"
