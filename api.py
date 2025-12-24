import os
import json
import unicodedata
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# Učitaj .env (lokalno) i API ključ (na Renderu ide preko Environment Variables)
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# Učitaj bazu jela
with open("jela.json", "r", encoding="utf-8") as f:
    DISHES = json.load(f)

app = FastAPI()

# CORS za Wix
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sumska1.com"],  # kasnije možeš zameniti sa ["https://sumska1.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


# -----------------------------
# NORMALIZACIJA (š → s, č → c…)
# -----------------------------
def normalize(text: str) -> str:
    text = text.lower()
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


# -----------------------------
# PRONALAŽENJE KONKRETNOG JELA
# -----------------------------
def nadji_jelo_u_pitanju(tekst: str):
    t = normalize(tekst)
    for dish in DISHES:
        if normalize(dish["name"]) in t:
            return dish
    return None


# -----------------------------
# PRONALAŽENJE KATEGORIJE U PITANJU
# -----------------------------
def nadji_kategoriju_u_pitanju(tekst: str):
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

    # glavna jela
    if any(kw in t for kw in ["glavno jelo", "glavna jela", "rucak", "ručak"]):
        return "glavno_jelo"

    return None


def filtriraj_jela_po_kategoriji(category: str):
    return [d for d in DISHES if d.get("category") == category]


# -----------------------------
# KONTKST ZA KONKRETNO JELO
# -----------------------------
def formiraj_kontekst_za_jelo(dish: dict) -> str:
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
def formiraj_kontekst_za_listu_jela(jela: list, category: str) -> str:
    lines = [
        "Ovo je lista jela iz interne baze restorana Šumska1.",
        f"Sva dole navedena jela imaju kategoriju: {category}.",
        "",
    ]

    for dish in jela:
        lines.append(f"- {dish['name']} (sastojci: {', '.join(dish['ingredients'])})")

    lines.append("")
    lines.append(
        "Kada gost pita za ovu kategoriju (npr. slatko, paste, salate, čorbe), "
        "nabroj mu po nazivu sva jela sa liste iznad. "
        "Ne izmišljaj nova jela koja nisu na listi. "
        "Naglasis da su jela veganska (ako jesu) i uvek napomeni da za alergije "
        "i posebne zdravstvene potrebe treba da proveri sa domaćinom."
    )

    return "\n".join(lines)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    user_input = (req.message or "").strip()
    if not user_input:
        return {"answer": "Napiši pitanje pa ću ti odgovoriti."}

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

    convo_messages = [base_system_message]

    # 1) Kategorija?
    category = nadji_kategoriju_u_pitanju(user_input)

    # 2) Konkretno jelo samo ako nije kategorija
    dish = nadji_jelo_u_pitanju(user_input) if category is None else None

    if category:
        jela = filtriraj_jela_po_kategoriji(category)
        if jela:
            convo_messages.append({
                "role": "system",
                "content": formiraj_kontekst_za_listu_jela(jela, category)
            })
        else:
            convo_messages.append({
                "role": "system",
                "content": (
                    "Nema nijednog jela u bazi za ovu kategoriju.\n"
                    "Nemoj izmišljati nazive jela. Reci gostu da trenutno "
                    "nema podataka u bazi i da proveri sa domaćinom."
                )
            })

    elif dish:
        convo_messages.append({
            "role": "system",
            "content": formiraj_kontekst_za_jelo(dish)
        })

    else:
        convo_messages.append({
            "role": "system",
            "content": (
                "Nema podataka o ovom jelu niti o traženoj kategoriji u bazi.\n"
                "NE izmišljaj sastojke ni nutritivne informacije.\n"
                "Možeš dati samo opštu informaciju o veganskoj ishrani, "
                "ali reci gostu da za konkretno jelo mora da proveri sa osobljem."
            )
        })

    convo_messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=convo_messages
    )

    reply = response.choices[0].message.content
    return {"answer": reply}
