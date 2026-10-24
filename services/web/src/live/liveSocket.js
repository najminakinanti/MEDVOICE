// WebSocket pratinjau langsung: autentikasi lewat pesan pertama (token tidak masuk URL/log), sambung ulang otomatis.
const PING_MS = 20000;

export function createLiveSocket({ sessionId, getToken, onMessage, onState, onReady }) {
  let ws = null, state = "connecting", closed = false, retry = 0, retryTimer = null, pingTimer = null;
  const url = () => (location.protocol === "https:" ? "wss://" : "ws://") + location.host + `/v1/sessions/${sessionId}/live/ws`;
  const set = (s) => { if (s !== state) { state = s; onState(s); } };

  function open() {
    if (closed) return;
    ws = new WebSocket(url());
    ws.binaryType = "arraybuffer";
    ws.onopen = () => ws.send(JSON.stringify({ t: "auth", token: getToken() }));
    ws.onmessage = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch { return; }
      if (m.t === "ready") { retry = 0; set("ready"); onReady(); return; }
      if (m.t === "error" && m.code === "stt_unavailable") { set("unavailable"); return; }
      onMessage(m);
    };
    ws.onclose = (ev) => {
      clearInterval(pingTimer);
      if (closed) return;
      if (ev.code === 4401) { set("denied"); return; }                       // token/sesi ditolak: jangan mencoba terus
      set(ev.code === 4503 ? "unavailable" : "reconnecting");
      retryTimer = setTimeout(open, Math.min(5000, 500 * 2 ** retry++));
    };
    ws.onerror = () => { /* onclose menangani */ };
    pingTimer = setInterval(() => { if (ws && ws.readyState === 1) ws.send('{"t":"ping"}'); }, PING_MS);
  }
  open();

  const ready = () => state === "ready" && ws && ws.readyState === 1;
  return {
    get state() { return state; },
    ready,
    send(obj) { if (ready()) ws.send(JSON.stringify(obj)); },
    sendAudio(ch, pcm16) {
      if (!ready()) return;
      const buf = new Uint8Array(1 + pcm16.byteLength);
      buf[0] = ch; buf.set(new Uint8Array(pcm16.buffer, pcm16.byteOffset, pcm16.byteLength), 1);
      ws.send(buf);
    },
    close() {
      closed = true; clearTimeout(retryTimer); clearInterval(pingTimer);
      try { if (ws && ws.readyState === 1) ws.send('{"t":"bye"}'); ws && ws.close(1000); } catch { /* sudah tertutup */ }
    },
  };
}
