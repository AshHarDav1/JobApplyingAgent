from __future__ import annotations

import re

MIDDLE_RE = re.compile(
    r"middle\+|middle\s*\+|mid-level|mid level|\bmiddle\b|\bmid\b|мидл|миддл",
    re.IGNORECASE,
)
JUNIOR_RE = re.compile(r"\bjunior\b|\bjr\b|джун", re.IGNORECASE)
SENIOR_RE = re.compile(
    r"\bsenior\b|\bsr\b|сеньор|синьор|\blead\b|principal|staff engineer|head of|ведущий",
    re.IGNORECASE,
)


def seniority_bonus(text: str) -> tuple[int, list[str]]:
    """Middle first, junior next, senior visible but lower."""
    haystack = text or ""
    if MIDDLE_RE.search(haystack):
        return 4, ["middle"]
    if JUNIOR_RE.search(haystack):
        return 1, ["junior"]
    if SENIOR_RE.search(haystack):
        return 0, ["senior"]
    return 0, []


def score_text(text: str, keywords: list[str], location_keywords: list[str]) -> tuple[int, list[str]]:
    haystack = text.lower()
    matched: list[str] = []
    score = 0
    for word in keywords:
        if not word:
            continue
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", haystack):
            matched.append(word)
            score += 2
    for word in location_keywords:
        if not word:
            continue
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", haystack):
            matched.append(word)
            score += 1
    bonus, labels = seniority_bonus(text)
    score += bonus
    matched.extend(labels)
    return score, matched
