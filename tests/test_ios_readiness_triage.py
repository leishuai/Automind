"""Tests for scripts/ios_readiness_analyzer.py model-first triage contract.

Verifies that classify_detail exposes triageSource/needsModelReview and that
classify (the 3-tuple wrapper) remains backward-compatible with external callers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def test_classify_detail_exposes_triage_source_for_every_outcome() -> None:
    sys.path.insert(0, str(Path("scripts").resolve()))
    from scripts import ios_readiness_analyzer as analyzer

    cases = [
        ("Welcome to ExampleApp — tap Start to begin.", "pass"),
        ("Loading...", "in_progress"),
        ("Please Sign in with your Apple ID 登录", "blocked"),
        ("Would Like to Send You Notifications — Don't Allow  Allow", "blocked"),
        ("个人信息保护 用户协议 同意 不同意", "blocked"),
        ("", "blocked"),
    ]
    for text, expected_result in cases:
        detail = analyzer.classify_detail(text)
        assert "result" in detail
        assert "category" in detail
        assert "matchedKeywords" in detail
        assert "triageSource" in detail
        assert "needsModelReview" in detail
        assert detail["result"] == expected_result, f"text={text!r}"


def test_classify_detail_requires_model_review_for_unrecognized_ocr_text() -> None:
    sys.path.insert(0, str(Path("scripts").resolve()))
    from scripts import ios_readiness_analyzer as analyzer

    detail = analyzer.classify_detail("Welcome to ExampleApp — tap Start to begin.")
    assert detail["result"] == "pass"
    assert detail["triageSource"] == "requires_model_review"
    assert detail["needsModelReview"] is True


def test_classify_detail_code_deterministic_for_privacy_permission_login_or_loading() -> None:
    sys.path.insert(0, str(Path("scripts").resolve()))
    from scripts import ios_readiness_analyzer as analyzer

    texts = [
        "个人信息保护 用户协议 同意 不同意",
        "Would Like to Send You Notifications — Don't Allow  Allow",
        "登录 手机号 验证码",
        "Loading...",
    ]
    for text in texts:
        detail = analyzer.classify_detail(text)
        assert detail["triageSource"] == "code_deterministic", text
        assert detail["needsModelReview"] is False


def test_classify_legacy_3_tuple_wrapper_still_works() -> None:
    sys.path.insert(0, str(Path("scripts").resolve()))
    from scripts import ios_readiness_analyzer as analyzer

    # Backward-compatible shape for monkeypatched callers.
    result, category, hits = analyzer.classify("")
    assert isinstance(result, str)
    assert isinstance(category, str)
    assert isinstance(hits, list)

    result, category, hits = analyzer.classify("Loading...")
    assert result == "in_progress"
    assert category == "loading_state"
    assert "Loading" in hits
