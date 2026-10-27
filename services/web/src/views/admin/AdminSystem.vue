<script setup>
// Sistem (khusus superadmin): status teknis server dan nilai bawaan. Bukan urusan admin RS.
import { computed, onMounted, ref } from "vue";
import { RefreshCw } from "lucide-vue-next";
import { api, errText } from "../../api.js";

const d = ref(null), err = ref(""), loading = ref(false);
async function load() { loading.value = true; err.value = ""; try { d.value = await api("/platform/system"); } catch (e) { err.value = errText(e); } finally { loading.value = false; } }
onMounted(load);
const stt = computed(() => d.value?.stt || {});
const llm = computed(() => d.value?.llm || {});
const llmState = computed(() => (!llm.value.reachable ? ["", "Tidak terjangkau"] : llm.value.installed === false ? ["pill-warning", "Model belum diunduh"] : ["pill-success", "Siap"]));
const KNOWN = ["ICD10", "ICD9CM", "KFA", "LOINC"];
const missing = computed(() => KNOWN.filter((c) => !(d.value?.terminology || []).some((t) => t.code === c)));
const n = (x) => new Intl.NumberFormat("id-ID").format(x);
const hours = (m) => (m % 60 === 0 ? `${m / 60} jam` : `${m} menit`);
</script>

<template>
  <div v-if="d" class="adm-wrap adm-wide">
    <div class="adm-row"><span class="adm-hint">Konfigurasi di bawah ini berasal dari server dan hanya bisa diubah oleh pengelola server (berkas <span class="adm-mono">.env</span>).</span>
      <button class="btn btn-sm adm-spacer" :disabled="loading" @click="load"><RefreshCw :size="14" />Muat ulang</button></div>
    <p v-if="err" class="banner bad" role="alert">{{ err }}</p>
    <p v-if="d.keep_audio" class="banner bad" role="alert"><b>Mode uji aktif:</b> audio rekaman TIDAK dihapus setelah diproses (KEEP_AUDIO). Matikan sebelum dipakai dengan data pasien nyata.</p>

    <section class="card adm-card">
      <div class="adm-head"><div><h2 class="h2">Status layanan</h2><p>Pemeriksaan langsung saat halaman dibuka.</p></div></div>
      <dl class="adm-kv">
        <dt>Pengenal suara (STT)</dt>
        <dd><span class="pill" :class="stt.reachable ? 'pill-success' : 'pill-danger'">{{ stt.reachable ? "Aktif" : "Tidak terjangkau" }}</span>
          <span v-if="stt.reachable" class="adm-sub"> &nbsp;{{ stt.device === "cuda" ? "GPU" : "CPU" }} · model akhir {{ stt.stream_final_model || stt.model }}</span></dd>
        <dt>Model bahasa (LLM)</dt>
        <dd><span class="pill" :class="llmState[0] || 'pill-danger'">{{ llmState[1] }}</span><span class="adm-sub"> &nbsp;{{ llm.model || "—" }}</span></dd>
        <dt>Pemakaian GPU bergantian</dt><dd>{{ d.gpu_timeshare ? "Aktif (STT dan LLM bergantian memakai VRAM)" : "Nonaktif" }}</dd>
        <dt>Model embedding (kode)</dt><dd>{{ d.embedding_model }}</dd>
      </dl>
    </section>

    <section class="card adm-card">
      <div class="adm-head"><div><h2 class="h2">Tabel terminologi</h2><p>Sumber kode untuk usulan ICD-10, obat, dan lab. Kode hanya diambil dari tabel resmi ini, tidak pernah dikarang AI.</p></div></div>
      <div class="adm-scroll">
        <table class="adm-table" style="min-width: 420px">
          <thead><tr><th>SISTEM</th><th>VERSI</th><th>JUMLAH KODE</th></tr></thead>
          <tbody>
            <tr v-for="t in d.terminology" :key="t.code + t.version"><td class="adm-name">{{ t.code }}</td><td>{{ t.version }}</td><td>{{ n(t.count) }}</td></tr>
            <tr v-if="!d.terminology.length"><td colspan="3" class="adm-empty">Belum ada tabel terminologi yang dimuat.</td></tr>
          </tbody>
        </table>
      </div>
      <p v-if="missing.length" class="adm-hint">Belum dimuat: {{ missing.join(", ") }}. Usulan kode untuk sistem ini dilewati sampai datanya dimuat.</p>
    </section>

    <section class="card adm-card">
      <div class="adm-head"><div><h2 class="h2">Batas dan nilai bawaan sistem</h2><p>Rumah sakit boleh menimpa masa simpan dan masa sesi di halaman Pengaturan mereka; angka di sini adalah nilai bawaannya.</p></div></div>
      <dl class="adm-kv">
        <dt>Ukuran audio maksimum</dt><dd>{{ d.max_audio_mb }} MB per berkas</dd>
        <dt>Masa simpan transkrip (bawaan)</dt><dd>{{ d.default_retention_days }} hari</dd>
        <dt>Masa sesi login (bawaan)</dt><dd>{{ hours(d.default_session_minutes) }}</dd>
        <dt>Batas percobaan login</dt><dd>{{ d.login_rate_per_min }} per menit per alamat IP</dd>
      </dl>
    </section>
  </div>
  <p v-else-if="err" class="banner bad" role="alert">{{ err }}</p>
</template>
