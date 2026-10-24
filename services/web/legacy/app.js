"use strict";
// Tidak ada API key/rahasia di sini. Token dokter hanya disimpan di memori halaman.
const API = "/v1";
let procShown = false, token = null, sessionId = null, review = null, recorder = null, chunks = [], stream = null;
const $ = (id) => document.getElementById(id);
const VIEWS = ["vLogin", "vStart", "vRecord", "vProcessing", "vReview"];
const SEC_NAME = { S: "Subjective", O: "Objective", A: "Assessment", P: "Plan" };
const NOTICE_TEXT = {
  stt_kosong_isi_manual: "Transkrip kosong. Isi SOAP secara manual.",
  json_llm_rusak_isi_manual: "Ekstraksi otomatis gagal dua kali. Isi SOAP secara manual.",
  kualitas_draft_rendah: "Peringatan: kualitas draft rendah (banyak butir ditolak validator). Periksa dengan teliti.",
  pipeline_gagal_isi_manual: "Pemrosesan otomatis gagal. Isi SOAP secara manual.",
  transkrip_sudah_dihapus_sesuai_retensi: "Transkrip sudah dihapus sesuai kebijakan retensi.",
};

function show(name) {
  VIEWS.forEach((v) => $(v).classList.toggle("hidden", v !== name));
  if (name === "vRecord") { fillDevices(); if (sessionId && token) api(`/sessions/${sessionId}/warmup`, { method: "POST" }).catch(() => {}); }
  if (name === "vRecord" || name === "vStart") { procShown = false; $("procChat").classList.add("hidden"); }
}
const EMBED = new URLSearchParams(location.search).get("embed") === "1";
function emit(type) {   // hanya id & status (tanpa data klinis) ke halaman induk saat disematkan sebagai widget
  if (!EMBED || window.parent === window) return;
  let target = "*"; try { target = new URL(document.referrer).origin; } catch (e) { /* tanpa referrer */ }
  window.parent.postMessage({ source: "medvoice", type, sessionId, status: review && review.session ? review.session.status : null }, target);
}
function msg(text, bad) {
  const box = $("msg"); box.textContent = "";
  if (!text) return;
  const d = document.createElement("div"); d.className = "banner" + (bad ? " bad" : ""); d.textContent = text; box.appendChild(d);
}
async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (token) headers["Authorization"] = "Bearer " + token;
  if (opts.json) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const r = await fetch(API + path, Object.assign({}, opts, { headers }));
  let data = null; try { data = await r.json(); } catch (e) { /* kosong */ }
  if (!r.ok) { const err = new Error((data && data.detail) || r.statusText); err.status = r.status; throw err; }
  return data;
}
function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  Object.entries(props).forEach(([k, v]) => { if (k === "class") e.className = v; else if (k === "text") e.textContent = v; else e[k] = v; });
  kids.forEach((k) => e.appendChild(k)); return e;
}
const fmt = (ms) => { const s = Math.floor(ms / 1000); return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); };

// ---- login
$("btnLogin").onclick = async () => {
  try {
    const d = await api("/auth/login", { method: "POST", json: { client: $("lClient").value, username: $("lUser").value, password: $("lPass").value } });
    token = d.access_token; $("lPass").value = ""; $("who").textContent = $("lUser").value;
    $("btnLogout").classList.remove("hidden"); msg(""); show("vStart");
  } catch (e) { msg(e.status === 429 ? "Terlalu banyak percobaan. Coba lagi nanti." : "Login gagal.", true); }
};
$("btnLogout").onclick = () => { token = null; sessionId = null; $("btnLogout").classList.add("hidden"); $("who").textContent = ""; show("vLogin"); };

