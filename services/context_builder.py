# services/context_builder.py

from typing import Dict, Any, List


def context_for_dish(dish: Dict[str, Any]) -> str:
    return (
        "These are verified facts from the internal Šumska1 menu database.\n"
        f"Dish name: {dish.get('name', '')}\n"
        f"Ingredients: {', '.join(dish.get('ingredients', []))}\n"
        f"Vegan: {'yes' if dish.get('vegan') else 'no'}\n"
        f"Contains gluten: {'yes' if dish.get('contains_gluten') else 'no'}\n"
        f"Sugar-free (no added sugar): {'yes' if dish.get('sugar_free') else 'no'}\n"
        f"Contains soy: {'yes' if dish.get('contains_soy') else 'no'}\n"
        f"Contains nuts: {'yes' if dish.get('contains_nuts') else 'no'}\n"
        f"Contains sesame: {'yes' if dish.get('contains_sesame') else 'no'}\n"
        f"Spicy: {'yes' if dish.get('spicy') else 'no'}\n"
        f"Notes: {dish.get('notes', '')}\n\n"
        "Rules:\n"
        "- Answer strictly using these fields only.\n"
        "- If something is not explicitly present here, say you do not have that information and advise the user to confirm with the host/staff.\n"
        "- Never guarantee 100% safety for allergies, intolerances, celiac disease, diabetes, or any medical condition.\n"
        "- Always answer the user in Serbian.\n"
    )


def context_for_category_list(dishes: List[Dict[str, Any]], category: str) -> str:
    lines = [
        "This is a list of dishes from the internal Šumska1 menu database.",
        f"All dishes below have category: {category}.",
        "",
    ]

    for dish in dishes:
        lines.append(
            f"- {dish.get('name', '')} (ingredients: {', '.join(dish.get('ingredients', []))})"
        )

    lines.append("")
    lines.append(
        "Rules:\n"
        "- When the user asks about this category, list the dish names from above.\n"
        "- Do not invent dishes that are not on the list.\n"
        "- Always remind users with allergies or health conditions to confirm with the host/staff.\n"
        "- Always answer the user in Serbian.\n"
    )

    return "\n".join(lines)
