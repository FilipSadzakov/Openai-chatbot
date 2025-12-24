# api.py

import os
import json
import time
import uuid
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

from core.menu_match import find_category_in_text, find_dish_in_text, filter_dishes_by_category
from data.category_synonyms import CATEGORY_SYNONYMS
from services.logger import log_event

# Load .env locally (Render uses Environment Variables)
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is missing. Set it in .env or Render Environment Variables.")

client = OpenAI(api_key=api_key)

# Load dishes database
with open("data/jela.json", "r", encoding="utf-8") as f:
    DISHES = json.load(f)

MODEL_NAME = "gpt-4.1-mini"

app = FastAPI()

# CORS for Wix
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sumska1.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


# -----------------------------
# ENGLISH-ONLY INTERNAL CONTEXT
# -----------------------------
def context_for_dish(dish: dict) -> str:
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
    )


def context_for_category_list(dishes: list, category: str) -> str:
    lines = [
        "This is a list of dishes from the internal Šumska1 menu database.",
        f"All dishes below have category: {category}.",
        "",
    ]
    for d in dishes:
        lines.append(f"- {d.get('name','')} (ingredients: {', '.join(d.get('ingredients', []))})")

    lines.append("")
    lines.append(
        "Rules:\n"
        "- When the user asks about this category, list the dish names from above.\n"
        "- Do not invent dishes that are not on the list.\n"
        "- Always remind users with allergies or health conditions to confirm with the host/staff."
    )
    return "\n".join(lines)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    request_id = uuid.uuid4().hex
    t0 = time.perf_counter()

    user_input = (req.message or "").strip()
    if not user_input:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log_event({
            "event": "chat_empty_message",
            "request_id": request_id,
            "latency_ms": latency_ms,
        })
        return {"answer": "Napiši pitanje pa ću ti odgovoriti.", "request_id": request_id, "latency_ms": latency_ms}

    # Log request
    log_event({
        "event": "chat_request",
        "request_id": request_id,
        "message": user_input,
    })

    # 1) Detect dish/category
    dish = find_dish_in_text(user_input, DISHES)
    category = find_category_in_text(user_input, CATEGORY_SYNONYMS) if dish is None else None

    # 2) Follow-up question if nothing matches (NO LLM call)
    if dish is None and category is None:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log_event({
            "event": "chat_fallback_question",
            "request_id": request_id,
            "message": user_input,
            "latency_ms": latency_ms,
        })
        return {
            "answer": (
                "Da li pitaš za neko konkretno jelo (napiši naziv), "
                "ili za kategoriju (npr. dezert, pasta, salata, čorba)?"
            ),
            "request_id": request_id,
            "latency_ms": latency_ms,
        }

    # 3) Base system prompt (ENGLISH, but user output must be Serbian)
    base_system_message = {
        "role": "system",
        "content": (
            "You are the chatbot for Šumska1 (a vegan venue).\n"
            "Always answer the user in Serbian.\n"
            "Be short, clear, and factual.\n"
            "Do not invent ingredients or menu items.\n"
            "Do not provide medical advice.\n"
            "If the user mentions allergies, celiac disease, diabetes, insulin resistance, or any health condition, "
            "always tell them to confirm with the host/staff.\n"
            "When internal database context is provided, answer strictly from that context.\n"
            "If a detail is not explicitly present in the context, say you don't have that information and ask them to confirm with the host."
        ),
    }

    convo_messages = [base_system_message]

    # 4) Add internal context (ENGLISH)
    if category:
        dishes_in_cat = filter_dishes_by_category(DISHES, category)
        if dishes_in_cat:
            convo_messages.append({"role": "system", "content": context_for_category_list(dishes_in_cat, category)})
        else:
            convo_messages.append({
                "role": "system",
                "content": (
                    "The internal database has no dishes for this category.\n"
                    "Rules:\n"
                    "- Do not invent dish names.\n"
                    "- Tell the user you currently do not have items in the database for this category and advise them to confirm with the host/staff.\n"
                    "Always answer the user in Serbian."
                )
            })
    else:
        convo_messages.append({"role": "system", "content": context_for_dish(dish)})

    convo_messages.append({"role": "user", "content": user_input})

    # Log LLM call intent (not the full prompt)
    log_event({
        "event": "llm_call",
        "request_id": request_id,
        "model": MODEL_NAME,
        "dish_found": bool(dish),
        "category": category,
    })

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=convo_messages,
    )

    reply = (response.choices[0].message.content or "").strip()
    latency_ms = int((time.perf_counter() - t0) * 1000)

    log_event({
        "event": "chat_response",
        "request_id": request_id,
        "latency_ms": latency_ms,
        "answer": reply,
    })

    return {"answer": reply, "request_id": request_id, "latency_ms": latency_ms}
