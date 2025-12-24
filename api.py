# api.py

import os
import json
import time
import uuid
from collections import deque
from typing import Optional, Deque, Dict, Any, List, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

from core.menu_match import find_category_in_text, find_dish_in_text, filter_dishes_by_category
from core.versioning import sha256_file
from core.postcheck import extract_allowed_ingredients, detect_unknown_ingredient
from core.normalize import normalize

from data.category_synonyms import CATEGORY_SYNONYMS
from services.context_payload import build_context_payload
from services.logger import log_event

# -----------------------------
# Config
# -----------------------------
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is missing. Set it in .env or Render Environment Variables.")

client = OpenAI(api_key=api_key)

MODEL_NAME = "gpt-4.1-mini"
PROMPT_VERSION = "v1"

DATA_PATH = "data/jela.json"
DATA_VERSION = sha256_file(DATA_PATH)

with open(DATA_PATH, "r", encoding="utf-8") as f:
    DISHES = json.load(f)

# -----------------------------
# RAM session memory
# -----------------------------
MAX_SESSION_MESSAGES = 10          # user+assistant messages kept
SESSION_TTL_SECONDS = 30 * 60      # 30 minutes inactivity


class SessionState:
    def __init__(self) -> None:
        self.messages: Deque[Dict[str, str]] = deque(maxlen=MAX_SESSION_MESSAGES)
        self.last_dish_name: Optional[str] = None
        self.last_category: Optional[str] = None
        self.last_dish_candidates: Optional[List[str]] = None  # <- NEW: candidates from last category listing
        self.updated_at: float = time.time()


SESSIONS: Dict[str, SessionState] = {}


def _cleanup_sessions(now: float) -> None:
    to_delete = [sid for sid, st in SESSIONS.items() if (now - st.updated_at) > SESSION_TTL_SECONDS]
    for sid in to_delete:
        del SESSIONS[sid]


def get_session(session_id: Optional[str]) -> Tuple[str, SessionState]:
    now = time.time()
    _cleanup_sessions(now)

    if session_id and session_id in SESSIONS:
        st = SESSIONS[session_id]
        st.updated_at = now
        return session_id, st

    new_id = uuid.uuid4().hex
    st = SessionState()
    SESSIONS[new_id] = st
    return new_id, st


def find_dish_by_name(name: str) -> Optional[Dict[str, Any]]:
    n = normalize(name)
    for d in DISHES:
        if normalize(d.get("name", "")) == n:
            return d
    return None


def resolve_dish_from_session(user_text: str, session: SessionState) -> Optional[Dict[str, Any]]:
    """
    Resolve short references like "palačinke" after:
    - we talked about a specific dish (last_dish_name), OR
    - we listed a category (last_dish_candidates).
    """
    t = normalize(user_text)

    # 1) If we previously talked about a specific dish
    if session.last_dish_name:
        last_name_norm = normalize(session.last_dish_name).replace("-", " ")
        stems = [w for w in last_name_norm.split() if len(w) >= 4]
        if any(stem in t for stem in stems):
            return find_dish_by_name(session.last_dish_name)

    # 2) If we previously listed dishes (category answer), try candidates
    if session.last_dish_candidates:
        for name in session.last_dish_candidates:
            nn = normalize(name).replace("-", " ")
            words = [w for w in nn.split() if len(w) >= 5]
            if not words:
                continue

            key = words[0]              # e.g. "palacinke"
            stem = key[:7]              # e.g. "palacin" (covers declensions: palacinke/palacinkama)
            if key in t or (stem and stem in t):
                return find_dish_by_name(name)

    return None


# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI()

# Wix HTML iframe -> allow all origins (no cookies)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


def db_only_answer_from_payload(payload: dict) -> str:
    dish = payload.get("dish") or {}
    name = dish.get("name") or "Ovo jelo"
    ingredients = dish.get("ingredients") or []
    ing_text = ", ".join(ingredients) if ingredients else "nisu navedeni u bazi"

    return (
        f"Prema našoj bazi, {name} sadrži: {ing_text}. "
        "Ako imaš alergije ili posebne zdravstvene potrebe, obavezno proveri sa domaćinom/osobljem."
    )


