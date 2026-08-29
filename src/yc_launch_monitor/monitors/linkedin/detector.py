"""Signal detector for identifying YC and Speedrun launch/acceptance signals in LinkedIn posts."""

from __future__ import annotations

import re
from dataclasses import dataclass

YC_ACCEPTANCE_PATTERNS = [
    r"\b(?:we\s+)?got\s+into\s+yc\b",
    r"\baccepted\s+(?:into|to)\s+yc\b",
    r"\baccepted\s+(?:into|to)\s+y\s*combinator\b",
    r"\b(?:we\s+)?got\s+into\s+y\s*combinator\b",
    r"\bbacked\s+by\s+y\s*combinator\b",
    r"\bfunded\s+by\s+y\s*combinator\b",
    r"\bjoining\s+(?:the\s+)?yc\b",
    r"\bwe(?:'re|\s+are)\s+in\s+yc\b",
    r"\bpart\s+of\s+(?:the\s+)?yc\b",
    r"\bin\s+the\s+next\s+yc\s+batch\b",
    r"\blaunching\s+in\s+yc\b",
    r"\blaunching\s+on\s+yc\b",
    r"\bour\s+yc\s+launch\b",
    r"\bexcited\s+to\s+announce.*?\byc\b",
    r"\bthrilled\s+to\s+(?:announce|share).*?\byc\b",
    r"\bproud\s+to\s+(?:announce|share).*?\byc\b",
    r"\b(?:in|part of|joined|accepted to|accepted into|our)\s+(?:the\s+)?yc\s+batch\b",
]

SPEEDRUN_PATTERNS = [
    r"\baccepted\s+(?:into|to)\s+speedrun\b",
    r"\b(?:we\s+)?got\s+into\s+speedrun\b",
    r"\bjoining\s+(?:the\s+)?speedrun\b",
    r"\bpart\s+of\s+(?:the\s+)?speedrun\b",
    r"\bspeedrun\s+(?:batch|cohort|program|accelerator)\b",
    r"\bspeedrun\s+(?:winter|summer|spring|fall)\s+20\d{2}\b",
    r"\bsr\d{2}\s+(?:batch|cohort)\b",
]

# Patterns that indicate purely commentary / educational / applicant advice / casual mentions rather than an acceptance signal
EXCLUSION_PATTERNS = [
    r"\bapplying\s+to\s+yc\b",
    r"\bapplied\s+to\s+yc\b",
    r"\bapplication\s+(?:tips|advice|guide|process)\b",
    r"\breading\s+paul\s+graham\b",
    r"\bpaul\s+graham['’]?s\s+essay\b",
    r"\bfailed\s+yc\s+interview\b",
    r"\brejected\s+by\s+yc\b",
    r"\bshould\s+i\s+apply\s+to\s+yc\b",
    r"\bthinking\s+about\s+applying\s+to\s+yc\b",
    r"\bworking\s+at\s+a\s+yc\s+startup\b",
    r"\blooking\s+to\s+hire.*?\byc\b",
]


@dataclass(frozen=True, slots=True)
class LinkedInDetectionResult:
    """Outcome of analyzing LinkedIn post text for YC/Speedrun signals."""

    is_relevant: bool
    program: str = "YC"
    batch: str | None = None
    company_name: str | None = None
    signal_reason: str | None = None
    confidence_score: float = 0.0


