"""5-layer JSON fallback parser for LLM responses.

Handles common LLM output quirks:
  1. Direct parse
  2. Raw newline fix inside string values
  3. Trailing comma removal
  4. strict=False (control characters)
  5. Individual object extraction
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


def _fix_raw_newlines(text: str) -> str:
    """Replace raw newlines inside JSON string values with \\n."""
    result: list[str] = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == "\\":
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ch == "\n":
            result.append("\\n")
            continue
        if in_string and ch == "\r":
            continue
        result.append(ch)
    return "".join(result)


def _extract_json_objects(text: str) -> list[dict]:
    """Extract individual top-level JSON objects from text."""
    objects: list[dict] = []
    depth = 0
    start: int | None = None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"' and not esc:
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                fragment = text[start : i + 1]
                try:
                    obj = json.loads(fragment)
                    objects.append(obj)
                except json.JSONDecodeError:
                    fixed = _fix_raw_newlines(fragment)
                    try:
                        obj = json.loads(fixed)
                        objects.append(obj)
                    except json.JSONDecodeError as e:
                        logger.debug("Layer 5 parse failed: %s", e)
                start = None
    return objects


def _strip_code_block(text: str) -> str:
    """Remove markdown code block wrappers if present."""
    text = text.strip()
    if "```json" in text:
        start = text.index("```json") + len("```json")
        end = text.index("```", start)
        return text[start:end].strip()
    if "```" in text:
        start = text.index("```") + len("```")
        end = text.index("```", start)
        return text[start:end].strip()
    return text


def extract_json_array(text: str) -> list:
    """Extract a JSON array from an LLM response with 5-layer fallback.

    Raises:
        json.JSONDecodeError: If all parse attempts fail.
    """
    text = _strip_code_block(text)

    # Narrow to array bounds
    bracket_start = text.find("[")
    bracket_end = text.rfind("]")
    if bracket_start != -1 and bracket_end != -1:
        text = text[bracket_start : bracket_end + 1]

    # Layer 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.debug("Layer 1 parse failed: %s", e)

    # Layer 2: fix raw newlines
    fixed = _fix_raw_newlines(text)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        logger.debug("Layer 2 parse failed: %s", e)

    # Layer 3: trailing comma removal
    fixed2 = re.sub(r",\s*([}\]])", r"\1", fixed)
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError as e:
        logger.debug("Layer 3 parse failed: %s", e)

    # Layer 4: strict=False (allows control characters)
    decoder = json.JSONDecoder(strict=False)
    try:
        result, _ = decoder.raw_decode(fixed)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError as e:
        logger.debug("Layer 4 parse failed: %s", e)

    # Layer 5: object-by-object extraction
    logger.debug("Trying object-by-object extraction as fallback")
    objects = _extract_json_objects(text)
    if objects:
        logger.debug("Extracted %d objects individually", len(objects))
        return objects

    logger.warning("All JSON array parse attempts failed (len=%d)", len(text))
    raise json.JSONDecodeError("All parse attempts failed", text, 0)


def extract_json_object(text: str) -> dict:
    """Extract a single JSON object from an LLM response.

    Raises:
        json.JSONDecodeError: If all parse attempts fail.
    """
    text = _strip_code_block(text)

    # Narrow to object bounds
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        text = text[brace_start : brace_end + 1]

    # Layer 1: direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError as e:
        logger.debug("Layer 1 parse failed: %s", e)

    # Layer 2: fix raw newlines
    fixed = _fix_raw_newlines(text)
    try:
        result = json.loads(fixed)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError as e:
        logger.debug("Layer 2 parse failed: %s", e)

    # Layer 3: trailing comma removal
    fixed2 = re.sub(r",\s*([}\]])", r"\1", fixed)
    try:
        result = json.loads(fixed2)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError as e:
        logger.debug("Layer 3 parse failed: %s", e)

    raise json.JSONDecodeError("Failed to extract JSON object", text, 0)
