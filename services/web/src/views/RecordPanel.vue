<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { Mic, Pause, Play, Sparkles, Square, TriangleAlert, Upload, X } from "lucide-vue-next";
import { initials, mmss, clock, sexAge } from "../format.js";
import { listMics, loadMicPrefs, saveMicPrefs } from "../live/devices.js";
import { uploadFiles, useRecording } from "../live/useRecording.js";
import { errText } from "../api.js";
import ChatBubble from "../components/ChatBubble.vue";
import Waveform from "../components/Waveform.vue";

const props = defineProps({ session: Object, autostart: Boolean, mobile: Boolean });
const emit = defineEmits(["finished", "exit"]);
const sid = () => props.session.id;
const rec = useRecording(sid);
const { status, error, elapsedMs, levels, sttState, modelState, bubbles, micLabel, noSpeech } = rec;

const prefs = ref(loadMicPrefs()), mics = ref(null), micErr = ref("");
const files = ref({ dokter: null, pasien: null, mixed: null }), upErr = ref(""), upBusy = ref(false);
const chat = ref(null), stick = ref(true), confirmStop = ref(false);

const recording = computed(() => ["recording", "paused", "uploading"].includes(status.value) || rec.canRetry.value);
const patient = computed(() => props.session.patient);

const sttChip = computed(() => {
  switch (sttState.value) {
    case "ready": return modelState.value === "loading" ? ["pill-purple", "Menyiapkan model suara…"] : ["pill-success", "Transkrip langsung aktif"];
    case "reconnecting": return ["pill-warning", "Menyambung ulang…"];
    case "unavailable": return ["pill-warning", "Pratinjau tidak tersedia · rekaman tetap berjalan"];
    case "denied": return ["pill-danger", "Pratinjau ditolak server"];
    default: return ["pill-purple", "Menyambungkan…"];
  }
});

async function begin() {
  saveMicPrefs(prefs.value);
  await rec.start(prefs.value);
}
onMounted(async () => { if (props.autostart) begin(); else { try { mics.value = await listMics(); } catch { micErr.value = "Izin mikrofon belum diberikan."; } } });

async function stopNow() {
  confirmStop.value = false;
  if (await rec.stop()) emit("finished");
}

// gulir otomatis hanya bila pengguna sedang di bawah (tidak merebut kendali saat membaca ke atas)
const onScroll = () => { const e = chat.value; stick.value = !e || e.scrollHeight - e.scrollTop - e.clientHeight < 80; };
const sig = computed(() => bubbles.value.map((b) => b.id + b.state + b.stable.length + b.tail.length + b.text.length).join("|"));
watch(sig, async () => { if (!stick.value) return; await nextTick(); chat.value && (chat.value.scrollTop = chat.value.scrollHeight); });

const guard = (e) => { if (recording.value && status.value !== "uploading") { e.preventDefault(); e.returnValue = ""; } };
onMounted(() => window.addEventListener("beforeunload", guard));
onBeforeUnmount(() => window.removeEventListener("beforeunload", guard));
onBeforeRouteLeave(() => (recording.value && status.value !== "uploading" ? window.confirm("Rekaman sedang berjalan. Keluar akan menghentikan dan membuang rekaman ini. Keluar?") : true));

async function doUpload() {
  upErr.value = ""; upBusy.value = true;
  try { await uploadFiles(sid(), files.value); emit("finished"); } catch (e) { upErr.value = errText(e) || e.message; } finally { upBusy.value = false; }
}
const pick = (k, e) => { files.value[k] = e.target.files[0] || null; };
</script>

