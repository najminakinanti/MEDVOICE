// Tidak ada API key/rahasia di sini. Token login hanya di sessionStorage tab ini (lihat restoreSession).
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

// Token disimpan di sessionStorage (hanya tab ini, hilang saat tab ditutup) supaya muat ulang halaman tidak memaksa login ulang.
const KEY = "medvoice.token";
const store = (t) => { try { t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY); } catch { /* penyimpanan diblokir */ } };

export async function restoreSession() {
  let t = null;
  try { t = sessionStorage.getItem(KEY); } catch { /* diblokir */ }
  if (!t) return;
  auth.token = t;
  try { auth.me = await api("/me"); } catch { auth.token = null; auth.me = null; store(null); }
}

export async function login(username, password) {
  const d = await api("/auth/login", { method: "POST", json: { username, password } });
  auth.token = d.access_token;
  store(auth.token);
  auth.me = await api("/me");
}

export const isAdmin = () => auth.me?.role === "admin";
export const isSuperadmin = () => auth.me?.role === "superadmin";
export const canAdmin = () => isAdmin() || isSuperadmin();                         // melihat bagian ADMIN RS
export const homePath = () => (isSuperadmin() ? "/admin/pengguna" : "/queue");
export const ROLE_LABEL = { dokter: "Dokter", admin: "Admin RS", superadmin: "Superadmin" };

export function logout() { auth.token = null; auth.me = null; store(null); }

const ERR = {
  invalid_credentials: "Akun atau kata sandi salah.", rate_limited: "Terlalu banyak percobaan. Coba lagi sebentar lagi.",
  consent_required: "Persetujuan pasien wajib sebelum merekam.", session_not_recording: "Sesi ini sudah tidak merekam.",
  session_not_editable: "Sesi sudah disetujui dan tidak bisa diedit.", flagged_not_acknowledged: "Ada kalimat bertanda; centang konfirmasi peninjauan.",
  soap_kosong: "SOAP masih kosong.", simrs_submit_failed: "SIMRS menolak/tidak merespons. Coba kirim ulang.",
  not_latest_version: "Ada versi SOAP yang lebih baru. Muat ulang halaman.", monthly_quota_exceeded: "Kuota bulanan terlampaui.",
  patient_access_denied: "Dokter tidak berhak atas pasien ini.", code_not_in_terminology: "Kode tidak ada di tabel terminologi.",
  session_not_found: "Sesi tidak ditemukan atau bukan milik Anda.", audio_too_large: "File audio terlalu besar.",
  unsupported_audio_type: "Format audio tidak didukung.",
  admin_required: "Hanya admin RS yang boleh membuka halaman ini.", user_not_found: "Pengguna tidak ditemukan.",
  email_invalid: "Format email tidak valid.", nip_invalid: "NIP hanya boleh huruf/angka/titik/strip (3-40 karakter).",
  identity_required: "Isi email atau NIP (dipakai untuk login).", username_invalid: "Nama pengguna tidak valid.",
  email_taken: "Email ini sudah dipakai akun lain.", nip_taken: "NIP ini sudah dipakai akun lain.",
  username_taken: "Nama pengguna sudah dipakai di RS ini.", simrs_user_id_taken: "ID dokter di SIMRS sudah dipakai di RS ini.",
  role_invalid: "Peran tidak valid.", password_too_short: "Kata sandi minimal 10 karakter.",
  password_unchanged: "Kata sandi baru harus berbeda dari yang lama.", current_password_wrong: "Kata sandi saat ini salah.",
  cannot_modify_self: "Anda tidak bisa menonaktifkan atau menurunkan peran akun Anda sendiri.",
  last_admin: "Setiap RS harus punya minimal satu admin aktif.", use_profile: "Ubah kata sandi sendiri lewat tab Profil Saya.",
  webhook_url_invalid: "URL webhook tidak valid (harus http/https, tanpa user:password).",
  origin_invalid: "Origin harus berbentuk https://host[:port] tanpa path.", adapter_unknown: "Adapter tidak dikenal.",
  key_not_found: "Kunci tidak ditemukan atau sudah dicabut.",
  superadmin_required: "Hanya superadmin yang boleh membuka halaman ini.", clinical_role_required: "Peran ini tidak punya akses data klinis.",
  hospital_not_found: "Rumah sakit tidak ditemukan.", hospital_name_taken: "Nama rumah sakit sudah dipakai.",
  status_invalid: "Filter status tidak valid.", group_invalid: "Filter jenis tidak valid.",
  submission_not_found: "Data pengiriman tidak ditemukan.", already_submitted: "SOAP ini sudah berhasil terkirim; tidak dikirim dua kali.",
  not_approved: "SOAP belum disetujui dokter, jadi belum boleh dikirim.",
  hospital_name_invalid: "Nama RS: huruf kecil, angka, dan tanda strip, 3-60 karakter (mis. rs-harapan-bandung).",
};
export const errText = (e) => (e && ERR[e.detail]) || (e && e.detail) || "Terjadi kesalahan.";
