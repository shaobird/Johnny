"""
Local semantic embeddings for Open Brain search.

Uses sentence-transformers/all-MiniLM-L6-v2 (~80 MB, 384 dims).
Runs fully offline — no API keys, no cloud dependency.

Embeddings stored in storage/thoughts/embeddings.json (gitignored).
Format: { "t00001": [float, ...], ... }

Usage:
    from agents.embeddings import semantic_search_thoughts, embed_and_store

    # Called automatically by capture_thought on each new thought
    embed_and_store(thought_id, thought_text)

    # Search
    results = semantic_search_thoughts("construction site progress", top_k=5)
"""

import json
import os
import math

EMBEDDINGS_FILE = "storage/thoughts/embeddings.json"
_MODEL = None  # lazy-loaded


def _get_model():
    global _MODEL
    if _MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            return None
    return _MODEL


def _embed(text: str) -> list[float] | None:
    model = _get_model()
    if model is None:
        return None
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def _load_embeddings() -> dict:
    if os.path.exists(EMBEDDINGS_FILE):
        with open(EMBEDDINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_embeddings(embs: dict) -> None:
    os.makedirs(os.path.dirname(EMBEDDINGS_FILE), exist_ok=True)
    tmp = EMBEDDINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(embs, f)
    os.replace(tmp, EMBEDDINGS_FILE)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Public API ─────────────────────────────────────────────────────────────────

def embed_and_store(thought_id: str, text: str) -> bool:
    """
    Embed a single thought and persist it.
    Returns True on success, False if sentence-transformers not available.
    Called by capture_thought() on every new capture.
    """
    vec = _embed(text)
    if vec is None:
        return False
    embs = _load_embeddings()
    embs[thought_id] = vec
    _save_embeddings(embs)
    return True


def semantic_search_thoughts(
    query: str,
    top_k: int = 5,
    category: str = "",
    min_score: float = 0.30,
) -> list[dict]:
    """
    Return the top-k most semantically similar thoughts to query.

    Each result: { "id": "t00001", "score": 0.82 }
    Caller looks up thought text from thoughts.json.
    Returns [] if sentence-transformers not installed or no embeddings exist.
    """
    query_vec = _embed(query)
    if query_vec is None:
        return []

    embs = _load_embeddings()
    if not embs:
        return []

    # If category filter requested, load thought metadata
    cat_filter: set = set()
    if category:
        try:
            from agents.thoughts import _load as load_thoughts
            cat_filter = {
                t["id"] for t in load_thoughts()
                if t.get("category", "") == category.lower()
            }
        except Exception:
            pass

    scores = []
    for tid, vec in embs.items():
        if cat_filter and tid not in cat_filter:
            continue
        score = _cosine(query_vec, vec)
        if score >= min_score:
            scores.append({"id": tid, "score": round(score, 4)})

    scores.sort(key=lambda x: x["score"], reverse=True)
    return scores[:top_k]


def embedding_stats() -> dict:
    """Return { "total": int, "model_loaded": bool }."""
    embs = _load_embeddings()
    return {
        "total": len(embs),
        "model_loaded": _MODEL is not None,
    }