<template>
  <div class="rec" :class="{ mobile }">
    <section class="card main">
      <!-- Siap merekam (belum mulai) -->
      <div v-if="!recording" class="ready">
        <div class="ready-h">
          <span class="micbig"><Mic :size="30" /></span>
          <div><h2 class="h1" style="color: #fff">Siap merekam</h2><p class="rs">Pastikan mikrofon sudah benar, lalu mulai. Pasien sudah menyetujui perekaman.</p></div>
        </div>
        <div class="ready-b">
          <p v-if="error" class="banner bad" role="alert">{{ error }}</p>
          <div class="g2">
            <div class="field"><label for="d1">Mikrofon dokter</label>
              <select id="d1" v-model="prefs.dokter" class="input"><option value="">Bawaan sistem</option><option v-for="m in mics || []" :key="m.id" :value="m.id">{{ m.label }}</option></select></div>
            <div class="field"><label for="d2">Mikrofon pasien (opsional)</label>
              <select id="d2" v-model="prefs.pasien" class="input"><option value="">Tidak ada — satu mikrofon</option><option v-for="m in mics || []" :key="m.id" :value="m.id">{{ m.label }}</option></select></div>
          </div>
          <p v-if="micErr" class="caption">{{ micErr }}</p>
          <p class="caption">Dua mikrofon: label Dokter/Pasien pasti. Satu mikrofon: pembicara ditandai "Suara" dan diagnosis dikonfirmasi dokter.</p>
          <button class="btn btn-primary btn-lg" :disabled="status === 'starting'" @click="begin"><Mic :size="18" />{{ status === "starting" ? "Membuka mikrofon…" : "Mulai Rekam" }}</button>

          <details class="up">
            <summary><Upload :size="15" />Atau unggah file audio rekaman</summary>
            <p class="caption">Dua file (dokter + pasien) = label pembicara pasti. Satu file campuran = pembicara tidak diketahui. Format: wav, mp3, m4a, ogg, webm, flac.</p>
            <div class="g3">
              <div class="field"><label>Dokter</label><input type="file" accept="audio/*" @change="pick('dokter', $event)" /></div>
              <div class="field"><label>Pasien</label><input type="file" accept="audio/*" @change="pick('pasien', $event)" /></div>
              <div class="field"><label>ATAU campuran</label><input type="file" accept="audio/*" @change="pick('mixed', $event)" /></div>
            </div>
            <p v-if="upErr" class="banner bad">{{ upErr }}</p>
            <button class="btn" :disabled="upBusy" @click="doUpload">{{ upBusy ? "Mengunggah…" : "Unggah & proses" }}</button>
          </details>
        </div>
      </div>

      <!-- Sedang merekam -->
      <template v-else>
        <header class="bar">
          <button v-if="mobile" class="x" aria-label="Keluar" @click="emit('exit')"><X :size="22" /></button>
          <div class="micwrap" :class="{ live: status === 'recording' }"><span class="micbtn"><Mic :size="30" /></span></div>
          <div class="clock">
            <div class="state"><i :class="{ off: status !== 'recording' }" />{{ status === "recording" ? "MEREKAM" : status === "paused" ? "DIJEDA" : "MENGUNGGAH" }}</div>
            <div class="time" data-testid="timer">{{ mmss(elapsedMs) }}</div>
          </div>
          <Waveform class="wf" :levels="levels" :still="status !== 'recording'" :height="mobile ? 44 : 52" />
          <div class="btns">
            <button v-if="!mobile" class="btn jeda" :disabled="status === 'uploading'" @click="status === 'paused' ? rec.resume() : rec.pause()">
              <component :is="status === 'paused' ? Play : Pause" :size="16" />{{ status === "paused" ? "Lanjut" : "Jeda" }}
            </button>
            <button v-if="!mobile" class="btn btn-danger" :disabled="status === 'uploading'" data-testid="stop" @click="confirmStop = true"><Square :size="14" />{{ status === "uploading" ? "Mengunggah…" : "Selesai & Proses" }}</button>
          </div>
        </header>

        <div class="th">
          <h2 class="h2">Transkrip Langsung</h2>
          <span class="pill" :class="sttChip[0]" data-testid="stt-chip">{{ sttChip[1] }}</span>
          <span class="pill nodot">Bahasa Indonesia</span>
          <span class="mic caption">Mic: {{ micLabel }}</span>
        </div>
        <p v-if="noSpeech" class="banner err" role="status"><TriangleAlert :size="16" />Belum ada suara terdeteksi. Pastikan mikrofon benar dan tidak dibisukan, lalu bicara lebih dekat ke mikrofon. Rekaman tetap berjalan.</p>
        <p v-if="error" class="banner bad err" role="alert">{{ error }}
          <button v-if="rec.canRetry.value" class="btn btn-sm" @click="rec.upload().then((ok) => ok && emit('finished'))">Kirim ulang</button></p>

        <div ref="chat" class="chat" aria-live="polite" @scroll="onScroll">
          <ChatBubble v-for="b in bubbles" :key="b.ch + ':' + b.id" :speaker="b.speaker" :time="clock(b.wall)" :text="b.text" :stable="b.stable" :tail="b.tail" :state="b.state" />
          <p v-if="!bubbles.length" class="empty">{{ status === "paused" ? "Perekaman dijeda." : "Mulai berbicara — teks akan muncul di sini saat Anda bicara." }}</p>
        </div>

        <footer v-if="mobile" class="mbar">
          <button class="mb" :disabled="status === 'uploading'" @click="status === 'paused' ? rec.resume() : rec.pause()"><span class="c"><component :is="status === 'paused' ? Play : Pause" :size="20" /></span>{{ status === "paused" ? "Lanjut" : "Jeda" }}</button>
          <button class="mb big" :disabled="status === 'uploading'" data-testid="stop" @click="confirmStop = true"><span class="c red"><Square :size="22" /></span><b>Selesai</b></button>
          <span class="mb ghost" />
        </footer>
      </template>
    </section>

    <aside v-if="!mobile" class="side">
      <section class="card pt">
        <span class="avatar lg">{{ initials(patient?.name || session.no_rawat) }}</span>
        <div class="pi">
          <div class="nm">{{ patient?.name || "No. rawat " + session.no_rawat }}</div>
          <div class="caption" v-if="patient">RM {{ patient.rm }} · {{ sexAge(patient) }}</div>
          <div class="pills"><span class="pill pill-success">Consent tercatat</span><span v-if="patient?.unit" class="pill">{{ patient.unit }}</span></div>
        </div>
      </section>
      <section class="card det">
        <h3 class="h2"><Sparkles :size="18" class="sp" />Terdeteksi sejauh ini</h3>
        <p class="caption">Butir klinis (keluhan, riwayat, alergi, tanda vital) disusun setelah <b>Selesai &amp; Proses</b>, dari rekaman penuh, bukan dari teks sementara ini.</p>
        <div class="tip"><TriangleAlert :size="16" />Teks langsung hanya pratinjau; hasil akhir bisa lebih akurat.</div>
      </section>
    </aside>

    <div v-if="confirmStop" class="dlg-back" @mousedown.self="confirmStop = false">
      <div class="dlg" role="alertdialog" aria-label="Akhiri sesi">
        <h3 class="h2">Akhiri rekaman?</h3>
        <p class="muted">Rekaman akan diunggah dan diproses menjadi transkrip, SOAP, dan kode. Rekaman tidak dapat dilanjutkan setelah ini.</p>
        <div class="dlg-f"><button class="btn" @click="confirmStop = false">Lanjut merekam</button><button class="btn btn-danger" data-testid="stop-confirm" @click="stopNow">Selesai & Proses</button></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rec { display: grid; grid-template-columns: 1fr 380px; gap: 20px; height: 100%; min-height: 0; }
