import os
import json
import unicodedata
from dotenv import load_dotenv
from openai import OpenAI

# Učitaj .env i API ključ
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# Učitaj bazu jela
with open("jela.json", "r", encoding="utf-8") as f:
    DISHES = json.load(f)


# -----------------------------
# NORMALIZACIJA (š → s, č → c…)
# -----------------------------
def normalize(text):
    """Pretvara š,č,ć,ž,đ u s,c,c,z,d radi lakšeg poređenja."""
    text = text.lower()
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


# -----------------------------
# PRONALAŽENJE KONKRETNOG JELA
# -----------------------------
def nadji_jelo_u_pitanju(tekst):
    """Upoređuje ime jela i korisnički unos bez dijakritika."""
    t = normalize(tekst)
    for dish in DISHES:
        if normalize(dish["name"]) in t:
            return dish
    return None


# -----------------------------
# PRONALAŽENJE KATEGORIJE U PITANJU
# -----------------------------
def nadji_kategoriju_u_pitanju(tekst):
    """
    Gleda da li gost pita za slatko, paste, salate, čorbe itd.
    Vraća string kategorije iz jela.json (npr. 'dezert', 'pasta', 'salata', 'corba'...),
    ili None ako ništa ne prepozna.
    """
    t = normalize(tekst)

    # slatko / desert
    if any(kw in t for kw in ["slatko", "slatkisi", "slatkis", "dezert", "desert", "kolac", "kolaci"]):
        return "dezert"

    # paste / testenine
    if any(kw in t for kw in ["pasta", "paste", "testenina", "testenine"]):
        return "pasta"

    # salate
    if "salat" in t:
        return "salata"

    # čorbe / supe
    if any(kw in t for kw in ["corba", "čorba", "supa", "supe"]):
        return "corba"

    # doručak
    if any(kw in t for kw in ["dorucak", "doručak"]):
        return "dorucak"

    # namazi
    if "namaz" in t or "namaze" in t:
        return "namaz"

    # hleb / lepinje
    if any(kw in t for kw in ["hleb", "lepinj"]):
        return "hleb"

    # prilozi
    if "prilog" in t:
        return "prilog"

    # glavna jela (opciono)
    if any(kw in t for kw in ["glavno jelo", "glavna jela", "rucak", "ručak"]):
        return "glavno_jelo"

    return None


def filtriraj_jela_po_kategoriji(category):
    """Vraća listu jela iz DISHES koja imaju traženu kategoriju."""
    return [d for d in DISHES if d.get("category") == category]


# -----------------------------
# KONTKST ZA KONKRETNO JELO
# -----------------------------
def formiraj_kontekst_za_jelo(dish):
    """Pretvara podatke iz JSON-a u jasan tekst koji model koristi za odgovor."""
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


# -----------------------------
# KONTKST ZA LISTU JELA (KATEGORIJA)
# -----------------------------
def formiraj_kontekst_za_listu_jela(jela, category):
    """
    Priprema kontekst kada gost pita npr. 'šta ima slatko', 'koje paste se kuvaju',
    'koje salate imate' itd.
    """
    lines = [
        "Ovo je lista jela iz interne baze restorana Šumska1.",
        f"Sva dole navedena jela imaju kategoriju: {category}.",
        "",
    ]

    for dish in jela:
        line = f"- {dish['name']} (sastojci: {', '.join(dish['ingredients'])})"
        lines.append(line)

    lines.append("")
    lines.append(
        "Kada gost pita za ovu kategoriju (npr. slatko, paste, salate, čorbe), "
        "nabroj mu po nazivu sva jela sa liste iznad. "
        "Ne izmišljaj nova jela koja nisu na listi. "
        "Naglasis da su jela veganska (ako jesu) i uvek napomeni da za alergije "
        "i posebne zdravstvene potrebe treba da proveri sa domaćinom."
    )

    return "\n".join(lines)


# -----------------------------
# MAIN PETLJA (sesiona memorija)
# -----------------------------
def main():
    print("Chatbot Šumska1 – pitanja o hrani. Ukucaj 'kraj' za izlaz.\n")

    base_system_message = {
        "role": "system",
        "content": (
            "Ti si chatbot veganskog prostora Šumska1.\n"
            "Odgovaraš kratko, jasno i na srpskom.\n"
            "Ne izmišljaš sastojke. Ne daješ medicinske savete.\n"
            "Za osobe sa alergijama, celijakijom, dijabetesom ili insulinskom rezistencijom "
            "uvek naglašavaš da moraju da provere sa domaćinom.\n"
            "Kada imaš kontekst o jelima iz interne baze, odgovaraj isključivo na osnovu tih podataka."
        ),
    }

    messages = [base_system_message]

    while True:
        user_input = input("Gost: ")

        if user_input.lower() in ["kraj", "exit", "quit"]:
            print("Chatbot: Hvala! Vidimo se u Šumskoj 🌿")
            break

        # Da li pita za kategoriju (slatko, paste, salate, čorbe...)
        category = nadji_kategoriju_u_pitanju(user_input)

        # Da li direktno pominje konkretno jelo po imenu
        dish = nadji_jelo_u_pitanju(user_input) if category is None else None

        convo_messages = [base_system_message]

        if category:
            jela = filtriraj_jela_po_kategoriji(category)
            if jela:
                # imamo jela iz te kategorije → pravi kontekst sa listom
                convo_messages.append({
                    "role": "system",
                    "content": formiraj_kontekst_za_listu_jela(jela, category)
                })
            else:
                # nema nijedno jelo te kategorije u bazi
                convo_messages.append({
                    "role": "system",
                    "content": (
                        "Nema nijednog jela u bazi za ovu kategoriju.\n"
                        "Nemoj izmišljati nazive jela. Reci gostu da trenutno "
                        "nema podataka u bazi i da proveri sa domaćinom."
                    )
                })

        elif dish:
            # Ako je jelo pronađeno → dodaj podatke iz baze
            convo_messages.append({
                "role": "system",
                "content": formiraj_kontekst_za_jelo(dish)
            })

        else:
            # Ako nije pronađeno ni jelo ni kategorija → ne izmišljaj ništa
            convo_messages.append({
                "role": "system",
                "content": (
                    "Nema podataka o ovom jelu niti o traženoj kategoriji u bazi.\n"
                    "NE izmišljaj sastojke ni nutritivne informacije.\n"
                    "Možeš dati samo opštu informaciju o veganskoj ishrani, "
                    "ali reci gostu da za konkretno jelo mora da proveri sa osobljem."
                )
            })

        # Dodaj korisnički input
        convo_messages.append({"role": "user", "content": user_input})

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=convo_messages
        )

        reply = response.choices[0].message.content
        print("Chatbot:", reply)

        # Čuvamo samo dijalog, ne dodatne sistemske poruke
        messages.append({"role": "user", "content": user_input})
        messages.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()
