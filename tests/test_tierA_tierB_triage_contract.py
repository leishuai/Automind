"""Tier A + Tier B model-first triage contract tests (second batch).

Tier A — keyword/text heuristics over user input (orchestrator.main +
orchestrator.reuse). These directly read the user's raw request and are the
most prone to misclassification, so their _detail variants must distinguish
"code_deterministic" confident matches from "requires_model_review" weak
heuristics.

Tier B — failure/log classification (orchestrator.main,
orchestrator.automation_tools, scripts.android_project_probe,
scripts.failure_classifier). Their catch-all fallbacks must surface
needsModelReview=True so the harness reads the real log instead of trusting a
blind default.

Each thin wrapper must still return the legacy scalar/bool/tuple/list so
existing call sites stay green.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Tier A
# --------------------------------------------------------------------------
def test_is_client_task_detail_explicit_client_keyword_is_deterministic() -> None:
    from orchestrator.main import is_client_development_or_verification_task_detail

    detail = is_client_development_or_verification_task_detail("修复 iOS app 的登录页面", "ios")
    assert detail["isClientTask"] is True
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_is_client_task_detail_non_mobile_is_deterministic_false() -> None:
    from orchestrator.main import is_client_development_or_verification_task_detail

    detail = is_client_development_or_verification_task_detail("跑一下数据清洗脚本", "script")
    assert detail["isClientTask"] is False
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_is_client_task_detail_mobile_without_signal_needs_review() -> None:
    from orchestrator.main import is_client_development_or_verification_task_detail

    # ios task type but no client/action keyword at all -> heuristic gap.
    detail = is_client_development_or_verification_task_detail("关于这个东西", "ios")
    assert detail["triageSource"] == "requires_model_review"
    assert detail["needsModelReview"] is True


def test_is_client_task_thin_wrapper_returns_bool() -> None:
    from orchestrator.main import is_client_development_or_verification_task

    assert isinstance(is_client_development_or_verification_task("构建 iOS app", "ios"), bool)


def test_hardstop_device_detail_explicit_pair_is_deterministic() -> None:
    from orchestrator.main import mentions_hardstop_device_unavailable_phrasing_detail

    detail = mentions_hardstop_device_unavailable_phrasing_detail("真机不可用，请走 simulator")
    assert detail["mentionsUnavailable"] is True
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_hardstop_device_detail_anchor_without_pair_needs_review() -> None:
    from orchestrator.main import mentions_hardstop_device_unavailable_phrasing_detail

    # Anchor word present but no clean unavailable pairing — ambiguous negation.
    detail = mentions_hardstop_device_unavailable_phrasing_detail("真机这边有点麻烦")
    assert detail["triageSource"] == "requires_model_review"
    assert detail["needsModelReview"] is True


def test_hardstop_device_detail_no_anchor_is_deterministic_false() -> None:
    from orchestrator.main import mentions_hardstop_device_unavailable_phrasing_detail

    detail = mentions_hardstop_device_unavailable_phrasing_detail("请实现一个排序算法")
    assert detail["mentionsUnavailable"] is False
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_hardstop_device_thin_wrapper_preserves_legacy_contract() -> None:
    from orchestrator.main import mentions_hardstop_device_unavailable_phrasing

    assert mentions_hardstop_device_unavailable_phrasing("真机不可用，请走 simulator") is True
    assert mentions_hardstop_device_unavailable_phrasing("没真机") is True
    assert mentions_hardstop_device_unavailable_phrasing("no real device available") is True
    assert mentions_hardstop_device_unavailable_phrasing("please verify on real device") is False
    assert mentions_hardstop_device_unavailable_phrasing("用真机来跑回归") is False


def test_mobile_target_review_detail_no_keyword_needs_review() -> None:
    from orchestrator.main import mobile_task_needs_verification_target_review_detail

    detail = mobile_task_needs_verification_target_review_detail("修复 iOS app 崩溃", "ios")
    assert detail["needsReview"] is True
    assert detail["triageSource"] == "requires_model_review"
    assert detail["needsModelReview"] is True


def test_mobile_target_review_detail_explicit_target_is_deterministic() -> None:
    from orchestrator.main import mobile_task_needs_verification_target_review_detail

    detail = mobile_task_needs_verification_target_review_detail("在 iOS 模拟器上验证 app 登录", "ios")
    assert detail["needsReview"] is False
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_mobile_target_review_thin_wrapper_returns_bool() -> None:
    from orchestrator.main import mobile_task_needs_verification_target_review

    assert isinstance(mobile_task_needs_verification_target_review("修复 iOS app 崩溃", "ios"), bool)


def test_simulator_only_detail_mixed_signals_needs_review() -> None:
    from orchestrator.main import mobile_verification_mentions_simulator_only_detail

    detail = mobile_verification_mentions_simulator_only_detail(
        "先用模拟器跑通 app，再上真机回归", "ios"
    )
    assert detail["simulatorOnly"] is False
    assert detail["triageSource"] == "requires_model_review"
    assert detail["needsModelReview"] is True


def test_simulator_only_detail_simulator_only_is_deterministic() -> None:
    from orchestrator.main import mobile_verification_mentions_simulator_only_detail

    detail = mobile_verification_mentions_simulator_only_detail("在模拟器上验证 app", "ios")
    assert detail["simulatorOnly"] is True
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_simulator_only_thin_wrapper_returns_bool() -> None:
    from orchestrator.main import mobile_verification_mentions_simulator_only

    assert isinstance(mobile_verification_mentions_simulator_only("在模拟器上验证 app", "ios"), bool)


def test_brainstorm_questions_detail_always_requests_review() -> None:
    from orchestrator.main import detect_brainstorm_questions_detail

    detail = detect_brainstorm_questions_detail("优化一下这个功能")
    assert detail["triageSource"] == "requires_model_review"
    assert detail["needsModelReview"] is True
    assert isinstance(detail["questions"], list)
    assert isinstance(detail["seededReasons"], list)


def test_brainstorm_questions_thin_wrapper_returns_list() -> None:
    from orchestrator.main import detect_brainstorm_questions, detect_brainstorm_questions_detail

    user_input = "优化一下这个功能"
    assert detect_brainstorm_questions(user_input) == detect_brainstorm_questions_detail(user_input)["questions"]


def test_preferred_language_detail_chinese_heavy_is_deterministic() -> None:
    from orchestrator.reuse import detect_preferred_language_detail

    detail = detect_preferred_language_detail("为MediaPlay模块新增埋点并完善异常上报逻辑")
    assert detail["language"] == "zh"
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_preferred_language_detail_no_cjk_is_deterministic_en() -> None:
    from orchestrator.reuse import detect_preferred_language_detail

    detail = detect_preferred_language_detail("please add logging to the parser")
    assert detail["language"] == "en"
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_preferred_language_detail_borderline_needs_review() -> None:
    from orchestrator.reuse import detect_preferred_language_detail

    # A handful of CJK chars next to lots of latin -> borderline.
    detail = detect_preferred_language_detail("add 埋点 to the analytics module and ship it")
    assert detail["triageSource"] == "requires_model_review"
    assert detail["needsModelReview"] is True


def test_preferred_language_thin_wrapper_preserves_legacy_contract() -> None:
    from orchestrator.reuse import detect_preferred_language

    assert detect_preferred_language("为MediaPlay模块新增埋点") == "zh"


# --------------------------------------------------------------------------
# Tier B
# --------------------------------------------------------------------------
def test_agent_failure_detail_known_signal_is_deterministic() -> None:
    from orchestrator.main import classify_agent_execution_failure_detail

    detail = classify_agent_execution_failure_detail("command timed out after 600s")
    assert detail["category"] == "agent_timeout"
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_agent_failure_detail_fallback_needs_review() -> None:
    from orchestrator.main import classify_agent_execution_failure_detail

    detail = classify_agent_execution_failure_detail("some unrecognized garbage output")
    assert detail["category"] == "agent_unavailable"
    assert detail["triageSource"] == "requires_model_review"
    assert detail["needsModelReview"] is True


def test_agent_failure_thin_wrapper_preserves_legacy_strings() -> None:
    from orchestrator.main import classify_agent_execution_failure

    assert classify_agent_execution_failure("ran out of room in the model's context window") == "agent_context_overflow"
    assert classify_agent_execution_failure("nothing matched here") == "agent_unavailable"


def test_android_probe_failure_detail_known_signal_is_deterministic() -> None:
    from orchestrator.main import classify_android_probe_failure_detail

    detail = classify_android_probe_failure_detail("blocked_sensitive overlay detected")
    assert detail["category"] == "permission_blocked"
    assert detail["triageSource"] == "code_deterministic"
    assert detail["needsModelReview"] is False


def test_android_probe_failure_detail_fallback_needs_review() -> None:
    from orchestrator.main import classify_android_probe_failure_detail

    detail = classify_android_probe_failure_detail("some weird unrecognized step error")
    assert detail["category"] == "validation_failure"
    assert detail["triageSource"] == "requires_model_review"
    assert detail["needsModelReview"] is True


def test_android_probe_failure_thin_wrapper_returns_tuple() -> None:
    from orchestrator.main import classify_android_probe_failure

    cat, msg = classify_android_probe_failure("no devices found")
    assert cat == "system_or_external_dependency"
    assert isinstance(msg, str)


def test_setup_failure_known_pattern_is_deterministic() -> None:
    from orchestrator.automation_tools import classify_setup_failure

    diag = classify_setup_failure("ERROR: Could not resolve host: pypi.org")
    assert diag["category"] == "network_or_dns"
    assert diag["triageSource"] == "code_deterministic"
    assert diag["needsModelReview"] is False


def test_setup_failure_unknown_needs_review() -> None:
    from orchestrator.automation_tools import classify_setup_failure

    diag = classify_setup_failure("totally unexpected setup error blob")
    assert diag["category"] == "unknown"
    assert diag["triageSource"] == "requires_model_review"
    assert diag["needsModelReview"] is True


def test_android_classify_build_fallback_needs_review() -> None:
    probe = _load("android_project_probe", "scripts/android_project_probe.py")

    result = probe.classify_build("BUILD FAILED with some obscure error", exit_code=1)
    assert result["category"] == "build_failure"
    assert result["triageSource"] == "requires_model_review"
    assert result["needsModelReview"] is True


def test_android_classify_build_pass_is_deterministic() -> None:
    probe = _load("android_project_probe", "scripts/android_project_probe.py")

    result = probe.classify_build("BUILD SUCCESSFUL", exit_code=0)
    assert result["result"] == "pass"
    assert result["triageSource"] == "code_deterministic"
    assert result["needsModelReview"] is False


def test_failure_classifier_needs_model_review_tracks_triage_source() -> None:
    fc = _load("failure_classifier", "scripts/failure_classifier.py")

    # Unclassified fallback -> needsModelReview True.
    unknown = fc.classify("ios", "build", "obscure error nobody recognises")
    assert unknown.triageSource == "unclassified"
    assert unknown.needsModelReview is True

    # Deterministic signing fast-path -> needsModelReview False.
    signed = fc.classify(
        "ios", "build",
        "Code signing is required for product type 'Application' in SDK 'iOS'\n"
        "Provisioning profile 'XYZ' doesn't include signing certificate\n",
    )
    assert signed.triageSource == "code_fast_path"
    assert signed.needsModelReview is False


def _load(module_name: str, rel_path: str):
    sys.path.insert(0, str(Path("scripts").resolve()))
    spec = importlib.util.spec_from_file_location(module_name, Path(rel_path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
