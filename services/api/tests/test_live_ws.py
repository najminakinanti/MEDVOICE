"""WebSocket pratinjau langsung: autentikasi lewat pesan pertama + proksi ke layanan STT (STT disimulasikan)."""
import asyncio
import json
import threading

import pytest
import websockets
from starlette.websockets import WebSocketDisconnect

from tests.conftest import login


@pytest.fixture()
def fake_stt(monkeypatch):
    """Server WebSocket kecil yang meniru /stream: membalas 'final' saat menerima 'end'."""
    got, ready = [], threading.Event()
    box = {}

    async def handler(ws):
        async for m in ws:
            got.append(m)
            if isinstance(m, str) and json.loads(m).get("t") == "end":
                await ws.send(json.dumps({"t": "final", "ch": 0, "id": 1, "text": "halo dok"}))

    def run():
        async def main():
            async with websockets.serve(handler, "127.0.0.1", 0) as srv:
                box["port"] = srv.sockets[0].getsockname()[1]
                box["stop"] = asyncio.Event()
                box["loop"] = asyncio.get_running_loop()
                ready.set()
                await box["stop"].wait()
        asyncio.run(main())

    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert ready.wait(5)
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "stt_url", f"http://127.0.0.1:{box['port']}")
    yield got
    box["loop"].call_soon_threadsafe(box["stop"].set)


def _session(client, tenant):
    h = login(client, tenant)
    r = client.post("/v1/sessions", headers=h, json={"no_rawat": "WS/1", "consent": {"given": True, "recorded_by": "t"}})
    assert r.status_code == 201
    return h, r.json()["id"]


def test_ws_proksi_audio_dan_teks_final(client, tenant, fake_stt):
    h, sid = _session(client, tenant)
    token = h["Authorization"].split()[1]
    with client.websocket_connect(f"/v1/sessions/{sid}/live/ws") as ws:
        ws.send_text(json.dumps({"t": "auth", "token": token}))
        assert ws.receive_json() == {"t": "ready"}
        ws.send_text(json.dumps({"t": "start", "ch": 0, "id": 1, "x": "diabaikan"}))
        ws.send_bytes(b"\x00" + b"\x01\x00" * 800)
        ws.send_text(json.dumps({"t": "evil", "ch": 0}))                  # perintah tak dikenal tidak diteruskan
        ws.send_text(json.dumps({"t": "end", "ch": 0, "id": 1}))
        assert ws.receive_json() == {"t": "final", "ch": 0, "id": 1, "text": "halo dok"}
    cfg = json.loads(fake_stt[0])
    assert cfg["t"] == "config" and cfg["language"] == "id" and "Istilah" in cfg["prompt"]
    kinds = [json.loads(m)["t"] if isinstance(m, str) else "audio" for m in fake_stt[1:]]
    assert kinds == ["start", "audio", "end"]
    assert "x" not in json.loads(fake_stt[1])


def test_ws_tolak_tanpa_token_token_salah_dan_sesi_tidak_merekam(client, tenant, fake_stt):
    h, sid = _session(client, tenant)
    for first in ({"t": "auth", "token": "bukan-token"}, {"t": "hello"}):
        with client.websocket_connect(f"/v1/sessions/{sid}/live/ws") as ws:
            ws.send_text(json.dumps(first))
            with pytest.raises(WebSocketDisconnect) as e:
                ws.receive_json()
            assert e.value.code == 4401
    other = login(client, tenant, "dr_b")["Authorization"].split()[1]       # dokter lain: sesi bukan miliknya
    with client.websocket_connect(f"/v1/sessions/{sid}/live/ws") as ws:
        ws.send_text(json.dumps({"t": "auth", "token": other}))
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401
    assert fake_stt == []                                                  # tidak ada yang sampai ke STT


def test_ws_stt_mati_memberi_kode_galat_bukan_menggantung(client, tenant, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "stt_url", "http://127.0.0.1:1")
    h, sid = _session(client, tenant)
    with client.websocket_connect(f"/v1/sessions/{sid}/live/ws") as ws:
        ws.send_text(json.dumps({"t": "auth", "token": h["Authorization"].split()[1]}))
        assert ws.receive_json() == {"t": "error", "code": "stt_unavailable"}
