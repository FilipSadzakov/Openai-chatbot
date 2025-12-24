# core/menu_match.py

from typing import Optional, Dict, Any, List
from core.normalize import normalize


def find_dish_in_text(text: str, dishes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    t = normalize(text)
    for dish in dishes:
        # Simple substring match (kept as-is for now)
        if normalize(dish["name"]) in t:
            return dish
    return None


def find_category_in_text(
    text: str,
    category_synonyms: Dict[str, List[str]],
) -> Optional[str]:
    t = normalize(text)

    for category, words in category_synonyms.items():
        for w in words:
            if normalize(w) in t:
                return category

    return None


def filter_dishes_by_category(dishes: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    return [d for d in dishes if d.get("category") == category]
