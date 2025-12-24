from typing import Dict, Any, List

def context_for_dish(dish: Dict[str, Any]) -> str:
    return (
        "Ovo su proverene informacije iz interne baze jela restorana Šumska1.\n"
        f"Naziv jela: {dish['name']}\n"
        f"Sastojci: {', '.join(dish['ingredients'])}\n"
        f"Vegansko: {'da' if dish.get('vegan') else 'ne'}\n"
        f"Sadrži gluten: {'da' if dish.get('contains_gluten') else 'ne'}\n"
        f"Bez dodatog šećera: {'da' if dish.get('sugar_free') else 'ne'}\n"
        f"Sadrži soju: {'da' if dish.get('contains_soy') else 'ne'}\n"
        f"Sadrži orašaste plodove: {'da' if dish.get('contains_nuts') else 'ne'}\n"
        f"Sadrži susam: {'da' if dish.get('contains_sesame') else 'ne'}\n"
        f"Ljuto: {'da' if dish.get('spicy') else 'ne'}\n"
        f"Napomene: {dish.get('notes', '')}\n\n"
        "Odgovaraj isključivo na osnovu ovih podataka.\n"
        "Ako nešto nije eksplicitno navedeno, reci gostu da obavezno proveri sa domaćinom.\n"
        "Nikada ne garantuj 100% bezbednost za alergije, intolerancije ili hronične bolesti."
    )

def context_for_category_list(dishes: List[Dict[str, Any]], category: str) -> str:
    lines = [
        "Ovo je lista jela iz interne baze restorana Šumska1.",
        f"Sva dole navedena jela imaju kategoriju: {category}.",
        "",
    ]
    for dish in dishes:
        lines.append(f"- {dish['name']} (sastojci: {', '.join(dish['ingredients'])})")

    lines.append("")
    lines.append(
        "Kada gost pita za ovu kategoriju, nabroj mu po nazivu sva jela sa liste iznad. "
        "Ne izmišljaj nova jela koja nisu na listi. "
        "Naglasis da su jela veganska (ako jesu) i uvek napomeni da za alergije "
        "i posebne zdravstvene potrebe treba da proveri sa domaćinom."
    )
    return "\n".join(lines)
