"""Similarity checking module for post deduplication.

Uses local text similarity algorithms (no external API) to detect
posts that are too similar to previous ones. Threshold: 0.7 (configurable).

Algorithm:
    1. Character-level Jaccard coefficient (bigrams)  - weight 0.2
    2. Word-level Jaccard coefficient                  - weight 0.5
    3. Keyphrase overlap rate                          - weight 0.3
    4. Weighted average of the three

Additional checks:
    - Opening line similarity (stricter threshold for spam detection)
    - Structural fingerprint (line count, question marks, bullets, emoji)
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Weights for the three similarity components
_W_CHAR = 0.2
_W_WORD = 0.5
_W_KEYPHRASE = 0.3

# Default similarity threshold
DEFAULT_THRESHOLD = 0.70

# Number of past posts to check against
MAX_HISTORY = 100

# Minimum keyphrase length (characters)
_MIN_KEYPHRASE_LEN = 4


class SimilarityChecker:
    """Check new posts against posting history for excessive similarity.

    Threshold: >= 0.7 -> reject (configurable via constructor).
    """

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self._threshold = threshold

    def check(self, new_text: str, history: list[str]) -> tuple[bool, float]:
        """Check if new_text is too similar to any post in history.

        Args:
            new_text: The candidate post text.
            history: List of past post texts (most recent first).

        Returns:
            (is_similar, max_similarity) where is_similar is True if the
            max similarity to any history post >= threshold.
        """
        if not history or not new_text.strip():
            return False, 0.0

        recent = history[:MAX_HISTORY]
        max_sim = 0.0

        for past_text in recent:
            if not past_text.strip():
                continue
            sim = self._compute_similarity(new_text, past_text)
            if sim > max_sim:
                max_sim = sim

        is_similar = max_sim >= self._threshold
        if is_similar:
            logger.warning(
                "Post rejected: similarity %.3f >= threshold %.2f",
                max_sim,
                self._threshold,
            )
        else:
            logger.debug("Similarity check passed: max=%.3f", max_sim)

        return is_similar, max_sim

    def check_opening(self, new_text: str, history: list[str]) -> tuple[bool, float]:
        """Check if the opening line is too similar to recent posts.

        Threads spam detection is sensitive to opening line patterns,
        so the first line is compared separately with a stricter threshold (0.50).

        Args:
            new_text: The candidate post text.
            history: List of past post texts (most recent first).

        Returns:
            (is_similar, max_similarity) for the opening line.
        """
        opening_threshold = 0.50
        recent_count = 30

        new_opening = self._extract_opening(new_text)
        if not new_opening:
            return False, 0.0

        recent = history[:recent_count]
        max_sim = 0.0

        for past_text in recent:
            past_opening = self._extract_opening(past_text)
            if not past_opening:
                continue
            sim = self._compute_similarity(new_opening, past_opening)
            if sim > max_sim:
                max_sim = sim

        is_similar = max_sim >= opening_threshold
        if is_similar:
            logger.warning(
                "Opening line too similar: %.3f >= %.2f | '%s'",
                max_sim,
                opening_threshold,
                new_opening[:40],
            )

        return is_similar, max_sim

    def check_structure(self, new_text: str, history: list[str]) -> tuple[bool, float]:
        """Check if the structural fingerprint is too similar to recent posts.

        Structural fingerprint: line count, question marks, bullets, emoji pattern.
        If 3+ of the last 5 posts share the same structure, flag it.

        Returns:
            (is_too_similar, match_ratio) ratio of recent posts with same structure.
        """
        recent_count = 5
        new_fp = self._structural_fingerprint(new_text)
        recent = history[:recent_count]

        match_count = 0
        for past_text in recent:
            if not past_text.strip():
                continue
            past_fp = self._structural_fingerprint(past_text)
            if new_fp == past_fp:
                match_count += 1

        ratio = match_count / max(len(recent), 1)
        is_similar = match_count >= 3
        if is_similar:
            logger.warning(
                "Structural fingerprint repeated %d/%d times: %s",
                match_count,
                len(recent),
                new_fp,
            )
        return is_similar, ratio

    @staticmethod
    def _structural_fingerprint(text: str) -> str:
        """Compute a structural fingerprint of the text."""
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        line_count = len(lines)
        has_question = any("？" in line or "?" in line for line in lines[:2])
        has_bullets = any(
            line.startswith(("・", "→", "✓", "✅", "●", "▶", "①", "1.", "2.", "3."))
            for line in lines
        )
        has_emoji = bool(re.search(r"[\U0001F300-\U0001F9FF]", text))
        ends_question = lines[-1].endswith(("？", "?")) if lines else False
        has_linebreak = "\n" in text.strip()

        if line_count <= 2:
            length_cat = "xs"
        elif line_count <= 4:
            length_cat = "short"
        elif line_count <= 6:
            length_cat = "medium"
        elif line_count <= 8:
            length_cat = "long"
        else:
            length_cat = "xl"

        return f"{length_cat}|q={has_question}|b={has_bullets}|e={has_emoji}|eq={ends_question}|lb={has_linebreak}"

    @staticmethod
    def _extract_opening(text: str) -> str:
        """Extract the first line of the post."""
        if not text:
            return ""
        return text.strip().split("\n")[0].strip()

    def _compute_similarity(self, a: str, b: str) -> float:
        """Compute weighted similarity between two texts."""
        char_sim = self._jaccard_chars(a, b)
        word_sim = self._jaccard_words(a, b)
        kp_sim = self._keyphrase_overlap(a, b)
        return _W_CHAR * char_sim + _W_WORD * word_sim + _W_KEYPHRASE * kp_sim

    @staticmethod
    def _jaccard_chars(a: str, b: str) -> float:
        """Character bigram Jaccard coefficient."""
        def bigrams(text: str) -> set[str]:
            t = text.strip()
            return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) >= 2 else set()

        set_a = bigrams(a)
        set_b = bigrams(b)
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    @staticmethod
    def _jaccard_words(a: str, b: str) -> float:
        """Word-level Jaccard coefficient."""
        def tokenize(text: str) -> set[str]:
            return set(re.findall(r"[\w]+", text.lower()))

        set_a = tokenize(a)
        set_b = tokenize(b)
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    @staticmethod
    def _keyphrase_overlap(a: str, b: str) -> float:
        """Keyphrase overlap rate.

        Extracts "keyphrases" as contiguous runs of 2+ kanji/katakana/hiragana
        or 4+ alphanumeric characters, then computes Jaccard on them.
        """
        def extract_keyphrases(text: str) -> set[str]:
            phrases: set[str] = set()
            for m in re.finditer(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]{2,}", text):
                phrases.add(m.group())
            for m in re.finditer(r"[a-zA-Z0-9]{4,}", text.lower()):
                phrases.add(m.group())
            return phrases

        set_a = extract_keyphrases(a)
        set_b = extract_keyphrases(b)
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)
