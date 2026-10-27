<script setup>
// Integrasi SIMRS, tiga tab: Koneksi & pengiriman | Webhook | Kunci API & origin.
// (Pemetaan ID dokter ke SIMRS diisi di form "Ubah data" pengguna.)
import { computed, onMounted, ref } from "vue";
import { Check, Copy, Eye, EyeOff, Plus, RefreshCw, Trash2 } from "lucide-vue-next";
import { api, errText } from "../../api.js";
import { dateShort } from "../../format.js";
import Modal from "../../components/Modal.vue";
import SubmissionsTab from "./SubmissionsTab.vue";

const TABS = [["koneksi", "Koneksi & pengiriman"], ["webhook", "Webhook"], ["kunci", "Kunci API & origin"]];
const tab = ref("koneksi");
const d = ref(null), err = ref(""), notice = ref(""), busy = ref("");
const adapter = ref(""), webhook = ref(""), origins = ref("");
const testRes = ref(null), secret = ref(null), showSecret = ref(false), copied = ref("");
const keyForm = ref(null), newKey = ref(null), revoke = ref(null), confirmAdapter = ref(false), hooks = ref(null);

function fill(x) { d.value = x; adapter.value = x.adapter; webhook.value = x.webhook_url || ""; origins.value = (x.allowed_origins || []).join("\n"); }
async function load() { try { fill(await api("/admin/integration")); } catch (e) { err.value = errText(e); } }
async function loadHooks() { try { hooks.value = (await api("/admin/integration/webhook-log")).items; } catch (e) { err.value = errText(e); } }
onMounted(() => { load(); loadHooks(); });

async function run(name, fn, ok) {
  err.value = ""; notice.value = ""; busy.value = name;
  try { await fn(); if (ok) notice.value = ok; await load(); } catch (e) { err.value = errText(e); } finally { busy.value = ""; }
}
const saveWebhook = () => run("wh", () => api("/admin/integration/webhook", { method: "PUT", json: { url: webhook.value.trim() || null } }), webhook.value.trim() ? "Webhook disimpan." : "Webhook dihapus.");
const saveOrigins = () => run("or", () => api("/admin/integration/origins", { method: "PUT", json: { origins: origins.value.split(/\s+/).filter(Boolean) } }), "Origin disimpan.");
const saveAdapter = () => { confirmAdapter.value = false; return run("ad", () => api("/admin/integration/adapter", { method: "PUT", json: { adapter: adapter.value } }), "Adapter SIMRS diganti."); };
async function test() {
  testRes.value = null; err.value = ""; busy.value = "test";
  try { testRes.value = await api("/admin/integration/test", { method: "POST" }); await load(); } catch (e) { err.value = errText(e); } finally { busy.value = ""; }
}
async function toggleSecret() {
  if (showSecret.value) { showSecret.value = false; return; }
  try { secret.value = (await api("/admin/integration/webhook-secret")).secret; showSecret.value = true; } catch (e) { err.value = errText(e); }
}
async function createKey() {
  err.value = ""; busy.value = "key";
  try { newKey.value = await api("/admin/integration/keys", { method: "POST", json: { label: keyForm.value.label } }); keyForm.value = null; await load(); }
  catch (e) { keyForm.value.err = errText(e); } finally { busy.value = ""; }
}
const doRevoke = () => { const k = revoke.value; revoke.value = null; return run("rv", () => api(`/admin/integration/keys/${k.prefix}/revoke`, { method: "POST" }), `Kunci ${k.prefix}… dicabut.`); };
async function copy(id, text) { try { await navigator.clipboard.writeText(text); copied.value = id; setTimeout(() => (copied.value = ""), 1500); } catch { /* izin ditolak */ } }

