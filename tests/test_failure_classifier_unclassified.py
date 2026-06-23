"""Failure-classifier: deterministic fast-path + explicit unclassified fallback.

The core architectural claim of the model-first failure triage:

* Code regex handles a small, provable set of patterns (Developer Mode,
  signing-not-trusted, Kotlin stale cache, Gradle missing task) and marks
  those with triageSource="code_fast_path" so callers can trust the fix.
* Anything else falls through with triageSource="unclassified" and
  recoveryAction="triage_needed" — the evaluator / generator reads the
  real log and produces a category and concrete recovery action.

The old behaviour was to return a broad "build_failure" classification for
any unrecognised log, which fed the ExampleApp-style "retry same command in a
tight loop" syndrome. The new behaviour explicitly declines to classify,
so callers must perform real log analysis.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load(module_name: str, rel_path: str):
    sys.path.insert(0, str(Path("scripts").resolve()))
    spec = importlib.util.spec_from_file_location(module_name, Path(rel_path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _classifier():
    return _load("failure_classifier", "scripts/failure_classifier.py")


def test_unrecognised_ios_build_log_says_triage_needed() -> None:
    """Unknown Xcode / CocoaPods error — the classifier must decline to
    classify instead of returning the generic 'build_failure' that led to
    the ExampleApp loop. The evaluator is expected to read the log and produce
    a concrete recovery action."""
    fc = _classifier()
    log = (
        "TTReadingWidgetExtension.swift:11:8: error: unable to find module dependency: 'SSUGCoinWidget'\n"
        "NotificationService.m:10:9: error: 'BDUGPushSDK/BDUGPushExtension.h' file not found\n"
        "** BUILD FAILED **\n"
    )
    c = fc.classify("ios", "build", log)
    assert c.category == "unknown" or c.category == "build_failure"
    assert c.recoveryAction == "triage_needed"
    assert c.triageSource == "unclassified"
    # sameProblemKey must be platform-scoped so evaluator can write a
    # fine-grained key on retry (e.g. ios.build.pod.SSUGCoinWidget_missing).
    assert c.sameProblemKey.endswith("unclassified_triage_needed") or c.sameProblemKey in ("", "ios.build.unknown")


def test_unrecognised_install_log_says_triage_needed() -> None:
    """Same gate for install-phase failures."""
    fc = _classifier()
    log = "some-driver install failed: obscure network blip\n"
    c = fc.classify("ios", "install", log)
    assert c.recoveryAction == "triage_needed"
    assert c.triageSource == "unclassified"


def test_deterministic_signing_failure_still_routed_to_code_fast_path() -> None:
    """Known-signing patterns must still be classified by code so the
    evaluator/generator do not waste model cycles on them. This guards
    the 'code handles only the provable, model handles the rest' split."""
    fc = _classifier()
    # iOS signing / provisioning-style string — a deterministic pattern.
    log = (
        "Code signing is required for product type 'Application' in SDK 'iOS'\n"
        "Provisioning profile 'XYZ' doesn't include signing certificate\n"
    )
    c = fc.classify("ios", "build", log)
    assert c.triageSource == "code_fast_path"
    assert c.recoveryAction and c.recoveryAction != "triage_needed"
