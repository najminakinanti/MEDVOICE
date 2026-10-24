// Perekaman + transkrip langsung. Dua jalur paralel dari mikrofon yang sama:
//  1) MediaRecorder -> rekaman penuh berkualitas (diunggah saat Selesai; sumber SOAP).
//  2) AudioWorklet -> detektor ucapan -> WebSocket -> teks sementara & akhir (HANYA tampilan, tidak disimpan).
import { computed, onBeforeUnmount, ref } from "vue";
import { api, auth } from "../api.js";
import { openSource } from "./capture.js";
import { openMic, recorderExt } from "./devices.js";
import { createLiveSocket } from "./liveSocket.js";

export const SPEAKER_LABEL = { dokter: "Dokter", pasien: "Pasien", tidak_diketahui: "Suara" };
const FINAL_TIMEOUT_MS = 25000;   // teks akhir tak kunjung datang: pakai teks sementara terakhir
const LEVEL_BARS = 30;

export function useRecording(sessionId) {
  const status = ref("idle");          // idle | starting | recording | paused | uploading | error
  const error = ref("");
  const elapsedMs = ref(0);
  const levels = ref(Array(LEVEL_BARS).fill(0));
  const sttState = ref("connecting");  // connecting | ready | reconnecting | unavailable | denied
  const modelState = ref("");          // "loading" | "ready" (dari layanan STT)
  const bubbles = ref([]);
  const micLabel = ref("");
  const dual = ref(false);
  const noSpeech = ref(false);         // >8 dtk merekam tetapi belum ada suara terdeteksi (mikrofon bisu/terlalu jauh/salah perangkat)
  const canRetry = ref(false);         // unggahan gagal tetapi rekaman masih di memori

  let sources = [], streams = [], recorders = [], parts = [], sock = null;
  let active = {};                       // ch -> {id,startMs} ucapan yang sedang berjalan
  let spoke = false, tick = null, sweep = null, lvTimer = null, lastRms = 0, t0 = 0, acc = 0;

  const byKey = (ch, id) => bubbles.value.find((b) => b.ch === ch && b.id === id);
  const ordered = computed(() => [...bubbles.value].sort((a, b) => a.startMs - b.startMs || a.ch - b.ch));
  const speakerOf = (ch) => (dual.value ? (ch === 0 ? "dokter" : "pasien") : "tidak_diketahui");

  function addBubble(ch, id, startMs) {
    bubbles.value.push({ ch, id, startMs, speaker: speakerOf(ch), wall: Date.now(), stable: "", tail: "", text: "", state: "listening", endedAt: 0 });
  }

  function onMessage(m) {
    if (m.t === "status") { modelState.value = m.state; return; }
    const b = byKey(m.ch, m.id);
    if (!b) return;
    if (m.t === "partial" && b.state !== "final") { b.stable = m.stable; b.tail = m.tail; b.state = "partial"; }
    else if (m.t === "final") { b.text = m.text; b.state = "final"; }
    else if (m.t === "drop") bubbles.value = bubbles.value.filter((x) => x !== b);
  }

  function startSocket() {
    sock = createLiveSocket({
      sessionId: sessionId(), getToken: () => auth.token, onMessage,
      onState: (s) => { sttState.value = s; },
      onReady: () => {                    // (re)connect: ucapan yang sedang berjalan dikenalkan lagi ke server
        for (const [ch, u] of Object.entries(active)) {
          if (!u) continue;
          sock.send({ t: "start", ch: Number(ch), id: u.id, start_ms: u.startMs });
          if (!byKey(Number(ch), u.id)) addBubble(Number(ch), u.id, u.startMs);
        }
      },
    });
  }

  async function begin(devices) {
    const pair = devices.pasien ? [devices.dokter, devices.pasien] : [devices.dokter];
    dual.value = pair.length === 2;
    if (dual.value && devices.dokter && devices.dokter === devices.pasien) throw new Error("Mikrofon dokter dan pasien tidak boleh perangkat yang sama.");
    streams = [];
    for (const id of pair) streams.push(await openMic(id));
    micLabel.value = streams[0].getAudioTracks()[0]?.label || "Mikrofon";
    recorders = streams.map((s) => {
      const r = new MediaRecorder(s), bucket = [];
      r.ondataavailable = (e) => { if (e.data.size) bucket.push(e.data); };
      parts.push(bucket); r.start(2000);
      return r;
    });
    startSocket();
    for (let ch = 0; ch < streams.length; ch++) {
      sources.push(await openSource(streams[ch], {
        onLevel: (r) => { if (r > lastRms) lastRms = r; },
        onStart: ({ id, startMs }) => {
          spoke = true; noSpeech.value = false;
          active[ch] = { id, startMs };
          if (sock.ready()) { sock.send({ t: "start", ch, id, start_ms: startMs }); addBubble(ch, id, startMs); }
        },
        onAudio: (pcm) => sock.sendAudio(ch, pcm),
        onEnd: ({ id, discard }) => {
          active[ch] = null;
          const b = byKey(ch, id);
          if (sock.ready()) sock.send({ t: "end", ch, id });
          if (!b) return;
          if (discard) bubbles.value = bubbles.value.filter((x) => x !== b);
          else b.endedAt = Date.now();
        },
      }));
    }
  }

  function startTimers() {
    t0 = performance.now();
    tick = setInterval(() => {
      elapsedMs.value = acc + (performance.now() - t0);
      if (!spoke && status.value === "recording" && elapsedMs.value > 8000) noSpeech.value = true;
    }, 200);
    lvTimer = setInterval(() => {
      const v = Math.min(1, Math.sqrt(lastRms) * 3.2); lastRms = 0;
      levels.value = [...levels.value.slice(1), status.value === "paused" ? 0 : v];
    }, 80);
    sweep = setInterval(() => {
      const now = Date.now();
      for (const b of [...bubbles.value]) {
        if (b.endedAt && b.state !== "final" && now - b.endedAt > FINAL_TIMEOUT_MS) {
          b.text = (b.stable + " " + b.tail).trim(); b.state = "final";
          if (!b.text) bubbles.value = bubbles.value.filter((x) => x !== b);
        }
      }
    }, 2000);
  }
  const stopTimers = () => { clearInterval(tick); clearInterval(lvTimer); clearInterval(sweep); };

  async function start(devices) {
    if (status.value !== "idle" && status.value !== "error") return;
    status.value = "starting"; error.value = "";
    try {
      api(`/sessions/${sessionId()}/warmup`, { method: "POST" }).catch(() => {});   // siapkan model STT (dan VRAM bila digilir)
      await begin(devices);
      acc = 0; startTimers(); status.value = "recording";
    } catch (e) {
      release();
      status.value = "error";
      error.value = e && e.name === "NotAllowedError" ? "Izin mikrofon ditolak. Izinkan mikrofon pada browser lalu coba lagi."
        : e && e.name === "NotFoundError" ? "Mikrofon tidak ditemukan." : (e && e.message) || "Mikrofon tidak bisa diakses.";
    }
  }

  function pause() {
    if (status.value !== "recording") return;
    acc += performance.now() - t0; elapsedMs.value = acc;
    recorders.forEach((r) => r.state === "recording" && r.pause());
    sources.forEach((s) => s.setPaused(true));
    status.value = "paused";
  }
  function resume() {
    if (status.value !== "paused") return;
    t0 = performance.now();
    recorders.forEach((r) => r.state === "paused" && r.resume());
    sources.forEach((s) => s.setPaused(false));
    status.value = "recording";
  }

  function release() {
    stopTimers();
    sources.forEach((s) => s.close()); sources = [];
    if (sock) { sock.close(); sock = null; }
    streams.forEach((s) => s.getTracks().forEach((t) => t.stop())); streams = [];
  }

  /** Hentikan, unggah rekaman penuh, lalu minta pemrosesan. Bila gagal, rekaman tetap di memori untuk dicoba lagi. */
  async function stop() {
    if (status.value !== "recording" && status.value !== "paused") return false;
    if (status.value === "recording") acc += performance.now() - t0;
    elapsedMs.value = acc;
    status.value = "uploading"; error.value = "";
    sources.forEach((s) => s.close()); sources = [];
    if (sock) { sock.close(); sock = null; }
    stopTimers();
    await Promise.all(recorders.map((r) => new Promise((res) => { if (r.state === "inactive") return res(); r.onstop = res; r.stop(); })));
    streams.forEach((s) => s.getTracks().forEach((t) => t.stop())); streams = [];
    return upload();
  }

  async function upload() {
    status.value = "uploading";
    try {
      const fd = new FormData();
      const blob = (i) => new Blob(parts[i], { type: recorders[i].mimeType || "audio/webm" });
      const ext = recorderExt(recorders[0].mimeType);
      if (recorders.length === 2) { fd.append("dokter", blob(0), `dokter.${ext}`); fd.append("pasien", blob(1), `pasien.${ext}`); }
      else fd.append("mixed", blob(0), `rekaman.${ext}`);
      await api(`/sessions/${sessionId()}/audio`, { method: "POST", body: fd });
      await api(`/sessions/${sessionId()}/finish`, { method: "POST" });
      status.value = "done"; parts = []; canRetry.value = false;
      return true;
    } catch (e) {
      status.value = "error"; canRetry.value = true; error.value = "Gagal mengirim rekaman: " + (e.detail || e.message) + ". Rekaman masih tersimpan di halaman ini; coba kirim lagi.";
      return false;
    }
  }

  onBeforeUnmount(() => { release(); recorders.forEach((r) => r.state !== "inactive" && r.stop()); });

  return { status, error, elapsedMs, levels, sttState, modelState, bubbles: ordered, micLabel, dual, noSpeech, start, pause, resume, stop, upload, canRetry };
}

/** Unggah file audio yang sudah ada (alternatif merekam langsung). */
export async function uploadFiles(sessionId, { dokter, pasien, mixed }) {
  const fd = new FormData();
  if (dokter && pasien) { fd.append("dokter", dokter, dokter.name); fd.append("pasien", pasien, pasien.name); }
  else if (mixed) fd.append("mixed", mixed, mixed.name);
  else throw Object.assign(new Error("Pilih file dokter + pasien, atau satu file campuran."), { detail: "Pilih file dokter + pasien, atau satu file campuran." });
  await api(`/sessions/${sessionId}/audio`, { method: "POST", body: fd });
  await api(`/sessions/${sessionId}/finish`, { method: "POST" });
}
