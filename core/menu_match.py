# core/menu_match.py

from typing import Optional, Dict, Any, List
from core.normalize import normalize


def _stems_from_name(name: str) -> List[str]:
    """
    Extract searchable stems from a dish name.
    - normalize accents
    - split to words
    - keep words >= 5 chars
    - take stem prefix to catch declensions (palacinke/palacinkama)
    """
    nn = normalize(name).replace("-", " ")
    words = [w for w in nn.split() if len(w) >= 5]
    stems = []
    for w in words:
        stems.append(w)         # full word
        stems.append(w[:7])     # stem
    # remove duplicates while keeping order
    out = []
    seen = set()
    for s in stems:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def find_dish_in_text(text: str, dishes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Dish match rules (in order):
    1) Full name substring match (old behavior)
    2) Stem/word match: if any stem from dish name is present in user text
       (so 'palačinke' / 'palacinkama' matches 'Palačinke bez mleka i jaja')
    """
    t = normalize(text)

    # 1) full name match
    for dish in dishes:
        name = dish.get("name", "")
        if name and normalize(name) in t:
            return dish

    # 2) stem match
    for dish in dishes:
        name = dish.get("name", "")
        if not name:
            continue
        stems = _stems_from_name(name)
        if any(stem in t for stem in stems):
            return dish

    return None


def find_category_in_text(text: str, category_synonyms: Dict[str, List[str]]) -> Optional[str]:
    t = normalize(text)

    for category, words in category_synonyms.items():
        for w in words:
            if normalize(w) in t:
                return category

    return None


def filter_dishes_by_category(dishes: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    return [d for d in dishes if d.get("category") == category]
