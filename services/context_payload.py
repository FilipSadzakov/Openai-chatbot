# services/context_payload.py

from typing import Any, Dict, List, Optional


def build_context_payload(
    dish: Optional[Dict[str, Any]],
    category: Optional[str],
    category_dishes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if dish:
        return {
            "mode": "dish",
            "dish": {
                "name": dish.get("name"),
                "ingredients": dish.get("ingredients", []),
                "vegan": dish.get("vegan"),
                "contains_gluten": dish.get("contains_gluten"),
                "sugar_free": dish.get("sugar_free"),
                "contains_soy": dish.get("contains_soy"),
                "contains_nuts": dish.get("contains_nuts"),
                "contains_sesame": dish.get("contains_sesame"),
                "spicy": dish.get("spicy"),
                "notes": dish.get("notes", ""),
                "category": dish.get("category"),
            },
        }

    return {
        "mode": "category",
        "category": category,
        "dishes": [
            {"name": d.get("name"), "ingredients": d.get("ingredients", []), "vegan": d.get("vegan")}
            for d in (category_dishes or [])
        ],
    }
