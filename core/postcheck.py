# core/postcheck.py

import re
from typing import Any, Dict, List, Optional, Tuple

from core.normalize import normalize


_MARKERS = [
    "sastojci",
    "sastojak",
    "sadrzi",
    "sadrži",
    "u jelu",
    "u jela",
]


def _allowed_set(allowed_ingredients: List[str]) -> List[str]:
    # normalized strings, keep full phrases
    return [normalize(x).strip() for x in allowed_ingredients if x and normalize(x).strip()]


def extract_allowed_ingredients(payload: Dict[str, Any]) -> Optional[List[str]]:
    if payload.get("mode") != "dish":
        return None
    dish = payload.get("dish") or {}
    ings = dish.get("ingredients") or []
    if not isinstance(ings, list):
        return None
    return ings


def _find_marker_pos(a_norm: str) -> Optional[int]:
    for m in _MARKERS:
        m_norm = normalize(m)
        idx = a_norm.find(m_norm)
        if idx != -1:
            return idx
    return None


def _extract_candidate_segment(a_norm: str) -> Optional[str]:
    """
    Grab a short segment after a marker like 'sastojci' or 'sadrži'.
    We stop at newline or sentence end. This is intentionally conservative.
    """
    pos = _find_marker_pos(a_norm)
    if pos is None:
        return None

    seg = a_norm[pos:]
    # cut at first newline
    seg = seg.split("\n", 1)[0]
    # cut at first sentence end (.)
    seg = seg.split(".", 1)[0]
    # cut at first ';'
    seg = seg.split(";", 1)[0]

    # If there's a colon, take after it (common "Sastojci: ...")
    if ":" in seg:
        seg = seg.split(":", 1)[1]

    return seg.strip() if seg.strip() else None


def _split_items(segment: str) -> List[str]:
    """
    Split by commas and ' i '.
    """
    seg = segment
    seg = seg.replace(" i ", ",")
    seg = seg.replace(" te ", ",")
    seg = seg.replace(" pa ", ",")
    parts = [p.strip() for p in seg.split(",")]
    # remove very short noise
    cleaned = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip()
        p = p.strip(" -•")
        if len(p) >= 3:
            cleaned.append(p)
    return cleaned


def _matches_allowed(item_norm: str, allowed_norm: List[str]) -> bool:
    """
    Allow match if:
    - exact match, OR
    - allowed phrase is contained in item, OR
    - item is contained in allowed phrase
    This handles multi-word ingredients.
    """
    for a in allowed_norm:
        if item_norm == a:
            return True
        if a and a in item_norm:
            return True
        if item_norm and item_norm in a:
            return True
    return False


def detect_unknown_ingredient(
    answer: str,
    allowed_ingredients: List[str],
) -> Tuple[bool, List[str]]:
    """
    Returns (triggered, unknown_items).
    Trigger only if we can confidently extract an ingredient-like list segment.
    """
    if not answer or not allowed_ingredients:
        return (False, [])

    a_norm = normalize(answer)
    segment = _extract_candidate_segment(a_norm)
    if not segment:
        return (False, [])

    items = _split_items(segment)
    if not items:
        return (False, [])

    allowed_norm = _allowed_set(allowed_ingredients)
    unknown = []
    for it in items:
        it_norm = normalize(it)
        # ignore generic words
        if it_norm in {"sastojci", "sastojak", "sadrzi", "sadrži"}:
            continue
        if not _matches_allowed(it_norm, allowed_norm):
            unknown.append(it)

    return (len(unknown) > 0, unknown)
