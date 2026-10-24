// Pemilihan mikrofon: dokter + pasien (opsional). Pilihan disimpan per perangkat di localStorage (hanya id perangkat).
const KEY = "mv.mics";

export function loadMicPrefs() {
  try { return { dokter: "", pasien: "", ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch { return { dokter: "", pasien: "" }; }
}
export function saveMicPrefs(p) {
  try { localStorage.setItem(KEY, JSON.stringify({ dokter: p.dokter || "", pasien: p.pasien || "" })); } catch { /* mode privat */ }
}

/** Minta izin mikrofon (label perangkat baru tersedia setelah izin) lalu daftar semua mikrofon. */
export async function listMics() {
  const tmp = await navigator.mediaDevices.getUserMedia({ audio: true });
  tmp.getTracks().forEach((t) => t.stop());
  const devs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
  return devs.map((d, i) => ({ id: d.deviceId, label: d.label || "Mikrofon " + (i + 1) }));
}

export async function openMic(deviceId) {
  const get = (audio) => navigator.mediaDevices.getUserMedia({ audio });
  if (!deviceId) return get(true);
  try { return await get({ deviceId: { exact: deviceId } }); } catch { return get(true); }   // perangkat tersimpan sudah dicabut
}

export function recorderExt(mime = "") {
  return /mp4|aac/.test(mime) ? "m4a" : /ogg/.test(mime) ? "ogg" : "webm";
}
