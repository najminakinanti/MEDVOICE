<script setup>
// Pengaturan rumah sakit, dua tab: Data & Privasi | Log audit.
// Status layanan STT/LLM, terminologi, dan daftar peran ada di halaman Sistem (khusus superadmin).
import { computed, onMounted, ref } from "vue";
import { Trash2 } from "lucide-vue-next";
import { api, errText } from "../../api.js";
import Modal from "../../components/Modal.vue";
import AuditLog from "./AuditLog.vue";

const TABS = [["privasi", "Data & Privasi"], ["audit", "Log audit"]];
const RETENTION = [7, 14, 30, 60, 90, 180, 365];
const SESSION = [[30, "30 menit"], [60, "1 jam"], [120, "2 jam"], [240, "4 jam"], [480, "8 jam"], [720, "12 jam"], [1440, "24 jam"]];
const DEFAULT_CONSENT = "Percakapan akan direkam dan diubah menjadi teks untuk membantu dokter menyusun rekam medis. Audio dihapus sesuai kebijakan retensi rumah sakit, dan hasil AI selalu ditinjau dokter.";

const tab = ref("privasi");
const d = ref(null), err = ref(""), notice = ref(""), busy = ref(""), confirmPurge = ref(false);
const retention = ref(""), consent = ref(""), session = ref("");

function fill(x) { d.value = x; retention.value = x.privacy.retention_custom ?? ""; consent.value = x.privacy.consent_text || ""; session.value = x.security.session_custom ?? ""; }
async function load() { err.value = ""; try { fill(await api("/admin/settings")); } catch (e) { err.value = errText(e); } }
onMounted(load);

async function save(name, path, json, ok) {
  err.value = ""; notice.value = ""; busy.value = name;
  try { const r = await api(path, { method: "PUT", json }); notice.value = typeof ok === "function" ? ok(r) : ok; await load(); }
  catch (e) { err.value = errText(e); } finally { busy.value = ""; }
}
const saveRetention = () => save("ret", "/admin/settings/privacy", { retention_days: retention.value === "" ? null : Number(retention.value) },
  (r) => `Masa simpan disimpan; ${r.transcripts_recalculated ?? 0} transkrip yang sudah tersimpan ikut dihitung ulang.`);
const saveConsent = () => save("con", "/admin/settings/privacy", { consent_text: consent.value.trim() || null }, "Teks persetujuan disimpan. Dokter melihatnya pada sesi berikutnya.");
const resetConsent = () => { consent.value = ""; return saveConsent(); };
const saveSession = () => save("ses", "/admin/settings/security", { session_minutes: session.value === "" ? null : Number(session.value) }, "Masa sesi disimpan. Berlaku pada login berikutnya.");
async function purge() {
  confirmPurge.value = false; busy.value = "purge"; notice.value = ""; err.value = "";
  try { const r = await api("/admin/settings/purge", { method: "POST" }); notice.value = `${r.transcripts_purged} transkrip kedaluwarsa dihapus.`; await load(); }
  catch (e) { err.value = errText(e); } finally { busy.value = ""; }
}
const n = (x) => new Intl.NumberFormat("id-ID").format(x);
const label = (m) => (m % 60 === 0 ? `${m / 60} jam` : `${m} menit`);
const retDirty = computed(() => (retention.value === "" ? null : Number(retention.value)) !== (d.value?.privacy.retention_custom ?? null));
const conDirty = computed(() => (consent.value.trim() || null) !== (d.value?.privacy.consent_text || null));
const sesDirty = computed(() => (session.value === "" ? null : Number(session.value)) !== (d.value?.security.session_custom ?? null));
</script>

