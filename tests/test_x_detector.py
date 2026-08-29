"""Tests for X signal detector."""

from __future__ import annotations

from yc_launch_monitor.monitors.x.detector import XSignalDetector


def test_detects_yc_acceptance_language() -> None:
    detector = XSignalDetector()
    result = detector.detect(
        "Thrilled to share that we got into YC S26! We're building @AgentScale to automate enterprise workflows.",
        author_name="Sarah Chen",
        author_username="sarah_founder",
    )

    assert result.is_relevant is True
    assert result.program == "YC"
    assert result.batch == "S26"
    assert result.company_name == "AgentScale"
    assert "YC acceptance pattern" in (result.signal_reason or "") or "YC batch" in (result.signal_reason or "")


def test_detects_speedrun_language() -> None:
    detector = XSignalDetector()
    result = detector.detect(
        "Excited to announce we were accepted into the Speedrun 2024 cohort! Building PixelForge.",
        author_name="Alex Rivera",
        author_username="alex_dev",
    )

    assert result.is_relevant is True
    assert result.program == "Speedrun"
    assert result.batch == "Speedrun 2024"
    assert result.company_name == "PixelForge"


def test_detects_backed_by_y_combinator() -> None:
    detector = XSignalDetector()
    result = detector.detect(
        "We are backed by Y Combinator! Building next-gen database tooling at @DataPulse.",
        author_name="Founder Joe",
    )

    assert result.is_relevant is True
    assert result.program == "YC"
    assert result.company_name == "DataPulse"


def test_ignores_unrelated_casual_mentions() -> None:
    detector = XSignalDetector()
    casual_posts = [
        "Just reading Paul Graham's essay on startups.",
        "Thinking about applying to YC next year, what are the best application tips?",
        "Interesting thoughts on the latest YC batch trends in AI.",
        "We failed the YC interview 3 years ago and survived.",
    ]

    for text in casual_posts:
        result = detector.detect(text)
        assert result.is_relevant is False


def test_extracts_batch_variations() -> None:
    detector = XSignalDetector()

    assert detector._extract_batch("We are in YC W26!") == "W26"
    assert detector._extract_batch("Joining YC S25") == "S25"
    assert detector._extract_batch("Speedrun 2024 batch is wild") == "Speedrun 2024"
