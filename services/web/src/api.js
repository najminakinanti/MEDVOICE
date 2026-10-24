// Tidak ada API key/rahasia di sini. Token dokter hanya disimpan di memori halaman (hilang saat muat ulang).
import { reactive } from "vue";

export const auth = reactive({ token: null, me: null, embed: false });

export class ApiError extends Error {
  constructor(status, detail) { super(detail || String(status)); this.status = status; this.detail = detail; }
}

let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

export async function api(path, { method = "GET", json, body, signal } = {}) {
  const headers = {};
  if (auth.token) headers.Authorization = "Bearer " + auth.token;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  const r = await fetch("/v1" + path, { method, headers, body, signal });
  let data = null;
  try { data = await r.json(); } catch { /* badan kosong */ }
  if (!r.ok) {
    if (r.status === 401 && auth.token) onUnauthorized();
    throw new ApiError(r.status, data && typeof data.detail === "string" ? data.detail : r.statusText);
  }
  return data;
}

export async function login(client, username, password) {
  const d = await api("/auth/login", { method: "POST", json: { client, username, password } });
  auth.token = d.access_token;
  auth.me = await api("/me");
}

export function logout() { auth.token = null; auth.me = null; }

const ERR = {
  invalid_credentials: "Akun atau kata sandi salah.", rate_limited: "Terlalu banyak percobaan. Coba lagi sebentar lagi.",
  consent_required: "Persetujuan pasien wajib sebelum merekam.", session_not_recording: "Sesi ini sudah tidak merekam.",
  session_not_editable: "Sesi sudah disetujui dan tidak bisa diedit.", flagged_not_acknowledged: "Ada kalimat bertanda; centang konfirmasi peninjauan.",
  soap_kosong: "SOAP masih kosong.", simrs_submit_failed: "SIMRS menolak/tidak merespons. Coba kirim ulang.",
  not_latest_version: "Ada versi SOAP yang lebih baru. Muat ulang halaman.", monthly_quota_exceeded: "Kuota bulanan terlampaui.",
  patient_access_denied: "Dokter tidak berhak atas pasien ini.", code_not_in_terminology: "Kode tidak ada di tabel terminologi.",
  session_not_found: "Sesi tidak ditemukan atau bukan milik Anda.", audio_too_large: "File audio terlalu besar.",
  unsupported_audio_type: "Format audio tidak didukung.",
};
export const errText = (e) => (e && ERR[e.detail]) || (e && e.detail) || "Terjadi kesalahan.";