.main { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.bar { display: flex; align-items: center; gap: 16px; padding: 16px 20px; background: var(--grad-hero); color: #fff; flex: none; }
.micwrap { position: relative; flex: none; width: 76px; height: 76px; border-radius: 50%; display: grid; place-items: center; background: rgba(217, 54, 54, .28); }
.micwrap.live::after { content: ""; position: absolute; inset: -6px; border-radius: 50%; border: 2px solid rgba(217, 54, 54, .55); animation: ring 1.6s ease-out infinite; }
@keyframes ring { from { transform: scale(.9); opacity: 1; } to { transform: scale(1.25); opacity: 0; } }
.micbtn { width: 62px; height: 62px; border-radius: 50%; background: var(--danger); display: grid; place-items: center; }
.state { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; letter-spacing: .04em; color: #ffb4b4; }
.state i { width: 8px; height: 8px; border-radius: 50%; background: #ff6b6b; animation: pulse 1.2s ease-in-out infinite; } .state i.off { animation: none; background: #cbb8ff; }
@keyframes pulse { 50% { opacity: .35; } }
.time { font-size: 36px; font-weight: 700; line-height: 1.1; font-variant-numeric: tabular-nums; }
.wf { flex: 1 1 100px; max-width: 220px; min-width: 0; }
.btns { display: flex; gap: 10px; margin-left: auto; flex: none; }
.jeda { background: rgba(255, 255, 255, .16); border-color: transparent; color: #fff; } .jeda:hover:not(:disabled) { background: rgba(255, 255, 255, .26); }
.th { display: flex; align-items: center; gap: 10px; padding: 14px 20px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.mic { margin-left: auto; }
.err { margin: 12px 20px 0; }
.chat { flex: 1; overflow-y: auto; padding: 14px 20px 20px; display: flex; flex-direction: column; gap: 4px; min-height: 0; }
.empty { margin: auto; color: var(--subtle); text-align: center; }
.side { display: flex; flex-direction: column; gap: 16px; min-height: 0; overflow-y: auto; }
.pt { display: flex; gap: 12px; padding: 16px; } .nm { font-weight: 700; } .pills { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.det { padding: 18px; display: grid; gap: 12px; } .sp { color: var(--purple-600); vertical-align: -3px; margin-right: 8px; }
.tip { display: flex; gap: 8px; align-items: center; padding: 10px 12px; border: 1.5px dashed var(--purple-200); border-radius: var(--radius-sm); background: var(--purple-50); color: var(--purple-700); font-size: 13px; }

.ready { overflow-y: auto; }
.ready-h { display: flex; align-items: center; gap: 18px; padding: 24px; background: var(--grad-hero); color: #fff; }
.micbig { display: grid; place-items: center; width: 64px; height: 64px; border-radius: 50%; background: rgba(255, 255, 255, .16); }
.rs { color: rgba(255, 255, 255, .85); margin-top: 4px; }
.ready-b { padding: 24px; display: grid; gap: 14px; align-content: start; } .ready-b .btn-lg { justify-self: start; }
.g2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; } .g3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 10px 0; }
.up { margin-top: 12px; padding-top: 16px; border-top: 1px solid var(--border); } .up summary { cursor: pointer; font-weight: 600; color: var(--purple-600); display: flex; align-items: center; gap: 8px; }
.up .field label { font-size: 12px; } .up input[type=file] { font-size: 12px; max-width: 100%; }

.dlg-back { position: fixed; inset: 0; z-index: 100; background: rgba(14, 26, 46, .45); display: grid; place-items: center; padding: 16px; }
.dlg { background: var(--surface); border-radius: 16px; padding: 24px; max-width: 440px; width: 100%; display: grid; gap: 10px; box-shadow: var(--shadow-pop); }
.dlg-f { display: flex; justify-content: flex-end; gap: 10px; margin-top: 10px; }

/* Mobile (desain "10 · Mobile · Rekam") */
.rec.mobile { grid-template-columns: 1fr; position: fixed; inset: 0; z-index: 50; background: var(--surface); }
.rec.mobile .main { border: 0; border-radius: 0; box-shadow: none; }
.rec.mobile .bar { flex-direction: column; align-items: center; gap: 10px; padding: 18px 20px 22px; position: relative; text-align: center; }
.rec.mobile .x { position: absolute; right: 12px; top: 12px; border: 0; background: none; color: #fff; width: 40px; height: 40px; display: grid; place-items: center; }
.rec.mobile .micwrap { display: none; } .rec.mobile .clock { order: 1; } .rec.mobile .wf { order: 2; min-width: 0; width: 100%; } .rec.mobile .state { justify-content: center; order: 3; margin-top: 4px; color: #ff9b9b; }
.rec.mobile .time { font-size: 44px; }
.mbar { flex: none; display: flex; justify-content: space-around; align-items: flex-end; padding: 14px 12px calc(14px + env(safe-area-inset-bottom)); border-top: 1px solid var(--border); }
.mb { display: grid; justify-items: center; gap: 4px; border: 0; background: none; font-size: 12px; color: var(--muted); width: 80px; } .mb.ghost { visibility: hidden; }
.mb .c { display: grid; place-items: center; width: 52px; height: 52px; border-radius: 50%; background: var(--bg); color: var(--navy-900); }
.mb .c.red { width: 72px; height: 72px; background: var(--danger); color: #fff; box-shadow: 0 0 0 8px rgba(217, 54, 54, .14); } .mb.big b { color: var(--ink); }
@media (max-width: 1100px) { .rec:not(.mobile) { grid-template-columns: 1fr; } .side { display: none; } }
@media (max-width: 640px) { .g2, .g3 { grid-template-columns: 1fr; } }
</style>
