from .base import SimrsAdapter, SubmitResult
from .mock import MockAdapter

_REGISTRY: dict[str, SimrsAdapter] = {"mock": MockAdapter()}


def register(adapter: SimrsAdapter) -> None:
    _REGISTRY[adapter.name] = adapter


def adapter_names() -> list[str]:
    return sorted(_REGISTRY)


def get_adapter(name: str) -> SimrsAdapter:
    if name not in _REGISTRY:
        raise KeyError(name)
    return _REGISTRY[name]


__all__ = ["SimrsAdapter", "SubmitResult", "adapter_names", "get_adapter", "register"]
