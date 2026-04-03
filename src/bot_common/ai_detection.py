"""AI-generated phrase detection for BAN avoidance.

Detects commonly flagged AI-generated expressions in post text.
Built-in common phrases are always available; domain-specific phrases
can be passed via extra_phrases argument.

Optional TOML loading:
    If a TOML path is provided, loads additional phrases from it.
    Sections: [common] and any domain-specific section.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in common phrases (domain-agnostic)
# ---------------------------------------------------------------------------

BUILTIN_COMMON_PHRASES: list[str] = [
    "と言えるでしょう",
    "と言っても過言ではありません",
    "ではないでしょうか",
    "について解説します",
    "について詳しく見ていきましょう",
    "まとめると",
    "いかがでしたか",
    "ぜひ参考にしてみてください",
    "それでは早速",
    "最後までお読みいただきありがとうございます",
    "ポイントを押さえて",
    "結論から言うと",
    "つまるところ",
    "端的に言えば",
    "網羅的に",
    "包括的に",
    "多角的に",
    "一助となれば幸いです",
    "お役に立てれば幸いです",
    "についてご紹介します",
    "していきましょう",
    "見ていきましょう",
    "確認していきましょう",
    "おさらいしましょう",
    "ここでは",
    "それでは",
    "というわけで",
    "以上のことから",
    "これらを踏まえて",
    "総合的に判断すると",
]


def detect_ai_phrases(
    text: str,
    extra_phrases: list[str] | None = None,
) -> list[str]:
    """Return list of AI-typical phrases found in the text.

    Args:
        text: Post content to check.
        extra_phrases: Domain-specific phrases to check in addition to built-in common phrases.

    Returns:
        List of matched phrases (empty if none found).
    """
    phrases = BUILTIN_COMMON_PHRASES
    if extra_phrases:
        phrases = phrases + extra_phrases
    return [p for p in phrases if p in text]


def load_phrases_from_toml(
    toml_path: str | Path,
    sections: list[str] | None = None,
) -> list[str]:
    """Load additional phrases from a TOML file.

    Args:
        toml_path: Path to the TOML file.
        sections: Section names to load (e.g. ["parenting"]). If None, loads all sections.

    Returns:
        Combined list of phrases from the specified sections.
        Returns empty list if file is missing or unreadable.
    """
    path = Path(toml_path)
    if not path.exists():
        logger.warning("ai_phrases.toml not found at %s", path)
        return []

    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        logger.error("Failed to load ai_phrases.toml: %s", e)
        return []

    phrases: list[str] = []
    target_sections = sections if sections else [k for k in data if k != "common"]
    for section in target_sections:
        phrases.extend(data.get(section, {}).get("phrases", []))

    logger.debug("Loaded %d phrases from %s (sections=%s)", len(phrases), path, target_sections)
    return phrases