// ---- mulai sesi & rekam
$("btnStart").onclick = async () => {
  if (!$("sConsent").checked) return msg("Consent pasien wajib dicentang sebelum merekam.", true);
  try {
    const d = await api("/sessions", { method: "POST", json: { no_rawat: $("sRawat").value, consent: { given: true, recorded_by: $("sBy").value || "-" } } });
    sessionId = d.id; msg(""); show("vRecord");
  } catch (e) { msg("Gagal memulai sesi: " + e.message, true); }
};
$("btnOpen").onclick = () => { sessionId = $("sOpen").value.trim(); loadOrPoll(); };
// ---- perangkat mikrofon: satu mikrofon (mixed) atau dua (dokter + pasien -> label pembicara pasti)
async function fillDevices() {
  try {
    const tmp = await navigator.mediaDevices.getUserMedia({ audio: true }); tmp.getTracks().forEach((t) => t.stop());
    const devs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
    ["devDokter", "devPasien"].forEach((id, n) => {
      const sel = $(id); sel.textContent = "";
      if (n === 1) sel.appendChild(el("option", { value: "", text: "(tidak ada - satu mikrofon)" }));
      devs.forEach((d, i) => sel.appendChild(el("option", { value: d.deviceId, text: d.label || "Mikrofon " + (i + 1) })));
    });
  } catch (e) { /* izin ditolak: pemilihan perangkat tidak tersedia */ }
}
const rec = { main: null, second: null, streams: [], parts: { main: [], second: [] }, live: false };
function newRecorder(stream, bucket) {
  const r = new MediaRecorder(stream); bucket.length = 0;
  r.ondataavailable = (e) => { if (e.data.size) bucket.push(e.data); };
  r.start(); return r;
}
// ---- chat: tiap ucapan = satu gelembung (dokter kiri, pasien kanan, tak dikenal tengah)
const SPEAKER_LABEL = { dokter: "Dokter", pasien: "Pasien", tidak_diketahui: "Suara" };
const SPEAKER_ORDER = { dokter: 0, pasien: 1, tidak_diketahui: 2 };
function bubble(speaker, ms, text, extraClass) {
  return el("div", { class: "bubble " + speaker + (extraClass ? " " + extraClass : "") },
    el("div", { class: "meta", text: `${SPEAKER_LABEL[speaker] || speaker} - ${fmt(ms)}` }), el("div", { text }));
}
function addLiveBubble(box, key, speaker, ms, text, pending) {
  const b = bubble(speaker, ms, text, "live" + (pending ? " pending" : "")); b.dataset.key = key;
  const next = [...box.children].find((c) => Number(c.dataset.key) > key);   // urut waktu walau hasil datang tak berurutan
  box.insertBefore(b, next || null); box.scrollTop = box.scrollHeight; return b;
}
function wavBlob(frames, rate) {   // Float32 -> WAV 16-bit mono
  const n = frames.reduce((a, f) => a + f.length, 0), buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVEfmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, 1, true); v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, n * 2, true);
  let o = 44; for (const f of frames) for (let i = 0; i < f.length; i++, o += 2) v.setInt16(o, Math.max(-1, Math.min(1, f[i])) * 32767, true);
  return new Blob([buf], { type: "audio/wav" });
}
// pratinjau langsung seperti chat, 3 tahap per kalimat (HANYA tampilan; tidak disimpan; SOAP dari rekaman penuh):
//  1) saat suara terdeteksi  -> gelembung "..." (sedang bicara) langsung muncul
//  2) selama bicara          -> teks SEMENTARA tiap ~1,5 dtk (model kecil+cepat, miring)
//  3) saat kalimat selesai   -> teks lebih akurat (model menengah); diperhalus lagi (turbo) saat ada jeda
async function startLive(sources) {
  rec.live = true; rec.liveAccurate = $("liveMode").value === "akurat"; rec.liveCtx = []; rec.liveQueue = Promise.resolve(); rec.refineQueue = Promise.resolve(); rec.refining = 0; rec.fastPending = 0; rec.lastEmit = 0;
  $("liveBox").classList.remove("hidden"); $("liveChat").textContent = ""; $("liveHint").textContent = "";
  const RATE = 16000, FRAME = 320, PREROLL = 15, END_SILENCE = 25, MAX_FRAMES = 500, MIN_VOICED = 10;   // 20 ms/frame
  const USE_REFINE = false, USE_PARTIAL = false, PARTIAL_EVERY = 75, PARTIAL_MAX_FRAMES = 400;   // teks sementara: aktifkan hanya bila STT di GPU                                                  // 1,5 dtk; maks 8 dtk terakhir
  const hint = (e) => { $("liveHint").textContent = e && e.status === 502 ? "Pratinjau belum siap: model suara sedang disiapkan/diunduh. Rekaman tetap berjalan dan hasil akhir tetap dibuat setelah Selesai." : ""; };
  const post = async (blob, extra) => {
    const fd = new FormData(); fd.append("chunk", blob, "u.wav"); Object.entries(extra || {}).forEach(([k, v]) => fd.append(k, v));
    return api(`/sessions/${sessionId}/live`, { method: "POST", body: fd });
  };
  for (const { stream, speaker } of sources) {
    const ctx = new AudioContext({ sampleRate: RATE }); await ctx.resume();
    try { await ctx.audioWorklet.addModule("pcm-worklet.js"); } catch (e) { msg("Pratinjau langsung tidak tersedia di browser ini.", true); return; }
    const node = new AudioWorkletNode(ctx, "pcm-capture"), mute = ctx.createGain(); mute.gain.value = 0;
    ctx.createMediaStreamSource(stream).connect(node); node.connect(mute); mute.connect(ctx.destination);   // tanpa suara ke speaker
    rec.liveCtx.push(ctx);
    const st = { acc: new Float32Array(FRAME), n: 0, frames: 0, floor: 0.003, pre: [], utt: null, silent: 0, voiced: 0 };

    const refine = (b, blob) => {   // tahap 3b: perhalus dengan model akurat, HANYA saat ada jeda
      if ((rec.refining || 0) >= 3 || !rec.live) return;
      rec.refining++;
      rec.refineQueue = rec.refineQueue.then(async () => {
        try {
          const t0 = Date.now();
          while (rec.live && (rec.fastPending > 0 || Date.now() - rec.lastEmit < 1500)) {
            if (Date.now() - t0 > 20000) return;
            await new Promise((r) => setTimeout(r, 300));
          }
          if (!rec.live || !b.isConnected) return;
          const d = await post(blob, { accurate: "1" });
          if (d.text && b.isConnected) { b.lastChild.textContent = d.text; b.classList.add("refined"); }
        } catch (e) { /* tetap pakai teks sebelumnya */ } finally { rec.refining--; }
      });
    };
    const startUtt = (t) => {
      const start = Math.max(0, t - (st.pre.length - 1) * 20);
      const b = addLiveBubble($("liveChat"), start * 10 + (SPEAKER_ORDER[speaker] || 0), speaker, start, "...", true);
      st.utt = { frames: st.pre.slice(), start, bubble: b, done: false, partialBusy: false, lastPartial: 0 }; st.pre = []; st.silent = 0; st.voiced = 1;
    };
    const maybePartial = () => {
      const u = st.utt;
      if (!USE_PARTIAL || !u || u.partialBusy || !rec.live || u.frames.length - u.lastPartial < PARTIAL_EVERY || st.voiced < MIN_VOICED) return;
      u.partialBusy = true; u.lastPartial = u.frames.length;
      const blob = wavBlob(u.frames.slice(-PARTIAL_MAX_FRAMES), RATE);
      post(blob, { partial: "1" }).then((d) => {
        if (!u.done && d.text && u.bubble.isConnected) { u.bubble.lastChild.textContent = d.text; u.bubble.classList.add("partial"); }
        hint(null);
      }).catch(hint).finally(() => { u.partialBusy = false; });
    };
    const finish = (u) => {
      u.done = true; const b = u.bubble;
      if (st.voiced < MIN_VOICED || !rec.live) { b.remove(); return; }
      const blob = wavBlob(u.frames, RATE);
      rec.fastPending++; rec.lastEmit = Date.now();
      rec.liveQueue = rec.liveQueue.then(async () => {
        try {
          if (!rec.live) { b.remove(); return; }                    // rekaman dihentikan: jangan kirim lagi
          const d = await post(blob, rec.liveAccurate ? { accurate: "1" } : {}); hint(null);
          if (d.text) { b.lastChild.textContent = d.text; b.classList.remove("pending", "partial"); rec.lastEmit = Date.now(); if (USE_REFINE) refine(b, blob); } else b.remove();
        } catch (e) { b.remove(); hint(e); } finally { rec.fastPending--; }
      });
    };
    const onFrame = (fr) => {
      let s = 0; for (let i = 0; i < FRAME; i++) s += fr[i] * fr[i];
      const rms = Math.sqrt(s / FRAME), t = st.frames * 20; st.frames++;
      if (rms < st.floor * 1.5) st.floor = 0.95 * st.floor + 0.05 * rms; else st.floor = Math.min(st.floor * 1.0003, 0.02);
      const voiced = rms > Math.max(0.012, st.floor * 3.5);
      if (!st.utt) {
        st.pre.push(fr); if (st.pre.length > PREROLL) st.pre.shift();
        if (voiced) startUtt(t);
        return;
      }
      st.utt.frames.push(fr);
      if (voiced) { st.voiced++; st.silent = 0; } else st.silent++;
      if (st.silent >= END_SILENCE || st.utt.frames.length >= MAX_FRAMES) { const u = st.utt; st.utt = null; finish(u); st.voiced = 0; st.silent = 0; }
      else maybePartial();
    };
    node.port.onmessage = (ev) => {
      const d = ev.data;
      for (let i = 0; i < d.length; i++) { st.acc[st.n++] = d[i]; if (st.n === FRAME) { onFrame(st.acc.slice()); st.n = 0; } }
    };
  }
}
$("btnRec").onclick = async () => {
  try {
    const second = $("devPasien").value, first = $("devDokter").value;
    if (second && second === first) return msg("Mikrofon dokter dan pasien tidak boleh perangkat yang sama.", true);
    const get = (id) => navigator.mediaDevices.getUserMedia({ audio: id ? { deviceId: { exact: id } } : true });
    const s1 = await get(first); rec.streams = [s1];
    rec.main = newRecorder(s1, rec.parts.main); rec.second = null;
    if (second) { const s2 = await get(second); rec.streams.push(s2); rec.second = newRecorder(s2, rec.parts.second); }
    if ($("livePreview").checked) startLive(second ? [{ stream: s1, speaker: "dokter" }, { stream: rec.streams[1], speaker: "pasien" }] : [{ stream: s1, speaker: "tidak_diketahui" }]);
    $("recState").textContent = second ? "Merekam (dua kanal: dokter + pasien)..." : "Merekam (satu mikrofon)...";
    $("btnRec").disabled = true; $("btnStop").disabled = false;
  } catch (e) { msg("Mikrofon tidak bisa diakses.", true); }
};
$("btnStop").onclick = async () => {
  $("btnStop").disabled = true; $("recState").textContent = "Mengunggah..."; rec.live = false; (rec.liveCtx || []).forEach((c) => c.close());
  const stop = (r) => new Promise((res) => { r.onstop = res; r.stop(); });
  await stop(rec.main); if (rec.second) await stop(rec.second);
  rec.streams.forEach((s) => s.getTracks().forEach((t) => t.stop()));
  try {
    const fd = new FormData();
    const blob = (parts, r) => new Blob(parts, { type: r.mimeType || "audio/webm" });
    if (rec.second) { fd.append("dokter", blob(rec.parts.main, rec.main), "dokter.webm"); fd.append("pasien", blob(rec.parts.second, rec.second), "pasien.webm"); }
    else fd.append("mixed", blob(rec.parts.main, rec.main), "rekaman.webm");
    await api(`/sessions/${sessionId}/audio`, { method: "POST", body: fd });
    await api(`/sessions/${sessionId}/finish`, { method: "POST" });
    $("btnRec").disabled = false; $("liveBox").classList.add("hidden"); loadOrPoll();
  } catch (e) { msg("Gagal mengirim rekaman: " + e.message, true); $("btnRec").disabled = false; }
};

