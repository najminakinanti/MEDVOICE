import time
from collections import defaultdict

from .config import get_settings

_mem: dict[str, int] = defaultdict(int)
_redis = None


def _client():
    global _redis
    url = get_settings().redis_url
    if not url:
        return None
    if _redis is None:
        import redis
        _redis = redis.Redis.from_url(url, socket_timeout=2)
    return _redis


def allow(client_id: str, limit_per_min: int) -> bool:
    """Fixed window per menit per client. Tanpa Redis -> memori proses (hanya dev/tes)."""
    window = int(time.time() // 60)
    key = f"rl:{client_id}:{window}"
    r = _client()
    if r is None:
        _mem[key] += 1
        return _mem[key] <= limit_per_min
    try:
        n = r.incr(key)
        if n == 1:
            r.expire(key, 90)
        return n <= limit_per_min
    except Exception:
        return True  # Redis down: jangan blokir pelayanan klinis; tercatat di monitoring infra