class LinkedInSignalDetector:
    """Analyzes text and author metadata from LinkedIn posts to detect founder acceptance/launch announcements."""

    def detect(
        self,
        text: str,
        author_name: str | None = None,
        author_company: str | None = None,
    ) -> LinkedInDetectionResult:
        """Evaluate if the LinkedIn post contains an actionable YC or Speedrun signal."""
        clean_text = text.strip()
        if not clean_text:
            return LinkedInDetectionResult(is_relevant=False)

        lower_text = clean_text.lower()

        # Step 1: Check exclusions (casual commentary, applicant questions, rejections)
        for excl_pattern in EXCLUSION_PATTERNS:
            if re.search(excl_pattern, lower_text):
                # Verify whether there is an explicit acceptance override
                has_explicit_acceptance = any(
                    re.search(p, lower_text)
                    for p in (r"\bgot into yc\b", r"\baccepted into yc\b", r"\baccepted to yc\b")
                )
                if not has_explicit_acceptance:
                    return LinkedInDetectionResult(
                        is_relevant=False, signal_reason="Matched exclusion pattern"
                    )

        # Step 2: Check Speedrun acceptance / launch signals
        is_speedrun = False
        matched_reason = None
        for pattern in SPEEDRUN_PATTERNS:
            match = re.search(pattern, lower_text)
            if match:
                is_speedrun = True
                matched_reason = f"Matched Speedrun pattern: '{match.group(0)}'"
                break

        # Step 3: Check YC acceptance / launch signals
        is_yc = False
        if not is_speedrun:
            for pattern in YC_ACCEPTANCE_PATTERNS:
                match = re.search(pattern, lower_text)
                if match:
                    is_yc = True
                    matched_reason = f"Matched YC acceptance pattern: '{match.group(0)}'"
                    break

        # Step 4: Check explicit batch mention (e.g. "YC S26", "YC W27", "Speedrun Fall 2024")
        batch = self._extract_batch(clean_text)
        if not (is_yc or is_speedrun) and batch:
            if "yc" in lower_text:
                is_yc = True
                matched_reason = f"Explicit YC batch pattern detected: {batch}"
            elif "speedrun" in lower_text:
                is_speedrun = True
                matched_reason = f"Explicit Speedrun batch pattern detected: {batch}"

        if not (is_yc or is_speedrun):
            return LinkedInDetectionResult(is_relevant=False)

        program = "Speedrun" if is_speedrun else "YC"
        company_name = self._extract_company_name(clean_text, author_name, author_company)

        return LinkedInDetectionResult(
            is_relevant=True,
            program=program,
            batch=batch,
            company_name=company_name,
            signal_reason=matched_reason,
            confidence_score=0.9 if batch else 0.8,
        )

    def _extract_batch(self, text: str) -> str | None:
        # Check Speedrun batches
        speedrun_matches = [
            r"\bSpeedrun\s+(?:cohort|batch)?\s*([SWF]\d{2}|20\d{2}|\d{2})\b",
            r"\bSpeedrun\s+(Winter|Summer|Spring|Fall)\s*(20\d{2}|\d{2})\b",
            r"\b(Winter|Summer|Spring|Fall)\s*(?:20\d{2}|\d{2})\s+Speedrun\b",
        ]
        for pattern in speedrun_matches:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = [g for g in match.groups() if g]
                if len(groups) == 1:
                    return f"Speedrun {groups[0].strip()}"
                elif len(groups) == 2:
                    return f"Speedrun {groups[0]} {groups[1]}".strip()

        # Check YC batches
        yc_matches = [
            r"\bYC\s*([SWF]\d{2})\b",
            r"\bYC\s*(Winter|Summer|Fall|Spring)\s*(20\d{2}|\d{2})\b",
            r"\b(Winter|Summer|Fall|Spring)\s*(?:20\d{2}|\d{2})\s*YC\b",
        ]
        for pattern in yc_matches:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = [g for g in match.groups() if g]
                if len(groups) == 1:
                    val = groups[0].strip()
                    return val if val.startswith(("S", "W", "F")) else f"YC {val}"
                elif len(groups) == 2:
                    return f"{groups[0]} {groups[1]}".strip()

        return None

    def _extract_company_name(
        self,
        text: str,
        author_name: str | None = None,
        author_company: str | None = None,
    ) -> str | None:
        if author_company and author_company.strip():
            clean_company = author_company.strip()
            if clean_company.lower() not in (
                "y combinator", "yc", "speedrun", "self-employed", "stealth", "founder", "freelance"
            ):
                return clean_company

        stop_words = {
            "something", "our", "the", "a", "an", "stealth", "ai", "software", "tech",
            "next-gen", "database", "infra", "tooling", "app", "platform", "product",
            "startup", "company", "team", "tools", "automation", "workflows", "agents",
            "new", "modern", "open-source", "yc", "speedrun", "cohort", "batch"
        }

        # Look for company mentions following founder verbs
        name_patterns = [
            r"(?:building|founded|co-founder of|founder of|creator of|we at|team at|at)\s+@?([A-Za-z0-9_\.\-]+)",
            r"(?:our\s+(?:startup|company|product|team))\s+(?:called\s+|is\s+)?@?([A-Za-z0-9_\.\-]+)",
            r"@?([A-Za-z0-9_\.\-]+)\s+is\s+(?:accepted|joining|in)\s+yc",
        ]
        for pattern in name_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                candidate = match.group(1).strip().rstrip(".,!?:")
                if (
                    candidate.lower() not in stop_words
                    and "-" not in candidate
                    and len(candidate) > 1
                ):
                    return candidate

        # Author name if it looks like an entity or display name fallback
        if author_name and any(
            term in author_name.lower() for term in ("ai", "labs", "hq", "app", "tech", "io")
        ):
            return author_name.strip()

        return author_name or None