// ---- polling status
async function loadOrPoll() {
  try {
    const s = await api(`/sessions/${sessionId}`);
    if (s.status === "recording") { show("vRecord"); return; }
    if (s.status === "processing") {
      show("vProcessing"); $("procState").textContent = s.jobs.map((j) => `${j.kind}: ${j.status}`).join("  |  ");
      const stt = s.jobs.find((j) => j.kind === "stt");
      if (stt && stt.status === "succeeded" && !procShown) {       // transkrip tampil segera, tanpa menunggu ekstraksi
        procShown = true;
        try {
          const rv = await api(`/sessions/${sessionId}/review`); const box = $("procChat"); box.textContent = ""; box.classList.remove("hidden");
          rv.transcript.segments.forEach((x) => box.appendChild(bubble(x.speaker, x.start_ms, x.text)));
        } catch (e) { /* diabaikan: tampil di layar review */ }
      }
      setTimeout(loadOrPoll, 3000); return;
    }
    await loadReview();
  } catch (e) { msg("Sesi tidak ditemukan atau tidak berhak diakses.", true); show("vStart"); }
}

// ---- review
async function loadReview() {
  review = await api(`/sessions/${sessionId}/review`);
  show("vReview"); render(); emit("review_loaded");
}
function render() {
  const approved = review.session.status === "approved" || review.session.status === "submitted";
  const nb = $("notices"); nb.textContent = "";
  review.notices.forEach((n) => nb.appendChild(el("div", { class: "banner" + (n === "kualitas_draft_rendah" ? " bad" : ""), text: NOTICE_TEXT[n] || n })));
  $("stat").textContent = `Status: ${review.session.status}` + (review.soap ? ` | versi ${review.soap.version} (${review.soap.source})` : "");
  $("btnSave").disabled = approved; $("btnApprove").disabled = approved;
  $("btnSubmit").disabled = review.session.status !== "approved";    // aktif hanya setelah approve
  renderSoap(approved); renderItems(); renderCodes(approved); renderTranscript();
}
function renderSoap(readOnly) {
  const box = $("soap"); box.textContent = "";
  const sentences = (review.soap && review.soap.sentences) || [];
  "SOAP".split("").forEach((sec) => {
    const wrap = el("div", { class: "sec" }, el("h3", { text: `${sec} - ${SEC_NAME[sec]}` }));
    const list = el("div", { id: "list" + sec }); wrap.appendChild(list);
    const rows = sentences.filter((s) => s.section === sec && !(s.text === "Tidak disebutkan" && !s.evidence_item_ids.length && sentences.filter((x) => x.section === sec).length > 1));
    if (!rows.length) rows.push({ id: null, section: sec, text: "Tidak disebutkan", evidence_item_ids: [], flagged: false, is_ai_suspicion: false });
    rows.forEach((s) => list.appendChild(sentenceRow(s, readOnly)));
    if (!readOnly) wrap.appendChild(el("button", { text: "+ Tambah kalimat", onclick: () => { list.appendChild(sentenceRow({ id: null, section: sec, text: "", evidence_item_ids: [], flagged: false, is_ai_suspicion: false }, false)); } }));
    box.appendChild(wrap);
  });
}
function sentenceRow(s, readOnly) {
  const row = el("div", { class: "sent" + (s.flagged ? " flagged" : "") + (s.is_ai_suspicion ? " suspicion" : "") });
  row.dataset.id = s.id || ""; row.dataset.section = s.section;
  const ta = el("textarea", { value: s.text, readOnly, rows: 1 });
  ta.onfocus = () => jumpTo(s.evidence_item_ids, row);
  row.onclick = () => jumpTo(s.evidence_item_ids, row);
  row.appendChild(ta);
  if (s.flagged) row.appendChild(el("span", { class: "badge ditandai", text: "ditandai" }));
  if (s.is_ai_suspicion) row.appendChild(el("span", { class: "badge", text: "dugaan" }));
  if (!readOnly) row.appendChild(el("button", { text: "Hapus", onclick: (e) => { e.stopPropagation(); row.remove(); } }));
  return row;
}
function renderItems() {
  const box = $("items"); box.textContent = "";
  review.items.forEach((it) => {
    const title = el("div", {}, el("span", { class: "badge " + it.verdict, text: it.verdict }), el("span", { text: ` ${it.field}: ${it.teks || it.nama || ""} ` }), el("span", { class: "badge", text: it.status }));
    const d = el("div", { class: "item" }, title, el("small", { text: `"${it.evidence}"` }));
    if (it.reasons && it.reasons.length) d.appendChild(el("small", { text: "Alasan: " + it.reasons.join(", ") }));
    d.onclick = () => highlight(it.segment_idxs);
    box.appendChild(d);
  });
  if (!review.items.length) box.appendChild(el("div", { class: "muted", text: "Tidak ada butir." }));
  const mb = $("missed"); mb.textContent = "";
  review.missed.forEach((m) => {
    const d = el("div", { class: "item", text: `[${m.kind}] ${m.mention} @ ${fmt(m.start_ms)}` });
    d.onclick = () => highlightByTime(m.start_ms); mb.appendChild(d);
  });
  if (!review.missed.length) mb.appendChild(el("div", { class: "muted", text: "Tidak ada." }));
}
const STATE_TEXT = { terisi: "terisi otomatis", saran: "saran (belum terisi)", kosong: "kosong", dipilih_dokter: "dipilih dokter" };
const REASON_TEXT = {
  dugaan_tidak_dikodekan: "dugaan, tidak dikodekan", dinegasi_tidak_dikodekan: "dinegasi, tidak dikodekan",
  direncanakan_tidak_dikodekan: "direncanakan, tidak dikodekan", bukan_diagnosis_dokter: "bukan diagnosis dokter",
  llm_tidak_ada_yang_cocok: "tidak ada kandidat yang cocok", tidak_ada_kandidat: "tidak ada kandidat",
  keyakinan_rendah: "keyakinan rendah", kandidat_mirip: "kandidat mirip", bukan_peringkat_pertama: "bukan peringkat 1",
  butir_ditandai: "butir ditandai", kode_tidak_ada_di_tabel: "kode tidak ada di tabel",
};
async function saveCode(c, code) {
  try { Object.assign(c, await api(`/sessions/${sessionId}/codes/${c.id}`, { method: "PUT", json: { code } })); msg(""); renderCodes(false); }
  catch (e) { msg("Kode tidak dapat disimpan: " + e.message, true); }
}
function renderCodes(readOnly) {
  const box = $("codes"); box.textContent = "";
  (review.codes || []).forEach((c) => {
    const it = review.items.find((x) => x.id === c.item_id) || {};
    const code = c.final_code || c.suggested_code;
    const disp = c.final_code ? c.final_display : c.suggested_display;
    const row = el("div", { class: "item" }, el("div", {}, el("b", { text: it.teks || "" }), el("span", { class: "badge", text: " " + (STATE_TEXT[c.state] || c.state) })));
    row.appendChild(el("div", { text: code ? `${code} - ${disp || ""}` : "(belum ada kode)" }));
    if (c.reason) row.appendChild(el("small", { text: "Catatan: " + (REASON_TEXT[c.reason] || c.reason) }));
    if (!readOnly) {
      if (c.state === "saran" && c.suggested_code) row.appendChild(el("button", { text: "Terima saran", onclick: () => saveCode(c, c.suggested_code) }));
      if (c.final_code) row.appendChild(el("button", { text: "Kosongkan", onclick: () => saveCode(c, null) }));
      const sel = el("select", {}, el("option", { value: "", text: "Ganti dengan kandidat..." }));
      (c.candidates || []).forEach((k) => sel.appendChild(el("option", { value: k.code, text: `${k.code} - ${k.display}` })));
      sel.onchange = () => sel.value && saveCode(c, sel.value);
      row.appendChild(sel);
      const q = el("input", { type: "text", placeholder: `Cari kode ${c.system}...` }); const res = el("div", {});
      let timer; q.oninput = () => { clearTimeout(timer); timer = setTimeout(async () => {
        res.textContent = ""; if (q.value.trim().length < 2) return;
        try { (await api(`/terminology/${c.system.toLowerCase()}/search?q=${encodeURIComponent(q.value.trim())}`)).forEach((r) => res.appendChild(el("div", { class: "item", text: `${r.code} - ${r.display}`, onclick: () => saveCode(c, r.code) }))); } catch (e) { /* abaikan */ }
      }, 350); };
      row.appendChild(q); row.appendChild(res);
    }
    box.appendChild(row);
  });
  if (!(review.codes || []).length) box.appendChild(el("div", { class: "muted", text: "Tidak ada diagnosis yang dapat dikodekan." }));
}
function renderTranscript() {
  const box = $("transcript"); box.textContent = "";
  review.transcript.segments.forEach((s) => {
    const b = bubble(s.speaker, s.start_ms, s.text, "seg"); b.id = "seg" + s.idx; b.classList.add(s.speaker);
    box.appendChild(b);
  });
  if (!review.transcript.segments.length) {
    const je = (review.job_errors || {}).stt;
    const why = je && je !== "None" ? `Pengenalan suara GAGAL (kode: ${je}). Periksa layanan STT.` : review.transcript.is_empty ? "Tidak ada ucapan terdeteksi pada rekaman." : "Transkrip tidak tersedia (mungkin sudah dihapus sesuai retensi).";
    box.appendChild(el("div", { class: "banner bad", text: why }));
  }
}
function highlight(idxs) {
  document.querySelectorAll(".seg.hl").forEach((e) => e.classList.remove("hl"));
  (idxs || []).forEach((i, n) => { const e = $("seg" + i); if (e) { e.classList.add("hl"); if (n === 0) { const box = $("transcript"); box.scrollTo({ top: Math.max(0, e.offsetTop - box.offsetTop - 40), behavior: "smooth" }); } } });
}
function highlightByTime(ms) { const s = review.transcript.segments.find((x) => x.start_ms <= ms && ms <= x.end_ms); if (s) highlight([s.idx]); }
function jumpTo(itemIds, row) {
  document.querySelectorAll(".sent.active").forEach((e) => e.classList.remove("active")); row.classList.add("active");
  const idxs = new Set(); (itemIds || []).forEach((id) => { const it = review.items.find((x) => x.id === id); if (it) it.segment_idxs.forEach((i) => idxs.add(i)); });
  highlight([...idxs]);
}
function collect() {
  const out = [];
  document.querySelectorAll(".sent").forEach((r) => {
    const t = r.querySelector("textarea").value.trim();
    if (t) out.push({ id: r.dataset.id || null, section: r.dataset.section, text: t });
  });
  return out;
}
async function save() {
  const d = await api(`/sessions/${sessionId}/soap`, { method: "PUT", json: { sentences: collect() } });
  review.soap = d; return d;
}
$("btnSave").onclick = async () => { try { await save(); msg("Tersimpan sebagai versi dokter."); render(); } catch (e) { msg("Gagal menyimpan: " + e.message, true); } };
$("btnApprove").onclick = async () => {
  try {
    const d = await save();
    const flagged = d.sentences.some((s) => s.flagged);
    if (flagged && !$("ack").checked) return msg("Ada kalimat bertanda. Tinjau lalu centang konfirmasi sebelum approve.", true);
    if (!confirm("Approve SOAP ini? Setelah approve tidak bisa diedit.")) return;
    await api(`/sessions/${sessionId}/approve`, { method: "POST", json: { soap_id: d.id, acknowledge_flagged: $("ack").checked } });
    msg("SOAP di-approve."); await loadReview(); emit("approved");
  } catch (e) { msg("Approve gagal: " + e.message, true); }
};
$("btnSubmit").onclick = async () => {
  try { await api(`/sessions/${sessionId}/submit`, { method: "POST" }); msg("Terkirim ke SIMRS."); await loadReview(); emit("submitted"); }
  catch (e) { msg("Pengiriman ke SIMRS gagal: " + e.message, true); }
};

