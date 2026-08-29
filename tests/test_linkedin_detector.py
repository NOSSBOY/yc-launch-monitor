"""Tests for LinkedIn signal detector."""

from __future__ import annotations

from yc_launch_monitor.monitors.linkedin.detector import LinkedInSignalDetector


def test_detects_yc_acceptance_language() -> None:
    detector = LinkedInSignalDetector()
    result = detector.detect(
        "Beyond excited to share that we got into YC S26! We are building AgentScale to revolutionize enterprise workflows.",
        author_name="Elena Rostova",
        author_company="AgentScale",
    )

    assert result.is_relevant is True
    assert result.program == "YC"
    assert result.batch == "S26"
    assert result.company_name == "AgentScale"
    assert "YC acceptance pattern" in (result.signal_reason or "") or "YC batch" in (result.signal_reason or "")


def test_detects_speedrun_language() -> None:
    detector = LinkedInSignalDetector()
    result = detector.detect(
        "Thrilled to announce that our startup was accepted into Speedrun Winter 2024! Building HyperForge.",
        author_name="Marcus Vance",
        author_company="HyperForge",
    )

    assert result.is_relevant is True
    assert result.program == "Speedrun"
    assert result.batch == "Speedrun Winter 2024"
    assert result.company_name == "HyperForge"


def test_detects_backed_by_y_combinator() -> None:
    detector = LinkedInSignalDetector()
    result = detector.detect(
        "We are backed by Y Combinator! Building next-gen database infrastructure at DataPulse.",
        author_name="Joe Founder",
    )

    assert result.is_relevant is True
    assert result.program == "YC"
    assert result.company_name == "DataPulse"


def test_ignores_unrelated_casual_mentions() -> None:
    detector = LinkedInSignalDetector()
    casual_posts = [
        "Just finished reading Paul Graham's essay on startup moats.",
        "Thinking about applying to YC next year. What are the best application tips?",
        "We failed the YC interview 3 years ago and here is what we learned.",
        "Interested in working at a YC startup in San Francisco.",
    ]

    for text in casual_posts:
        result = detector.detect(text)
        assert result.is_relevant is False


def test_extracts_batch_variations() -> None:
    detector = LinkedInSignalDetector()

    assert detector._extract_batch("We are in YC W27!") == "W27"
    assert detector._extract_batch("Joining YC S26 batch") == "S26"
    assert detector._extract_batch("Speedrun Winter 2024 cohort is amazing") == "Speedrun Winter 2024"
