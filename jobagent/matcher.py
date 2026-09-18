from __future__ import annotations

import re


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
    return score, matched