@app.post("/chat")
def chat(req: ChatRequest):
    request_id = uuid.uuid4().hex
    t0 = time.perf_counter()

    session_id, session = get_session(req.session_id)

    user_input = (req.message or "").strip()
    if not user_input:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log_event({
            "event": "chat_empty_message",
            "request_id": request_id,
            "session_id": session_id,
            "prompt_version": PROMPT_VERSION,
            "data_version": DATA_VERSION,
            "latency_ms": latency_ms,
        })
        return {
            "answer": "Napiši pitanje pa ću ti odgovoriti.",
            "session_id": session_id,
            "request_id": request_id,
            "latency_ms": latency_ms
        }

    log_event({
        "event": "chat_request",
        "request_id": request_id,
        "session_id": session_id,
        "prompt_version": PROMPT_VERSION,
        "data_version": DATA_VERSION,
        "message": user_input,
    })

    # 1) Detect dish/category in current message
    dish = find_dish_in_text(user_input, DISHES)
    category = find_category_in_text(user_input, CATEGORY_SYNONYMS) if dish is None else None

    # 2) If nothing found, try resolve from session context
    if dish is None and category is None:
        dish = resolve_dish_from_session(user_input, session)

    # 3) If still nothing, ask a follow-up (NO LLM call)
    if dish is None and category is None:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        log_event({
            "event": "chat_fallback_question",
            "request_id": request_id,
            "session_id": session_id,
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
            "session_id": session_id,
            "request_id": request_id,
            "latency_ms": latency_ms,
        }

    # 4) Base system prompt (ENGLISH; user output Serbian)
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
            "If a detail is not explicitly present in CONTEXT_JSON, say you don't have that information and ask the user to confirm with the host.\n"
        ),
    }

    convo_messages: List[Dict[str, str]] = [base_system_message]

    # 5) Add session history (last 10 messages)
    convo_messages.extend(list(session.messages))

    # 6) Build structured context payload (JSON) for this turn + update session memory pointers
    if dish is not None:
        payload = build_context_payload(dish=dish, category=None, category_dishes=None)

        session.last_dish_name = dish.get("name")
        session.last_category = None
        session.last_dish_candidates = None  # <- clear candidates when specific dish selected
    else:
        dishes_in_cat = filter_dishes_by_category(DISHES, category)
        payload = build_context_payload(dish=None, category=category, category_dishes=dishes_in_cat)

        session.last_category = category
        session.last_dish_name = None
        session.last_dish_candidates = [d.get("name") for d in dishes_in_cat if d.get("name")]  # <- NEW

    convo_messages.append({
        "role": "system",
        "content": "CONTEXT_JSON:\n" + json.dumps(payload, ensure_ascii=False),
    })

    # 7) Current user message
    convo_messages.append({"role": "user", "content": user_input})

    log_event({
        "event": "llm_call",
        "request_id": request_id,
        "session_id": session_id,
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

    # 8) Post-check (dish mode only): if unknown ingredient appears, override with DB-only answer
    if payload.get("mode") == "dish":
        allowed = extract_allowed_ingredients(payload) or []
        triggered, unknown_items = detect_unknown_ingredient(reply, allowed)
        if triggered:
            safe_reply = db_only_answer_from_payload(payload)
            latency_ms = int((time.perf_counter() - t0) * 1000)

            session.messages.append({"role": "user", "content": user_input})
            session.messages.append({"role": "assistant", "content": safe_reply})

            log_event({
                "event": "chat_postcheck_triggered",
                "request_id": request_id,
                "session_id": session_id,
                "prompt_version": PROMPT_VERSION,
                "data_version": DATA_VERSION,
                "latency_ms": latency_ms,
                "unknown_items": unknown_items,
            })

            return {
                "answer": safe_reply,
                "session_id": session_id,
                "request_id": request_id,
                "latency_ms": latency_ms
            }

    latency_ms = int((time.perf_counter() - t0) * 1000)

    # 9) Save history (RAM): user + assistant
    session.messages.append({"role": "user", "content": user_input})
    session.messages.append({"role": "assistant", "content": reply})

    log_event({
        "event": "chat_response",
        "request_id": request_id,
        "session_id": session_id,
        "prompt_version": PROMPT_VERSION,
        "data_version": DATA_VERSION,
        "latency_ms": latency_ms,
        "answer": reply,
    })

    return {
        "answer": reply,
        "session_id": session_id,
        "request_id": request_id,
        "latency_ms": latency_ms
    }
