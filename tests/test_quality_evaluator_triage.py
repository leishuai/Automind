"""Tests for scripts/quality_evaluator.py model-first triage contract.

Verifies that classify_crash_timeout_quality exposes triageSource/needsModelReview
on every returned check, and that hard vs. weak signal patterns produce the
correct code_deterministic vs. requires_model_review classifications.
"""
from __future__ import annotations

import sys
from pathlib import Path


def test_quality_checks_always_expose_triage_source_fields(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path("scripts").resolve()))
    from scripts import quality_evaluator as q

    # Hard evidence: stack-like trace + page context in a runtime log.
    hard = (
        "runtime.log\n"
        "Screen: HomePage\n"
        "FATAL EXCEPTION: segfault in com.example.Foo\n"
        "backtrace:\n"
        "  at com.example.Foo.doit(Foo.kt:42)\n"
        "  at com.example.Main.onStart(Main.kt:100)\n"
    )
    checks = q.classify_crash_timeout_quality(hard, tmp_path, tmp_path)
    assert checks, "hard evidence should produce at least one check"
    for c in checks:
        assert "triageSource" in c
        assert "needsModelReview" in c

    # Hard crash case must be marked code_deterministic
    hard_crashes = [c for c in checks if c.get("result") == "fail"]
    assert len(hard_crashes) >= 1
    for c in hard_crashes:
        assert c["triageSource"] == "code_deterministic"
        assert c["needsModelReview"] is False


def test_warn_only_when_stack_or_page_missing() -> None:
    sys.path.insert(0, str(Path("scripts").resolve()))
    from scripts import quality_evaluator as q

    # "crash" mention without stack or page: warning, triage needed.
    soft = "syslog: some-service reported crash-like condition (no stack, no page)\n"
    checks = q.classify_crash_timeout_quality(soft, tmp := Path("."), tmp)
    assert any(c["triageSource"] == "requires_model_review" for c in checks), checks
    assert any(c["needsModelReview"] is True for c in checks), checks


def test_timeout_signal_falls_under_review_when_not_product_level() -> None:
    sys.path.insert(0, str(Path("scripts").resolve()))
    from scripts import quality_evaluator as q

    # Generic "timed out" without product-level wording — not a product hang.
    text = "verifier command: step timed out after 30s\n"
    checks = q.classify_crash_timeout_quality(text, tmp := Path("."), tmp)
    assert checks, "timeout should surface at least one check"
    assert any(c["triageSource"] == "requires_model_review" for c in checks), checks


def test_no_false_positives_for_unrelated_text() -> None:
    sys.path.insert(0, str(Path("scripts").resolve()))
    from scripts import quality_evaluator as q

    unrelated = (
        "User tapped SignIn.\n"
        "Navigation to /home succeeded.\n"
        "Test case TC-F01 passed.\n"
    )
    checks = q.classify_crash_timeout_quality(unrelated, tmp := Path("."), tmp)
    assert checks == [], f"unrelated text should produce zero checks, got {checks}"
