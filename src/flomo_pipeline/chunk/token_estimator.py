from __future__ import annotations

import math
import re


WORD_RE = re.compile(r"\S+")


def estimate_tokens(text: str) -> int:
    """Deterministic v1 heuristic.

    - word-based estimate for whitespace-separated text: ceil(words * 1.3)
    - mixed-language fallback: ceil(char_count / 4)
    - use the larger number to avoid undersizing chunks too aggressively
    """

    if not text:
        return 0

    word_count = len(WORD_RE.findall(text))
    word_estimate = math.ceil(word_count * 1.3)
    char_estimate = math.ceil(len(text) / 4)
    return max(word_estimate, char_estimate, 1)
