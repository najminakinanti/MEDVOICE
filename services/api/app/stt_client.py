import httpx

from .config import get_settings


class STTError(Exception):
    pass


def transcribe(path: str, initial_prompt: str, live=False) -> dict:
    """Kirim satu file audio ke layanan STT. Return {"model","language","segments":[{start_ms,end_ms,text}]}."""
    s = get_settings()
    try:
        with open(path, "rb") as f:
            r = httpx.post(s.stt_url.rstrip("/") + "/transcribe",
                           files={"file": (path.rsplit("/", 1)[-1], f)},
                           data={"language": s.stt_language, "initial_prompt": initial_prompt, "live": {"partial": "p", "refine": "r"}.get(live, "1" if live else "")},
                           timeout=60 if live else s.stt_timeout_s)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        raise STTError(type(e).__name__) from None


def _post_quiet(path: str, timeout: float = 15.0) -> dict | None:
    try:
        r = httpx.post(get_settings().stt_url.rstrip("/") + path, timeout=timeout)
        return r.json() if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


def warmup() -> None:
    """Minta STT memuat model (abaikan galat; pratinjau opsional)."""
    _post_quiet("/warmup")


def unload() -> None:
    """Minta STT membebaskan VRAM sebelum LLM bekerja (abaikan galat)."""
    _post_quiet("/unload")
