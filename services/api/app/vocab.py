from functools import lru_cache
from pathlib import Path

from .config import get_settings


def _read(name: str) -> list[str]:
    p = Path(get_settings().vocab_dir) / name
    if not p.exists():
        return []
    return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


@lru_cache
def vocab_terms() -> list[str]:
    return _read("vocab.txt")


@lru_cache
def drug_names() -> list[str]:
    return _read("drugs.txt")


def initial_prompt() -> str:
    """Kosakata medis untuk initial_prompt Whisper."""
    return "Percakapan dokter dan pasien. Istilah: " + ", ".join(vocab_terms() + drug_names()) + "."
