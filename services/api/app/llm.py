"""Satu-satunya pintu ke LLM. Backend diganti lewat LLM_BACKEND. LLM tidak punya akses tool/DB:
fungsi ini hanya mengembalikan teks, yang selalu divalidasi kode sesudahnya."""
import httpx

from .config import get_settings


class LLMError(Exception):
    pass


def call_llm(system: str, user: str, *, json_mode: bool = True, model: str | None = None) -> str:
    s = get_settings()
    model = model or s.llm_model
    if not model:
        raise LLMError("llm_model_not_set")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        if s.llm_backend == "ollama":
            body = {"model": model, "stream": False, "messages": messages,
                    "options": {"temperature": 0, "num_ctx": s.llm_num_ctx}}
            if json_mode:
                body["format"] = "json"
            r = httpx.post(s.llm_base_url.rstrip("/") + "/api/chat", json=body, timeout=s.llm_timeout_s)
            r.raise_for_status()
            return r.json()["message"]["content"]
        if s.llm_backend == "openai":
            body = {"model": model, "temperature": 0, "messages": messages}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            headers = {"Authorization": f"Bearer {s.llm_api_key}"} if s.llm_api_key else {}
            r = httpx.post(s.llm_base_url.rstrip("/") + "/v1/chat/completions", json=body,
                           headers=headers, timeout=s.llm_timeout_s)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except httpx.HTTPError as e:
        raise LLMError(type(e).__name__) from None   # tanpa pesan: bisa memuat isi transkrip
    raise LLMError("llm_backend_unknown")


def unload_llm() -> None:
    """Bongkar LLM (dan embedding) dari VRAM agar STT di GPU punya ruang. Hanya Ollama; galat diabaikan."""
    s = get_settings()
    if s.llm_backend != "ollama":
        return
    for model in {s.llm_model, s.embedding_model} - {""}:
        try:
            httpx.post(s.llm_base_url.rstrip("/") + "/api/generate", json={"model": model, "keep_alive": 0}, timeout=15)
        except httpx.HTTPError:
            pass
