"""
Persistent semantic search over ontology entities.

Uses provider embeddings through LiteLLM when configured and falls back to a
deterministic local hashing embedding so search still works without API keys.
"""
from __future__ import annotations

import asyncio
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from litellm import aembedding
from sklearn.feature_extraction.text import HashingVectorizer

from app.core.config import settings
from app.services import ontology_service

LOCAL_MODEL_NAME = "local-hash-v1"
LOCAL_DIMENSIONS = 256
_local_vectorizer = HashingVectorizer(
    n_features=LOCAL_DIMENSIONS,
    alternate_sign=False,
    norm=None,
    ngram_range=(1, 2),
)


def _storage_dir(*, db_path: str | Path | None = None, project_id: str | None = None) -> Path:
    if db_path:
        candidate = Path(db_path)
        if candidate.exists():
            return candidate.parent
    current_db = ontology_service.get_db_path(project_id)
    if current_db and Path(current_db).exists():
        return Path(current_db).parent
    return settings.engine_root / "ontology"


def _index_path(*, db_path: str | Path | None = None, project_id: str | None = None) -> Path:
    return _storage_dir(db_path=db_path, project_id=project_id) / "embeddings.db"


def is_ready(db_path: str | Path | None = None, *, project_id: str | None = None) -> bool:
    return _index_path(db_path=db_path, project_id=project_id).exists()


async def build_index(db_path: str | Path | None = None, *, project_id: str | None = None) -> None:
    docs = await ontology_service._run(project_id, ontology_service.list_search_documents)
    if not docs:
        raise RuntimeError("No ontology entities available to index")

    # Dedupe by the key used as the SQLite primary key.
    # An individual can be returned multiple times because Owlready2 reports subclass
    # instances in parent class `.instances()` too (e.g. Faculty is also AcademicPerson),
    # but our serialized `entity["class"]` is the concrete type, so duplicates collide.
    unique: dict[str, dict[str, Any]] = {}
    for doc in docs:
        try:
            ent = doc.get("entity") or {}
            key = f'{ent.get("class")}:{ent.get("id")}'
        except Exception:
            continue
        if key not in unique:
            unique[key] = doc

    docs = list(unique.values())
    texts = [doc["text"] for doc in docs]
    model_name, vectors = await _embed_texts(texts)
    await asyncio.to_thread(
        _write_index,
        _index_path(db_path=db_path, project_id=project_id),
        model_name,
        docs,
        vectors,
    )


async def search(
    query: str,
    top_k: int = 20,
    types: list[str] | None = None,
    *,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    q = query.strip()
    if not q:
        return []

    index_path = _index_path(project_id=project_id)
    if not index_path.exists():
        await build_index(ontology_service.get_db_path(project_id), project_id=project_id)

    payload = await asyncio.to_thread(_read_index, index_path)
    model_name = payload["model_name"]
    query_vector = (await _embed_texts([q], model_name=model_name))[1][0]

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in payload["rows"]:
        if types and row["class"] not in types:
            continue
        score = _cosine_similarity(query_vector, row["vector"])
        if score <= 0:
            continue
        scored.append((score, row["entity"]))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [entity for _, entity in scored[:top_k]]


async def _embed_texts(
    texts: list[str],
    model_name: str | None = None,
) -> tuple[str, list[list[float]]]:
    selected_model = model_name or settings.embedding_model
    if selected_model != LOCAL_MODEL_NAME and _has_embedding_provider():
        try:
            response = await aembedding(model=selected_model, input=texts)
            return selected_model, [list(item["embedding"]) for item in response["data"]]
        except Exception:
            pass

    return LOCAL_MODEL_NAME, _local_embed(texts)


def _local_embed(texts: list[str]) -> list[list[float]]:
    matrix = _local_vectorizer.transform(texts)
    vectors: list[list[float]] = []
    for row in matrix:
        dense = row.toarray()[0].astype("float32")
        norm = float(math.sqrt(float((dense * dense).sum())))
        if norm:
            dense = dense / norm
        vectors.append(dense.tolist())
    return vectors


def _has_embedding_provider() -> bool:
    return bool(
        settings.openai_api_key
        or settings.anthropic_api_key
        or settings.google_api_key
        or settings.openrouter_api_key
    )


def _write_index(
    path: Path,
    model_name: str,
    docs: list[dict[str, Any]],
    vectors: list[list[float]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE IF EXISTS embeddings")
        conn.execute("DROP TABLE IF EXISTS metadata")
        conn.execute(
            """
            CREATE TABLE metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE embeddings (
              id TEXT PRIMARY KEY,
              class TEXT NOT NULL,
              entity_json TEXT NOT NULL,
              vector_json TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            [
                ("model_name", model_name),
                ("dimensions", str(len(vectors[0]) if vectors else 0)),
            ],
        )
        conn.executemany(
            """
            INSERT INTO embeddings (id, class, entity_json, vector_json)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    f'{doc["entity"]["class"]}:{doc["entity"]["id"]}',
                    doc["entity"]["class"],
                    json.dumps(doc["entity"]),
                    json.dumps(vector),
                )
                for doc, vector in zip(docs, vectors, strict=True)
            ],
        )
        conn.commit()


def _read_index(path: Path) -> dict[str, Any]:
    with sqlite3.connect(path) as conn:
        model_name = conn.execute(
            "SELECT value FROM metadata WHERE key = 'model_name'"
        ).fetchone()
        if not model_name:
            raise RuntimeError("Semantic index metadata missing")
        rows = conn.execute(
            "SELECT class, entity_json, vector_json FROM embeddings"
        ).fetchall()

    return {
        "model_name": model_name[0],
        "rows": [
            {
                "class": row[0],
                "entity": json.loads(row[1]),
                "vector": json.loads(row[2]),
            }
            for row in rows
        ],
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    return float(sum(a * b for a, b in zip(left, right, strict=True)))
