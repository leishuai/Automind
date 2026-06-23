"""P1 模块的 triage 契约统一测试。

验证 orchestrator.classification、orchestrator.loop_decision 和
scripts/quality_evaluator 三个模块均暴露 triageSource + needsModelReview
字段，并且确定性分类与需模型审查分类之间有明确边界。
"""
from __future__ import annotations

import sys
import pathlib


def test_classification_triage_exposes_decision_boundary() -> None:
    from orchestrator.classification import classify_mobile_signal

    cases = {
        "explicit_disable": (
            "不需要Android/iOS，纯后端修改",
            {"triageSource": "code_deterministic", "needsModelReview": False, "explicitlyDisabled": True},
        ),
        "explicit_disable_english": (
            "This task avoids mobile devices, focusing only on backend API endpoints.",
            {"triageSource": "code_deterministic", "needsModelReview": False, "explicitlyDisabled": True},
        ),
        "explicit_enable_with_intent": (
            "在真机上测试iOS应用，确保登录流程正常",
            {"triageSource": "code_deterministic", "needsModelReview": False, "explicitlyEnabled": True},
        ),
        "ambiguous_ui_only_mention": (
            "修复登录页面的UI bug，确保布局正确",
            {"triageSource": "requires_model_review", "needsModelReview": True},
        ),
        "plain_backend_fix": (
            "优化数据库查询性能",
            {"triageSource": "requires_model_review", "needsModelReview": True},
        ),
        "empty_text": ("", {"triageSource": "requires_model_review", "needsModelReview": True}),
    }
    for label, (text, expected) in cases.items():
        result = classify_mobile_signal(text)
        for key, expected_value in expected.items():
            assert result.get(key) == expected_value, (
                f"{label}: expected {key}={expected_value!r}, got {result.get(key)!r}\n"
                f"full result: {result}"
            )
        assert "matchedPhrases" in result
        # result is always a dict
        assert isinstance(result, dict)


def test_loop_decision_triage_maps_reason_sets_to_certainty() -> None:
    from orchestrator.loop_decision import classify_loop_exit

    recoverable = ["dependency_check_warning", "agent_unavailable", "network_timeout", "probe_flow_failure"]
    for reason in recoverable:
        decision = classify_loop_exit(reason)
        assert decision.classification == "recoverable"
        assert decision.should_continue is True
        assert decision.triageSource == "code_deterministic"
        assert decision.needsModelReview is False

    unrecoverable = ["completion_succeeded", "iteration_limit_exhausted", "user_blocked"]
    for reason in unrecoverable:
        decision = classify_loop_exit(reason)
        assert decision.classification == "unrecoverable"
        assert decision.should_continue is False
        assert decision.triageSource == "code_deterministic"
        assert decision.needsModelReview is False

    unknown_reasons = ["some_new_reason", "", "weird_provider_timeout_never_seen"]
    for reason in unknown_reasons:
        decision = classify_loop_exit(reason)
        assert decision.classification == "unknown"
        assert decision.should_continue is False  # fail-closed by default
        assert decision.triageSource == "requires_model_review"
        assert decision.needsModelReview is True

    # exception paths: KeyboardInterrupt and SystemExit
    ki = classify_loop_exit("ignored", exception=KeyboardInterrupt())
    assert ki.classification == "unrecoverable"
    assert ki.interrupted_by_user is True
    assert ki.triageSource == "code_deterministic"

    se = classify_loop_exit("ignored", exception=SystemExit(1))
    assert se.classification == "unrecoverable"
    assert se.triageSource == "code_deterministic"


def test_loop_decision_as_dict_roundtrip_includes_triage_fields() -> None:
    from orchestrator.loop_decision import classify_loop_exit

    for reason in ["agent_unavailable", "something_new"]:
        d = classify_loop_exit(reason)
        payload = d.as_dict()
        assert "triageSource" in payload
        assert "needsModelReview" in payload
        assert payload["triageSource"] == d.triageSource
        assert payload["needsModelReview"] == d.needsModelReview


def test_quality_evaluator_every_check_has_triage_source(tmp_path: pathlib.Path) -> None:
    sys.path.insert(0, str(pathlib.Path("scripts").resolve()))
    from scripts import quality_evaluator as qe

    text = (
        "Screen: HomePage loading stuck infinite loading\n"
        "Stack trace: at com.example.Foo.doIt(Foo.java:123)\n"
        "Thread 0 crashed — segmentation fault\n"
        "some operation timed out after 30s\n"
        "retry attempt 3\n"
        "network request slow — 15000 ms duration\n"
    )
    # Prepare a fake logs dir to get duration_ms extraction working.
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    checks, _meta = qe.quality_checks(tmp_path, tmp_path, log_dir)
    # Must produce at least 2 checks — a duration check and a crash/timeout
    # or stuck-loading check — this ensures the test fixture is real.
    assert len(checks) >= 2, f"expected >=2 checks, got: {[c.get('id') for c in checks]}"
    for check in checks:
        assert "triageSource" in check, (
            f"check id={check.get('id')!r} missing triageSource; keys={list(check)}"
        )
        assert "needsModelReview" in check, (
            f"check id={check.get('id')!r} missing needsModelReview"
        )
        # Invariant: code_deterministic checks must NOT flip needsModelReview=True.
        if check["triageSource"] == "code_deterministic":
            assert check["needsModelReview"] is False, (
                f"code_deterministic check id={check.get('id')!r} had needsModelReview=True"
            )
        else:
            assert check["triageSource"] == "requires_model_review"
            assert check["needsModelReview"] is True


def test_quality_evaluator_structure_triage_follows_result_severity() -> None:
    """Hard-fail results (stuck_loading/crash-with-stack) must be code_deterministic
    because their patterns are strong. Heuristic warn results must be requires_model_review."""
    sys.path.insert(0, str(pathlib.Path("scripts").resolve()))
    from scripts import quality_evaluator as qe

    checks = qe.classify_crash_timeout_quality(
        "app loading stuck loading forever\nScreen: HomePage page loading page",
        pathlib.Path("/tmp"),
        pathlib.Path("/tmp"),
    )
    hard = [c for c in checks if c["result"] == "fail"]
    # A hard crash/timeout result must be code-deterministic; it's already gated.
    for c in hard:
        assert c["triageSource"] == "code_deterministic", f"hard fail check triage mismatch: {c}"

    # Heuristic warnings must surface "needs model review" to the Evaluator.
    soft = [c for c in checks if c["result"] == "warn"]
    for c in soft:
        assert c["triageSource"] == "requires_model_review", f"soft check triage mismatch: {c}"
