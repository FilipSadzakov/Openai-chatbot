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
from core.versioning import sha256_file
from core.postcheck import extract_allowed_ingredients, detect_unknown_ingredient
from data.category_synonyms import CATEGORY_SYNONYMS
from services.context_payload import build_context_payload
from services.logger import log_event

# Load .env locally (Render uses Environment Variables)
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is missing. Set it in .env or Render Environment Variables.")

client = OpenAI(api_key=api_key)

MODEL_NAME = "gpt-4.1-mini"

# Version fingerprints (for tracing/debugging)
PROMPT_VERSION = "v1"
DATA_PATH = "data/jela.json"
DATA_VERSION = sha256_file(DATA_PATH)

# Load dishes database
with open(DATA_PATH, "r", encoding="utf-8") as f:
    DISHES = json.load(f)

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


@app.get("/health")
def health():
    return {"status": "ok"}


def db_only_answer_from_payload(payload: dict) -> str:
    dish = payload.get("dish") or {}
    name = dish.get("name") or "Ovo jelo"
    ingredients = dish.get("ingredients") or []
    ing_text = ", ".join(ingredients) if ingredients else "nisu navedeni u bazi"

    # Keep user-facing Serbian
    lines = [
        f"Prema našoj bazi, {name} sadrži: {ing_text}.",
        "Ako imaš alergije ili posebne zdravstvene potrebe, obavezno proveri sa domaćinom/osobljem.",
    ]
    return " ".join(lines)


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
            "prompt_version": PROMPT_VERSION,
            "data_version": DATA_VERSION,
            "latency_ms": latency_ms,
        })
        return {"answer": "Napiši pitanje pa ću ti odgovoriti.", "request_id": request_id, "latency_ms": latency_ms}

    log_event({
        "event": "chat_request",
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "data_version": DATA_VERSION,
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
            "prompt_version": PROMPT_VERSION,
            "data_version": DATA_VERSION,
            "latency_ms": latency_ms,
            "message": user_input,
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
            "You will receive CONTEXT_JSON from the internal menu database.\n"
            "Answer strictly using CONTEXT_JSON only.\n"
            "If a detail is not explicitly present in CONTEXT_JSON, say you don't have that information and ask the user to confirm with the host."
        ),
    }

    convo_messages = [base_system_message]

    # 4) Build structured context payload (JSON)
    if dish is not None:
        payload = build_context_payload(dish=dish, category=None, category_dishes=None)
    else:
        dishes_in_cat = filter_dishes_by_category(DISHES, category)
        payload = build_context_payload(dish=None, category=category, category_dishes=dishes_in_cat)

    convo_messages.append({
        "role": "system",
        "content": "CONTEXT_JSON:\n" + json.dumps(payload, ensure_ascii=False),
    })
    convo_messages.append({"role": "user", "content": user_input})

    log_event({
        "event": "llm_call",
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "data_version": DATA_VERSION,
        "model": MODEL_NAME,
        "context_mode": payload.get("mode"),
        "dish_found": bool(dish),
        "category": category,
    })

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=convo_messages,
    )

    reply = (response.choices[0].message.content or "").strip()

    # 5) Post-check (dish mode only): if unknown ingredient appears, override with DB-only answer
    if payload.get("mode") == "dish":
        allowed = extract_allowed_ingredients(payload) or []
        triggered, unknown_items = detect_unknown_ingredient(reply, allowed)
        if triggered:
            safe_reply = db_only_answer_from_payload(payload)
            latency_ms = int((time.perf_counter() - t0) * 1000)

            log_event({
                "event": "chat_postcheck_triggered",
                "request_id": request_id,
                "prompt_version": PROMPT_VERSION,
                "data_version": DATA_VERSION,
                "latency_ms": latency_ms,
                "unknown_items": unknown_items,
            })

            return {"answer": safe_reply, "request_id": request_id, "latency_ms": latency_ms}

    latency_ms = int((time.perf_counter() - t0) * 1000)

    log_event({
        "event": "chat_response",
        "request_id": request_id,
        "prompt_version": PROMPT_VERSION,
        "data_version": DATA_VERSION,
        "latency_ms": latency_ms,
        "answer": reply,
    })

    return {"answer": reply, "request_id": request_id, "latency_ms": latency_ms}
