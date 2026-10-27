<script setup>
import { ref } from "vue";
import { Mic, ShieldCheck, X } from "lucide-vue-next";
import { api, auth, errText } from "../api.js";
import { initials, sexAge } from "../format.js";
import { listMics, loadMicPrefs, saveMicPrefs } from "../live/devices.js";
import Modal from "./Modal.vue";

// patient = baris antrean; null = sesi manual (petugas mengetik no. rawat).
const props = defineProps({ patient: Object, unit: { type: String, default: "Poli Umum" } });
const emit = defineEmits(["close", "started"]);

const METHODS = ["Lisan", "Tanda tangan digital", "Formulir kertas"];
const agreed = ref(false), byGuardian = ref(false), method = ref("Lisan"), noRawat = ref(props.patient?.no_rawat || "");
const busy = ref(false), err = ref("");
const mics = ref(null), prefs = ref(loadMicPrefs()), micErr = ref("");

async function openMics(e) {
  if (!e.target.open || mics.value) return;
  try { mics.value = await listMics(); } catch { micErr.value = "Izin mikrofon belum diberikan; pilihan perangkat belum tersedia."; }
}

async function start() {
  if (!agreed.value || !noRawat.value.trim()) return;
  busy.value = true; err.value = "";
  try {
    saveMicPrefs(prefs.value);
    const d = await api("/sessions", { method: "POST", json: {
      no_rawat: noRawat.value.trim(),
      consent: { given: true, recorded_by: auth.me?.display_name || "-", note: `Metode: ${method.value}${byGuardian.value ? "; diberikan oleh wali" : ""}` },
    } });
    emit("started", d.id);
  } catch (e) { err.value = errText(e); busy.value = false; }
}
</script>

<template>
  <Modal label="Persetujuan Perekaman" @close="emit('close')">
    <header class="head">
      <span class="ic"><ShieldCheck :size="22" /></span>
      <div><h2 class="h1">Persetujuan Perekaman</h2><p class="caption">Wajib sebelum sesi dimulai</p></div>
      <button class="x" aria-label="Tutup" @click="emit('close')"><X :size="20" /></button>
    </header>

    <div class="pt">
      <template v-if="patient">
        <span class="avatar lg">{{ initials(patient.name) }}</span>
        <div><div class="nm">{{ patient.name }}</div><div class="caption">RM {{ patient.rm }} · {{ sexAge(patient) }} · {{ unit }}</div></div>
      </template>
      <div v-else class="field" style="flex: 1">
        <label for="nr">No. rawat</label>
        <input id="nr" v-model="noRawat" class="input" placeholder="Nomor rawat pasien" autocomplete="off" />
      </div>
    </div>

    <p class="body">{{ auth.me?.consent_text || "Percakapan akan direkam dan diubah menjadi teks untuk membantu dokter menyusun rekam medis. Audio dihapus sesuai kebijakan retensi rumah sakit, dan hasil AI selalu ditinjau dokter." }}</p>

    <label class="check"><input v-model="agreed" type="checkbox" /><span>Pasien/wali sudah dijelaskan dan menyetujui perekaman</span></label>
    <label class="check"><input v-model="byGuardian" type="checkbox" /><span>Persetujuan diberikan oleh wali (bukan pasien)</span></label>

    <div class="label" style="margin-top: 18px">Metode persetujuan</div>
    <div class="chips">
      <button v-for="m in METHODS" :key="m" type="button" class="chip" :class="{ active: method === m }" @click="method = m">{{ m }}</button>
    </div>

    <details class="mic" @toggle="openMics">
      <summary>Atur mikrofon</summary>
      <p v-if="micErr" class="caption">{{ micErr }}</p>
      <template v-else-if="mics">
        <div class="field"><label for="m1">Mikrofon dokter</label>
          <select id="m1" v-model="prefs.dokter" class="input"><option value="">Bawaan sistem</option><option v-for="m in mics" :key="m.id" :value="m.id">{{ m.label }}</option></select></div>
        <div class="field"><label for="m2">Mikrofon pasien (opsional)</label>
          <select id="m2" v-model="prefs.pasien" class="input"><option value="">Tidak ada — satu mikrofon</option><option v-for="m in mics" :key="m.id" :value="m.id">{{ m.label }}</option></select></div>
        <p class="caption">Dua mikrofon: label Dokter/Pasien pasti. Satu mikrofon: pembicara ditandai "Suara" dan diagnosis dikonfirmasi dokter.</p>
      </template>
      <p v-else class="caption">Memuat perangkat…</p>
    </details>

    <p v-if="err" class="banner bad" role="alert" style="margin-top: 14px">{{ err }}</p>
    <footer class="foot">
      <button class="btn btn-lg" @click="emit('close')">Pasien menolak</button>
      <button class="btn btn-primary btn-lg" :disabled="!agreed || !noRawat.trim() || busy" @click="start"><Mic :size="18" />{{ busy ? "Membuat sesi…" : "Setuju & Mulai Rekam" }}</button>
    </footer>
  </Modal>
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
.ic { display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 12px; background: var(--purple-100); color: var(--purple-600); }
.head > div { flex: 1; } .x { border: 0; background: none; color: var(--muted); width: 36px; height: 36px; border-radius: 8px; display: grid; place-items: center; } .x:hover { background: var(--bg); }
.pt { display: flex; align-items: center; gap: 12px; background: var(--bg); border-radius: var(--radius-sm); padding: 14px 16px; }
.nm { font-weight: 600; }
.body { margin: 18px 0; color: var(--muted); line-height: 1.7; }
.check { margin-bottom: 12px; } .check span { font-size: 14px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.mic { margin-top: 16px; font-size: 13px; } .mic summary { cursor: pointer; color: var(--purple-600); font-weight: 600; }
.mic .field { margin-top: 10px; }
.foot { display: flex; justify-content: flex-end; gap: 10px; margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--border); }
@media (max-width: 520px) { .foot { flex-direction: column-reverse; } .foot .btn { width: 100%; } }
</style>