// ---- mode widget: token + sesi dari fragmen URL (fragmen tidak dikirim ke server/log)
(function initFromHash() {
  const h = new URLSearchParams(location.hash.replace(/^#/, ""));
  if (h.get("token") && h.get("session")) {
    token = h.get("token"); sessionId = h.get("session");
    history.replaceState(null, "", location.pathname + location.search);
    $("btnLogout").classList.add("hidden"); $("who").textContent = "widget";
    if (EMBED) document.body.classList.add("embed");
    loadOrPoll();
  }
})();

// ---- unggah file audio (alternatif merekam langsung)
$("btnUpload").onclick = async () => {
  const d = $("fDokter").files[0], p = $("fPasien").files[0], m = $("fMixed").files[0];
  const fd = new FormData();
  if (d && p) { fd.append("dokter", d, d.name); fd.append("pasien", p, p.name); }
  else if (m) fd.append("mixed", m, m.name);
  else return msg("Pilih file dokter + pasien, atau satu file campuran.", true);
  $("btnUpload").disabled = true; msg("Mengunggah...");
  try {
    await api(`/sessions/${sessionId}/audio`, { method: "POST", body: fd });
    await api(`/sessions/${sessionId}/finish`, { method: "POST" });
    msg(""); loadOrPoll();
  } catch (e) { msg("Gagal mengunggah: " + e.message, true); }
  $("btnUpload").disabled = false;
};
