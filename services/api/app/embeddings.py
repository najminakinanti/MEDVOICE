"""Embedding lewat Ollama (bge-m3, multibahasa). Dijalankan di CPU agar tidak menggusur LLM dari VRAM."""
import httpx

from .config import get_settings


class EmbeddingError(Exception):
    pass


def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    try:
        r = httpx.post(s.llm_base_url.rstrip("/") + "/api/embed",
                       json={"model": s.embedding_model, "input": texts,
                             "options": {"num_gpu": 0 if s.embedding_cpu else 99, "num_ctx": 512}, "keep_alive": "30m"},
                       timeout=s.llm_timeout_s)
        r.raise_for_status()
        out = r.json()["embeddings"]
    except httpx.HTTPError as e:
        raise EmbeddingError(type(e).__name__) from None
    if len(out) != len(texts) or any(len(v) != s.embedding_dim for v in out):
        raise EmbeddingError("bad_dimension")
    return out


def to_pgvector(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