const activeKeys = computed(() => (d.value?.keys || []).filter((k) => !k.revoked_at).length);
const quotaPct = computed(() => (d.value?.monthly_quota ? Math.min(100, Math.round((d.value.sessions_this_month / d.value.monthly_quota) * 100)) : null));
const webhookHttp = computed(() => /^http:\/\//i.test(webhook.value.trim()) && !/^http:\/\/(localhost|127\.0\.0\.1)/i.test(webhook.value.trim()));
const lt = computed(() => testRes.value ? { ok: testRes.value.ok, ms: testRes.value.latency_ms, at: null } : d.value?.last_test ? { ok: d.value.last_test.ok, ms: d.value.last_test.latency_ms, at: d.value.last_test.at } : null);
const EVENTS = [["session.processed", "Draf SOAP selesai disusun AI"], ["session.approved", "Dokter menyetujui SOAP"], ["session.submitted", "SOAP berhasil dikirim ke SIMRS"]];
</script>

<template>
  <div v-if="d" class="adm-wrap adm-wide">
    <div class="adm-tabs" role="tablist">
      <button v-for="t in TABS" :key="t[0]" class="adm-tab" :class="{ on: tab === t[0] }" role="tab" :aria-selected="tab === t[0]" @click="tab = t[0]">{{ t[1] }}</button>
    </div>
    <p v-if="err" class="banner bad" role="alert">{{ err }}</p>
    <p v-if="notice" class="adm-ok" role="status">{{ notice }}</p>

    <!-- ===== Koneksi & pengiriman -->
    <template v-if="tab === 'koneksi'">
      <section class="card adm-card">
        <div class="adm-head"><div><h2 class="h2">Adapter SIMRS</h2><p>Penghubung ke SIMRS rumah sakit: antrean pasien dan pengiriman SOAP yang sudah disetujui dokter.</p></div>
          <span class="adm-badge" :class="lt ? (lt.ok ? 'ok' : 'bad') : ''">{{ lt ? (lt.ok ? "Terhubung" : "Gagal tersambung") : "Belum diuji" }}</span></div>
        <div class="adm-row">
          <select v-model="adapter" class="input adm-grow" style="max-width: 280px" aria-label="Adapter SIMRS"><option v-for="a in d.adapters" :key="a" :value="a">{{ a }}</option></select>
          <button class="btn btn-primary" :disabled="adapter === d.adapter || busy === 'ad'" @click="confirmAdapter = true">Simpan</button>
          <button class="btn adm-spacer" :disabled="busy === 'test'" @click="test"><RefreshCw :size="16" />{{ busy === "test" ? "Menguji…" : "Uji koneksi" }}</button>
        </div>
        <p v-if="lt" class="adm-hint">Uji terakhir: <b>{{ lt.ok ? "berhasil" : "gagal" }}</b><template v-if="lt.ms != null"> · {{ lt.ms }} ms</template><template v-if="lt.at"> · {{ dateShort(lt.at) }}</template>
          <template v-if="testRes && !testRes.ok"> · jenis galat: {{ testRes.detail }}</template></p>
        <p class="adm-hint">Saat ini hanya adapter <b>mock</b> (data contoh) yang tersedia. Adapter untuk SIMRS nyata menunggu dokumentasi REST SIMRS rumah sakit.</p>
      </section>
      <SubmissionsTab />
    </template>

    <!-- ===== Webhook -->
    <template v-else-if="tab === 'webhook'">
      <section class="card adm-card">
        <div class="adm-head"><div><h2 class="h2">Webhook</h2><p>MedVoice memanggil URL ini setiap status sesi berubah. Isi panggilan hanya ID dan status (tanpa data klinis) dan ditandatangani HMAC-SHA256. Bila SIMRS gagal menerima, dicoba ulang hingga 5 kali.</p></div></div>
        <div class="field"><label for="wh">URL webhook</label>
          <input id="wh" v-model="webhook" class="input" placeholder="https://simrs.rs.co.id/medvoice/hook" autocomplete="off" />
          <span v-if="webhookHttp" class="adm-hint" style="color: var(--warning)">URL http tanpa enkripsi: gunakan https bila SIMRS mendukungnya.</span></div>
        <div class="adm-row">
          <button class="btn btn-primary" :disabled="busy === 'wh' || webhook.trim() === (d.webhook_url || '')" @click="saveWebhook">Simpan</button>
          <button class="btn" :disabled="!d.webhook_url || busy === 'wh'" @click="webhook = ''; saveWebhook()">Hapus webhook</button>
        </div>
        <div class="field"><label>Rahasia penanda tangan (header <span class="adm-mono">X-MedVoice-Signature</span>)</label>
          <div class="adm-secret"><span class="adm-mono">{{ showSecret ? secret : "•".repeat(32) }}</span>
            <span class="adm-row"><button class="btn btn-sm" @click="toggleSecret"><component :is="showSecret ? EyeOff : Eye" :size="14" />{{ showSecret ? "Sembunyikan" : "Tampilkan" }}</button>
              <button v-if="showSecret" class="btn btn-sm" @click="copy('sec', secret)"><component :is="copied === 'sec' ? Check : Copy" :size="14" />{{ copied === "sec" ? "Tersalin" : "Salin" }}</button></span></div>
          <span class="adm-hint">Melihat rahasia ini dicatat di log audit. Event yang dikirim: <span class="adm-mono">{{ EVENTS.map((e) => e[0]).join(", ") }}</span>.</span></div>
      </section>
      <section class="card adm-box">
        <header class="adm-cardhead"><h2>Pengiriman webhook terbaru</h2><button class="btn adm-btn-sm adm-spacer" @click="loadHooks"><RefreshCw :size="13" />Muat ulang</button></header>
        <div class="adm-scroll"><table class="adm-table adm-fig" style="min-width: 560px">
          <thead><tr><th>WAKTU</th><th>EVENT</th><th style="width: 110px">STATUS</th><th>KETERANGAN</th></tr></thead>
          <tbody>
            <tr v-for="(h, i) in hooks || []" :key="i">
              <td class="adm-sub" style="font-size: 13px; white-space: nowrap">{{ dateShort(h.at) }}</td><td class="adm-mono" style="font-size: 13px">{{ h.event || "—" }}</td>
              <td><span class="adm-badge" :class="h.ok ? 'ok' : 'bad'">{{ h.ok ? "Terkirim" : "Gagal" }}</span></td>
              <td class="adm-sub" style="font-size: 12px">{{ h.error || "—" }}<template v-if="h.attempt"> · percobaan ke-{{ h.attempt }}</template></td>
            </tr>
            <tr v-if="hooks && !hooks.length"><td colspan="4" class="adm-empty">Belum ada pengiriman webhook.</td></tr>
          </tbody></table></div>
      </section>
    </template>

    <!-- ===== Kunci API & origin -->
    <template v-else>
      <section class="card adm-card">
        <div class="adm-head"><div><h2 class="h2">Kunci API</h2><p>Dipakai server SIMRS untuk memanggil API MedVoice. Kunci utuh hanya tampil sekali saat dibuat. {{ activeKeys }} kunci aktif.</p></div>
          <button class="btn btn-primary" @click="keyForm = { label: '', err: '' }"><Plus :size="16" />Buat kunci</button></div>
        <div class="adm-scroll">
          <table class="adm-table" style="min-width: 640px">
            <thead><tr><th>LABEL</th><th>AWALAN</th><th>DIBUAT</th><th>TERAKHIR DIPAKAI</th><th>STATUS</th><th /></tr></thead>
            <tbody>
              <tr v-for="k in d.keys" :key="k.prefix" :class="{ 'adm-off': k.revoked_at }">
                <td class="adm-name">{{ k.label || "—" }}</td><td class="adm-mono">{{ k.prefix }}…</td>
                <td class="adm-sub">{{ dateShort(k.created_at) }}</td><td class="adm-sub">{{ k.last_used_at ? dateShort(k.last_used_at) : "Belum pernah" }}</td>
                <td><span class="pill" :class="k.revoked_at ? '' : 'pill-success'">{{ k.revoked_at ? "Dicabut" : "Aktif" }}</span></td>
                <td><button v-if="!k.revoked_at" class="btn btn-sm" @click="revoke = k"><Trash2 :size="14" />Cabut</button></td>
              </tr>
              <tr v-if="!d.keys.length"><td colspan="6" class="adm-empty">Belum ada kunci API.</td></tr>
            </tbody>
          </table>
        </div>
      </section>
      <section class="card adm-card">
        <div class="adm-head"><div><h2 class="h2">Origin yang boleh menyematkan MedVoice</h2><p>Alamat situs SIMRS yang boleh menanamkan widget atau memanggil API dari browser. Satu per baris, bentuk <span class="adm-mono">https://host[:port]</span>.</p></div></div>
        <textarea v-model="origins" class="adm-textarea" spellcheck="false" aria-label="Daftar origin" placeholder="https://simrs.rs.co.id" />
        <div class="adm-row"><button class="btn btn-primary" :disabled="busy === 'or'" @click="saveOrigins">Simpan origin</button><span class="adm-hint">UI MedVoice sendiri selalu diizinkan.</span></div>
      </section>
      <section class="card adm-card">
        <div class="adm-head"><div><h2 class="h2">Batas pemakaian</h2><p>Ditetapkan oleh pengelola layanan MedVoice; hubungi pengelola bila perlu diubah.</p></div></div>
        <dl class="adm-kv">
          <dt>Batas permintaan</dt><dd>{{ d.rate_limit_per_min }} per menit</dd>
          <dt>Sesi bulan ini</dt><dd>{{ d.sessions_this_month }}<template v-if="d.monthly_quota"> dari {{ d.monthly_quota }} ({{ quotaPct }}%)</template><template v-else> (tanpa kuota bulanan)</template></dd>
        </dl>
      </section>
    </template>

    <Modal v-if="confirmAdapter" :width="460" label="Ganti adapter" @close="confirmAdapter = false">
      <h2 class="adm-modal-h">Ganti adapter ke “{{ adapter }}”?</h2>
      <p class="muted">SOAP yang disetujui dokter berikutnya akan dikirim lewat adapter ini, dan antrean pasien diambil darinya.</p>
      <div class="adm-modal-actions"><button class="btn" @click="confirmAdapter = false">Batal</button><button class="btn btn-primary" @click="saveAdapter">Ya, ganti</button></div>
    </Modal>

    <Modal v-if="keyForm" :width="460" label="Buat kunci API" @close="keyForm = null">
      <form @submit.prevent="createKey">
        <h2 class="adm-modal-h">Buat kunci API</h2>
        <div class="field"><label for="kl">Label</label><input id="kl" v-model="keyForm.label" class="input" required maxlength="80" placeholder="mis. server SIMRS utama" autofocus /></div>
        <p v-if="keyForm.err" class="banner bad" role="alert" style="margin-top: 12px">{{ keyForm.err }}</p>
        <div class="adm-modal-actions"><button type="button" class="btn" @click="keyForm = null">Batal</button><button class="btn btn-primary" :disabled="busy === 'key'">Buat</button></div>
      </form>
    </Modal>

    <Modal v-if="newKey" :width="560" label="Kunci API baru" @close="newKey = null">
      <h2 class="adm-modal-h">Kunci API dibuat</h2>
      <p class="muted">Simpan kunci ini sekarang di tempat aman (mis. konfigurasi server SIMRS). Kunci utuh <b>tidak bisa ditampilkan lagi</b>.</p>
      <div class="adm-secret" style="margin-top: 14px"><span class="adm-mono">{{ newKey.key }}</span>
        <button class="btn btn-sm" @click="copy('key', newKey.key)"><component :is="copied === 'key' ? Check : Copy" :size="14" />{{ copied === "key" ? "Tersalin" : "Salin" }}</button></div>
      <div class="adm-modal-actions"><button class="btn btn-primary" @click="newKey = null">Sudah saya simpan</button></div>
    </Modal>

    <Modal v-if="revoke" :width="460" label="Cabut kunci" @close="revoke = null">
      <h2 class="adm-modal-h">Cabut kunci {{ revoke.prefix }}…?</h2>
      <p class="muted">Sistem yang masih memakai kunci “{{ revoke.label || revoke.prefix }}” langsung ditolak. Tindakan ini tidak bisa dibatalkan; buat kunci baru bila perlu.</p>
      <div class="adm-modal-actions"><button class="btn" @click="revoke = null">Batal</button><button class="btn btn-danger" @click="doRevoke">Ya, cabut</button></div>
    </Modal>
  </div>
  <p v-else-if="err" class="banner bad" role="alert">{{ err }}</p>
</template>