<template>
  <div v-if="d" class="adm-wrap adm-wide">
    <div class="adm-tabs" role="tablist">
      <button v-for="t in TABS" :key="t[0]" class="adm-tab" :class="{ on: tab === t[0] }" role="tab" :aria-selected="tab === t[0]" @click="tab = t[0]">{{ t[1] }}</button>
    </div>
    <p v-if="err" class="banner bad" role="alert">{{ err }}</p>
    <p v-if="notice" class="adm-ok" role="status">{{ notice }}</p>
    <p v-if="d.keep_audio" class="banner bad" role="alert"><b>Mode uji aktif di server:</b> audio rekaman TIDAK dihapus setelah diproses. Hubungi pengelola server; jangan dipakai dengan data pasien nyata.</p>

    <template v-if="tab === 'privasi'">
      <section class="card adm-card">
        <div class="adm-head"><div><h2 class="h2">Retensi transkrip</h2><p>Berapa lama teks transkrip disimpan sebelum dihapus otomatis. Berlaku juga untuk transkrip yang sudah tersimpan.</p></div></div>
        <div class="adm-row">
          <select v-model="retention" class="input" style="max-width: 280px" aria-label="Masa simpan transkrip">
            <option value="">Bawaan server ({{ d.privacy.retention_default }} hari)</option>
            <option v-for="r in RETENTION" :key="r" :value="r">{{ r }} hari</option>
          </select>
          <button class="btn btn-primary" :disabled="!retDirty || busy === 'ret'" @click="saveRetention">{{ busy === "ret" ? "Menyimpan…" : "Simpan" }}</button>
          <span class="adm-hint">Berlaku sekarang: <b>{{ d.privacy.retention_days }} hari</b> · {{ n(d.transcripts.stored) }} transkrip tersimpan</span>
          <button v-if="d.transcripts.due_for_purge" class="btn adm-btn-sm adm-spacer" :disabled="busy === 'purge'" @click="confirmPurge = true"><Trash2 :size="13" />Hapus {{ n(d.transcripts.due_for_purge) }} yang kedaluwarsa</button>
        </div>
      </section>

      <section class="card adm-card">
        <div class="adm-head"><div><h2 class="h2">Teks persetujuan pasien</h2><p>Ditampilkan dokter sebelum merekam. Kosongkan untuk memakai teks bawaan aplikasi. Sebaiknya ditinjau pihak hukum/komite etik rumah sakit.</p></div></div>
        <textarea v-model="consent" class="adm-textarea" style="font-family: inherit; font-size: 14px; min-height: 100px" maxlength="2000" :placeholder="DEFAULT_CONSENT" aria-label="Teks persetujuan" />
        <div class="adm-row">
          <button class="btn btn-primary" :disabled="!conDirty || busy === 'con'" @click="saveConsent">Simpan teks</button>
          <button class="btn" :disabled="!d.privacy.consent_text || busy === 'con'" @click="resetConsent">Kembalikan ke teks bawaan</button>
          <span class="adm-hint adm-spacer">{{ consent.length }} / 2000</span>
        </div>
      </section>

      <section class="card adm-card">
        <div class="adm-head"><div><h2 class="h2">Masa sesi login</h2><p>Berapa lama pengguna tetap masuk sebelum diminta login ulang. Berlaku pada login berikutnya.</p></div></div>
        <div class="adm-row">
          <select v-model="session" class="input" style="max-width: 280px" aria-label="Masa sesi login">
            <option value="">Bawaan server ({{ label(d.security.session_default) }})</option>
            <option v-for="s in SESSION" :key="s[0]" :value="s[0]">{{ s[1] }}</option>
          </select>
          <button class="btn btn-primary" :disabled="!sesDirty || busy === 'ses'" @click="saveSession">{{ busy === "ses" ? "Menyimpan…" : "Simpan" }}</button>
          <span class="adm-hint">Berlaku sekarang: <b>{{ label(d.security.session_minutes) }}</b></span>
        </div>
      </section>

      <p class="adm-hint">Dikunci sistem dan tidak bisa dimatikan: audio dihapus segera setelah menjadi teks, consent wajib sebelum merekam, dan hasil AI wajib disetujui dokter sebelum dikirim.</p>
    </template>

    <AuditLog v-else />

    <Modal v-if="confirmPurge" :width="460" label="Bersihkan transkrip" @close="confirmPurge = false">
      <h2 class="adm-modal-h">Hapus {{ n(d.transcripts.due_for_purge) }} transkrip kedaluwarsa?</h2>
      <p class="muted">Isi teks transkrip yang sudah lewat masa simpan dihapus permanen. SOAP yang sudah disetujui dan riwayat sesi tidak ikut terhapus. Ini sama dengan pembersihan terjadwal, hanya dijalankan sekarang untuk RS Anda.</p>
      <div class="adm-modal-actions"><button class="btn" @click="confirmPurge = false">Batal</button><button class="btn btn-danger" @click="purge">Ya, hapus</button></div>
    </Modal>
  </div>
  <p v-else-if="err" class="banner bad" role="alert">{{ err }}</p>
</template>
