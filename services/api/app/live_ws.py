"""Pratinjau transkrip langsung lewat WebSocket: browser -> API -> layanan STT (/stream) dan sebaliknya.

Browser tidak bisa mengirim header Authorization pada WebSocket; token dikirim sebagai pesan PERTAMA
({"t":"auth","token":...}) supaya tidak masuk URL/log. Audio & teks pratinjau tidak disimpan di mana pun
(SOAP dibuat dari rekaman penuh setelah Selesai)."""
import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from . import ratelimit
from .config import get_settings
from .db import engine
from .deps import load_session, principal_from

router = APIRouter(prefix="/v1")
MAX_FRAME_BYTES = 64 * 1024          # ~2 dtk audio 16 kHz/16-bit per pesan
IDLE_TIMEOUT_S = 90                  # tanpa pesan apa pun (termasuk detak) -> tutup
AUTH_TIMEOUT_S = 10


def _authorize(token: str, session_id: str, origin: str | None, host: str | None, ip: str | None) -> bool:
    """Dokter pemilik sesi (atau token widget untuk sesi ini) dan sesi masih merekam. Koneksi DB dilepas segera."""
    with engine().begin() as conn:
        try:
            p = principal_from(conn, key=None, auth="Bearer " + token, origin=origin, host=host, ip=ip)
            if p.kind != "doctor":
                return False
            s = load_session(conn, p, session_id)
        except HTTPException:
            return False
        return s["status"] == "recording"


def _stt_ws_url() -> str:
    u = get_settings().stt_url.rstrip("/")
    return ("wss" if u.startswith("https") else "ws") + "://" + u.split("://", 1)[1] + "/stream"


@router.websocket("/sessions/{session_id}/live/ws")
async def live_ws(ws: WebSocket, session_id: str):
    import websockets

    from . import vocab
    await ws.accept()
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), AUTH_TIMEOUT_S))
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect, RuntimeError):
        await _close(ws, 4401)
        return
    ip = ws.client.host if ws.client else None
    ok = (first.get("t") == "auth" and isinstance(first.get("token"), str) and ratelimit.allow(f"livews:{ip}", 30)
          and await asyncio.to_thread(_authorize, first["token"], session_id, ws.headers.get("origin"),
                                      ws.headers.get("host"), ip))
    if not ok:
        await _close(ws, 4401)
        return
    cfg = get_settings()
    try:
        up = await asyncio.wait_for(websockets.connect(_stt_ws_url(), max_size=1 << 20, open_timeout=5), 8)
    except Exception:  # noqa: BLE001 - STT mati/belum siap: UI tetap merekam, hanya pratinjau yang hilang
        await ws.send_text(json.dumps({"t": "error", "code": "stt_unavailable"}))
        await _close(ws, 4503)
        return
    await up.send(json.dumps({"t": "config", "language": cfg.stt_language, "prompt": vocab.initial_prompt()}))
    await ws.send_text(json.dumps({"t": "ready"}))

    async def client_to_stt():
        while True:
            m = await asyncio.wait_for(ws.receive(), IDLE_TIMEOUT_S)
            if m["type"] == "websocket.disconnect":
                return
            if m.get("bytes") is not None:
                if len(m["bytes"]) <= MAX_FRAME_BYTES:
                    await up.send(m["bytes"])
            elif m.get("text"):
                try:
                    d = json.loads(m["text"])
                except ValueError:
                    continue
                if d.get("t") in ("start", "end", "bye"):        # hanya perintah yang dikenal diteruskan
                    await up.send(json.dumps({k: d[k] for k in ("t", "ch", "id") if k in d}))
                    if d["t"] == "bye":
                        return
                # {"t":"ping"} cukup mereset idle timeout

    async def stt_to_client():
        async for msg in up:
            if isinstance(msg, str):
                await ws.send_text(msg)

    tasks = [asyncio.create_task(client_to_stt()), asyncio.create_task(stt_to_client())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await up.close()
        await _close(ws, 1000)


async def _close(ws: WebSocket, code: int) -> None:
    try:
        await ws.close(code)
    except Exception:  # noqa: BLE001 - sudah tertutup
        pass

