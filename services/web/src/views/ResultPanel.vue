<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Copy, Link2, Plus, ShieldCheck, Sparkles, X } from "lucide-vue-next";
import { api, errText } from "../api.js";
import { FIELD } from "../fields.js";
import { clockHM, dur, initials, mmss, sexAge } from "../format.js";
import ChatBubble from "../components/ChatBubble.vue";
import ClinicalItems from "../components/ClinicalItems.vue";
import CodesPanel from "../components/CodesPanel.vue";
import Modal from "../components/Modal.vue";
import { notifyParent } from "../widget.js";
import SubmittedPanel from "./SubmittedPanel.vue";

const props = defineProps({ session: Object });
const emit = defineEmits(["step", "reload", "next"]);
const id = () => props.session.id;

const EMPTY = "Tidak disebutkan";
const NOTICE = {
  stt_kosong_isi_manual: "Transkrip kosong. Isi SOAP secara manual.",
  json_llm_rusak_isi_manual: "Ekstraksi otomatis gagal dua kali. Isi SOAP secara manual.",
  kualitas_draft_rendah: "Kualitas draft rendah (banyak butir ditolak validator). Periksa dengan teliti.",
  pipeline_gagal_isi_manual: "Pemrosesan otomatis gagal. Isi SOAP secara manual.",
  transkrip_sudah_dihapus_sesuai_retensi: "Transkrip sudah dihapus sesuai kebijakan retensi.",
};
const SECTIONS = [["S", "Subjektif", "info"], ["O", "Objektif", "teal"], ["A", "Assessment", "warning"], ["P", "Plan", "purple"]];

const review = ref(null), loadErr = ref(""), tab = ref("info"), selectedItem = ref(null);
const draft = ref([]), lastSaved = ref(""), savedAt = ref(null), saveErr = ref("");
const ack = ref(false), busy = ref(false), actErr = ref(""), confirm = ref(false), copied = ref(false);
let uid = 0, timer = null, chain = Promise.resolve();

const status = computed(() => review.value?.session.status);
const readOnly = computed(() => status.value === "approved" || status.value === "submitted");
const items = computed(() => review.value?.items || []);
const codes = computed(() => review.value?.codes || []);
const segs = computed(() => review.value?.transcript.segments || []);
const coded = computed(() => items.value.filter((i) => codes.value.some((c) => c.item_id === i.id)));
const patient = computed(() => props.session.patient);
const flagged = computed(() => draft.value.filter((r) => r.flagged && r.text.trim() && r.text !== EMPTY).length);
const step = computed(() => (status.value === "submitted" ? 7 : status.value === "approved" ? 6 : ({ transkrip: 2, info: 3, soap: 5, kode: 5 }[tab.value] || 5)));
watch(step, (v) => emit("step", v), { immediate: true });

const STATUS_PILL = {
  review: ["pill-warning", "Draft AI · perlu review"], failed: ["pill-danger", "Isi manual"], approved: ["pill-success", "Disetujui"], submitted: ["pill-info", "Terkirim"],
};

async function load() {
  loadErr.value = "";
  try {
    review.value = await api(`/sessions/${id()}/review`);
    initDraft();
    notifyParent("review_loaded", id(), status.value);
    if (status.value === "submitted") tab.value = "done";
    else if (readOnly.value || !items.value.length) tab.value = "soap";
  } catch (e) { loadErr.value = errText(e); }
}
onMounted(load);
onBeforeUnmount(() => clearTimeout(timer));

// ---------- draft SOAP (autosimpan)
function initDraft() {
  const all = review.value.soap?.sentences || [];
  draft.value = [];
  for (const [sec] of SECTIONS) {
    const mine = all.filter((s) => s.section === sec);
    let rows = mine.filter((s) => !(s.text === EMPTY && !s.evidence_item_ids.length && mine.length > 1));
    if (!rows.length) rows = [{ id: null, section: sec, text: EMPTY, evidence_item_ids: [], flagged: false, is_ai_suspicion: false }];
    rows.forEach((r) => draft.value.push({ uid: ++uid, ...r }));
  }
  lastSaved.value = snapshot();
  savedAt.value = review.value.soap?.source === "dokter" ? new Date() : null;
}
const real = (r) => r.text.trim() && r.text.trim() !== EMPTY;
const snapshot = () => JSON.stringify(draft.value.filter((r) => r.text.trim()).map((r) => [r.section, r.text.trim()]));
const dirty = computed(() => snapshot() !== lastSaved.value);
watch(draft, () => {
  if (readOnly.value || !dirty.value) return;
  clearTimeout(timer); timer = setTimeout(() => save().catch(() => {}), 2500);
}, { deep: true });

function reconcile(d) {                      // server membuat id baru tiap versi: PUT berikutnya WAJIB memakai id terbaru
  for (const [sec] of SECTIONS) {
    const server = d.sentences.filter((s) => s.section === sec && s.text !== EMPTY);
    const mine = draft.value.filter((r) => r.section === sec && real(r));
    mine.forEach((r, i) => { const s = server[i]; if (s && s.text === r.text.trim()) Object.assign(r, { id: s.id, flagged: s.flagged, is_ai_suspicion: s.is_ai_suspicion, evidence_item_ids: s.evidence_item_ids }); });
    if (!mine.length) { const e = draft.value.find((r) => r.section === sec && r.text.trim() === EMPTY); const s = d.sentences.find((x) => x.section === sec); if (e && s) e.id = s.id; }
  }
}

function save(force = false) {
  clearTimeout(timer);
  const run = async () => {
    const snap = snapshot();
    if (!force && snap === lastSaved.value) return review.value.soap;
    const sentences = draft.value.filter((r) => r.text.trim()).map((r) => ({ id: r.id, section: r.section, text: r.text.trim() }));
    try {
      const d = await api(`/sessions/${id()}/soap`, { method: "PUT", json: { sentences } });
      review.value.soap = d; lastSaved.value = snap; savedAt.value = new Date(); saveErr.value = "";
      reconcile(d);
      return d;
    } catch (e) { saveErr.value = errText(e); throw e; }
  };
  const p = chain.then(run);
  chain = p.catch(() => {});
  return p;
}

const addRow = (sec) => draft.value.splice(draft.value.map((r) => r.section).lastIndexOf(sec) + 1, 0, { uid: ++uid, id: null, section: sec, text: "", evidence_item_ids: [], flagged: false, is_ai_suspicion: false });
function delRow(r) {
  const i = draft.value.indexOf(r);
  draft.value.splice(i, 1);
  if (!draft.value.some((x) => x.section === r.section)) draft.value.splice(i, 0, { uid: ++uid, id: null, section: r.section, text: EMPTY, evidence_item_ids: [], flagged: false, is_ai_suspicion: false });
}
const vFit = { mounted: fit, updated: fit };
function fit(el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; }
function goSource(r) {
  const first = r.evidence_item_ids.find((x) => items.value.some((i) => i.id === x));
  if (first) { selectedItem.value = first; tab.value = "info"; }
}
async function copySoap() {
  const t = SECTIONS.map(([s, n]) => `${n.toUpperCase()}\n` + draft.value.filter((r) => r.section === s && real(r)).map((r) => "- " + r.text.trim()).join("\n")).join("\n\n");
  try { await navigator.clipboard.writeText(t); copied.value = true; setTimeout(() => (copied.value = false), 1800); } catch { actErr.value = "Tidak bisa menyalin ke papan klip."; }
}

// ---------- sumber di transkrip
const selected = computed(() => items.value.find((i) => i.id === selectedItem.value) || null);
const hl = computed(() => new Set(selected.value ? selected.value.segment_idxs : []));
const srcBox = ref(null);
watch(selected, async (s) => {
  if (!s) return;
  await nextTick();
  const el = srcBox.value && srcBox.value.querySelector(".hlrow");
  if (el) srcBox.value.scrollTo({ top: Math.max(0, el.offsetTop - 60), behavior: "smooth" });
});
function pick(i) { selectedItem.value = i; }
const missedAt = (m) => { const s = segs.value.find((x) => x.start_ms <= m.start_ms && m.start_ms <= x.end_ms); if (s) { selectedItem.value = null; tab.value = "transkrip"; nextTick(() => document.getElementById("seg" + s.idx)?.scrollIntoView({ block: "center" })); } };

// ---------- setujui & kirim
async function finalize() {
  confirm.value = false; actErr.value = ""; busy.value = true;
  try {
    if (status.value !== "approved") {
      const d = await save(true);
      await api(`/sessions/${id()}/approve`, { method: "POST", json: { soap_id: d.id, acknowledge_flagged: ack.value } });
      review.value.session.status = "approved";
      notifyParent("approved", id(), "approved");
    }
    await api(`/sessions/${id()}/submit`, { method: "POST" });
    await load();
    notifyParent("submitted", id(), "submitted");
    emit("reload");
  } catch (e) {
    actErr.value = errText(e);
    try { review.value.session.status = (await api(`/sessions/${id()}`)).status; } catch { /* abaikan */ }
  } finally { busy.value = false; }
}
const canSend = computed(() => ack.value && !busy.value && !!draft.value.some(real));
</script>

<template>
  <div v-if="loadErr" class="banner bad" role="alert">{{ loadErr }}</div>
  <div v-else-if="!review" class="load"><span class="spinner" /></div>
  <SubmittedPanel v-else-if="status === 'submitted' && tab === 'done'" :session="session" :review="review" @next="emit('next')" @back="tab = 'soap'" />
  <div v-else class="res">
    <div v-for="n in review.notices" :key="n" class="banner" :class="{ bad: n === 'kualitas_draft_rendah' }">{{ NOTICE[n] || n }}</div>

    <section class="card top">
      <header class="hd">
        <span class="avatar lg">{{ initials(patient?.name || session.no_rawat) }}</span>
        <div class="who">
          <div class="nm">{{ patient?.name || "No. rawat " + session.no_rawat }}</div>
          <div class="caption">
            <template v-if="patient">RM {{ patient.rm }} · {{ sexAge(patient) }} · </template>Durasi rekaman {{ dur(session.started_at && session.finished_at ? Math.round((new Date(session.finished_at) - new Date(session.started_at)) / 1000) : null) }}
            <template v-if="session.started_at"> · {{ clockHM(session.started_at) }}<template v-if="session.finished_at">–{{ clockHM(session.finished_at) }}</template></template>
          </div>
        </div>
        <span class="pill" :class="(STATUS_PILL[status] || [''])[0]">{{ (STATUS_PILL[status] || [0, status])[1] }}</span>
        <button v-if="status === 'submitted'" class="btn btn-sm" @click="tab = 'done'">Ringkasan pengiriman</button>
      </header>

      <nav class="tabs" role="tablist">
        <button role="tab" :aria-selected="tab === 'transkrip'" :class="{ on: tab === 'transkrip' }" @click="tab = 'transkrip'">Transkrip</button>
        <button role="tab" :aria-selected="tab === 'info'" :class="{ on: tab === 'info' }" @click="tab = 'info'">Info Klinis <span class="n">{{ items.length }}</span></button>
        <button role="tab" :aria-selected="tab === 'soap'" :class="{ on: tab === 'soap' }" @click="tab = 'soap'">SOAP</button>
        <button role="tab" :aria-selected="tab === 'kode'" :class="{ on: tab === 'kode' }" @click="tab = 'kode'">Kode Terminologi <span class="n">{{ codes.length }}</span></button>
      </nav>

      <!-- Transkrip -->
      <div v-if="tab === 'transkrip'" class="pane tr">
        <div class="trl">
          <ChatBubble v-for="s in segs" :id="'seg' + s.idx" :key="s.idx" :speaker="s.speaker" :time="mmss(s.start_ms)" :text="s.text" :highlight="hl.has(s.idx)" />
          <div v-if="!segs.length" class="banner bad">{{ review.job_errors?.stt && review.job_errors.stt !== "None" ? `Pengenalan suara gagal (kode: ${review.job_errors.stt}). Periksa layanan STT.` : review.transcript.is_empty ? "Tidak ada ucapan terdeteksi pada rekaman." : "Transkrip tidak tersedia (mungkin sudah dihapus sesuai retensi)." }}</div>
        </div>
        <aside v-if="review.missed.length" class="missed">
          <h3 class="h2">Terlewat</h3><p class="caption">Istilah klinis yang terdengar tetapi tidak terekstrak.</p>
          <button v-for="(m, i) in review.missed" :key="i" class="mi" @click="missedAt(m)"><b>[{{ m.kind }}]</b> {{ m.mention }} <span class="caption">@ {{ mmss(m.start_ms) }}</span></button>
        </aside>
      </div>

      <!-- Info Klinis -->
      <div v-else-if="tab === 'info'" class="pane two">
        <ClinicalItems :items="items" :selected="selectedItem" @select="pick" />
        <aside class="src card">
          <header class="sh"><Link2 :size="16" class="lk" /><h3 class="h2">Sumber di transkrip</h3><span class="caption sp">{{ selected ? FIELD[selected.field]?.label : "" }}</span></header>
          <div ref="srcBox" class="sb">
            <ChatBubble v-for="s in segs" :key="s.idx" :class="{ hlrow: hl.has(s.idx) }" :speaker="s.speaker" :time="mmss(s.start_ms)" :text="s.text" :highlight="hl.has(s.idx)" :marks="hl.has(s.idx) && selected ? [selected.evidence] : []" />
          </div>
          <footer class="sf">Klik item di kiri untuk melihat kalimat asalnya</footer>
        </aside>
      </div>

      <!-- SOAP -->
      <div v-else-if="tab === 'soap'" class="pane two soap">
        <div class="se">
          <section v-for="[sec, name, tone] in SECTIONS" :key="sec" class="sec">
            <header class="sh2"><span class="bd" :class="tone">{{ sec }}</span><h3 class="h2">{{ name }}</h3></header>
            <div class="rows">
              <template v-for="r in draft.filter((x) => x.section === sec)" :key="r.uid">
                <div class="row" :class="{ flg: r.flagged, sus: r.is_ai_suspicion, empty: r.text === EMPTY }">
                  <textarea v-model="r.text" v-fit rows="1" :readonly="readOnly" :aria-label="`${name}`" :placeholder="'Tulis ' + name.toLowerCase() + '…'" />
                  <span v-if="r.flagged" class="pill pill-warning nodot">Perlu dicek</span>
                  <span v-if="r.is_ai_suspicion" class="pill pill-purple nodot">Dugaan</span>
                  <button v-if="r.evidence_item_ids.length" class="ib" title="Lihat sumber di transkrip" aria-label="Lihat sumber" @click="goSource(r)"><Link2 :size="15" /></button>
                  <button v-if="!readOnly" class="ib" title="Hapus kalimat" aria-label="Hapus kalimat" @click="delRow(r)"><X :size="15" /></button>
                </div>
              </template>
            </div>
            <button v-if="!readOnly" class="add" @click="addRow(sec)"><Plus :size="14" />Tambah kalimat</button>
          </section>
          <footer class="sfoot">
            <span class="saved caption" :class="{ bad: saveErr }">{{ saveErr || (readOnly ? "Disetujui; tidak dapat diedit." : dirty ? "Menyimpan…" : savedAt ? "Disimpan otomatis " + clockHM(savedAt) : "Draft AI belum diedit") }}</span>
            <button class="btn btn-sm" @click="copySoap"><Copy :size="14" />{{ copied ? "Tersalin" : "Salin" }}</button>
          </footer>
        </div>
        <CodesPanel :session-id="session.id" :codes="codes" :items="items" :read-only="readOnly" @error="(m) => (actErr = m)">
          <template #footer>
            <div class="ap">
              <p v-if="flagged" class="banner" style="padding: 8px 10px">{{ flagged }} kalimat bertanda "Perlu dicek". Periksa sebelum menyetujui.</p>
              <label class="check"><input v-model="ack" type="checkbox" :disabled="status === 'submitted'" /><span>Saya telah meninjau SOAP dan kode di atas</span></label>
              <p v-if="actErr" class="banner bad" role="alert" style="padding: 8px 10px">{{ actErr }}</p>
              <button class="btn btn-navy btn-lg btn-block" :disabled="!canSend || status === 'submitted'" data-testid="approve" @click="confirm = true">
                <ShieldCheck :size="18" />{{ busy ? "Memproses…" : status === "approved" ? "Kirim ulang ke SIMRS" : "Setujui & Kirim ke SIMRS" }}
              </button>
            </div>
          </template>
        </CodesPanel>
      </div>

      <!-- Kode -->
      <div v-else class="pane two soap">
        <div class="se">
          <h3 class="h2">Butir yang dikodekan</h3>
          <p class="caption" style="margin-bottom: 12px">Klik butir untuk membuka kutipan asli di tab Info Klinis.</p>
          <ClinicalItems :items="coded" :selected="selectedItem" @select="(i) => { pick(i); tab = 'info'; }" />
        </div>
        <CodesPanel :session-id="session.id" :codes="codes" :items="items" :read-only="readOnly" @error="(m) => (actErr = m)">
          <template #footer>
            <div class="ap">
              <label class="check"><input v-model="ack" type="checkbox" :disabled="status === 'submitted'" /><span>Saya telah meninjau SOAP dan kode di atas</span></label>
              <p v-if="actErr" class="banner bad" role="alert" style="padding: 8px 10px">{{ actErr }}</p>
              <button class="btn btn-navy btn-lg btn-block" :disabled="!canSend || status === 'submitted'" @click="confirm = true"><ShieldCheck :size="18" />{{ status === "approved" ? "Kirim ulang ke SIMRS" : "Setujui & Kirim ke SIMRS" }}</button>
            </div>
          </template>
        </CodesPanel>
      </div>

      <footer v-if="tab === 'info'" class="foot">
        <span class="caption ft"><Sparkles :size="15" class="sp2" />{{ items.length }} informasi klinis terdeteksi · ditinjau sebelum disusun jadi SOAP</span>
        <button class="btn btn-primary" @click="tab = 'soap'">Lanjut ke SOAP</button>
      </footer>
    </section>

    <Modal v-if="confirm" :width="440" label="Setujui dan kirim" @close="confirm = false">
      <h2 class="h1">Setujui &amp; kirim ke SIMRS?</h2>
      <p class="muted" style="margin: 10px 0 20px">Setelah disetujui, SOAP dan kode tidak dapat diedit. Dokter bertanggung jawab atas isi catatan.</p>
      <div class="cf"><button class="btn" @click="confirm = false">Batal</button><button class="btn btn-navy" data-testid="approve-confirm" @click="finalize">Setujui &amp; Kirim</button></div>
    </Modal>
  </div>
</template>

<style scoped>
.load { display: grid; place-items: center; padding: 60px; }
.res { display: grid; gap: 14px; max-width: 1400px; margin: 0 auto; }
.top { overflow: hidden; }
.hd { display: flex; align-items: center; gap: 14px; padding: 16px 20px; flex-wrap: wrap; } .who { flex: 1; min-width: 0; } .nm { font-weight: 700; font-size: 16px; }
.tabs { display: flex; gap: 8px; padding: 0 12px; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); overflow-x: auto; }
.tabs button { display: inline-flex; align-items: center; gap: 8px; height: 48px; padding: 0 16px; border: 0; background: none; color: var(--muted); font-weight: 500; border-bottom: 2px solid transparent; white-space: nowrap; margin-bottom: -1px; }
.tabs button.on { color: var(--purple-600); font-weight: 700; border-bottom-color: var(--purple-600); }
.n { display: inline-grid; place-items: center; min-width: 20px; height: 20px; padding: 0 6px; border-radius: 999px; background: var(--purple-100); color: var(--purple-600); font-size: 11px; font-weight: 700; }
.pane { padding: 20px; }
.two { display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, 420px); gap: 20px; align-items: start; }
.soap { grid-template-columns: minmax(0, 1fr) minmax(340px, 400px); }
.src { display: flex; flex-direction: column; max-height: 640px; min-height: 420px; overflow: hidden; }
.sh { display: flex; align-items: center; gap: 8px; padding: 14px 16px; border-bottom: 1px solid var(--border); } .lk { color: var(--purple-600); } .sp { margin-left: auto; }
.sb { flex: 1; overflow-y: auto; padding: 10px 8px; position: relative; } .sf { padding: 12px 16px; border-top: 1px solid var(--border); font-size: 12px; color: var(--subtle); }
.tr { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 20px; } .trl { max-width: 860px; }
.missed { align-self: start; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 14px; display: grid; gap: 6px; } .mi { text-align: left; border: 0; background: none; padding: 6px 8px; border-radius: 6px; } .mi:hover { background: var(--bg); }
.foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 20px; border-top: 1px solid var(--border); flex-wrap: wrap; } .ft { display: flex; align-items: center; gap: 8px; font-size: 13px; } .sp2 { color: var(--purple-600); }

.se { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); }
.sec { padding: 16px 20px; border-bottom: 1px solid var(--border); } .sec:last-of-type { border-bottom: 0; }
.sh2 { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.bd { display: inline-grid; place-items: center; width: 32px; height: 32px; border-radius: 8px; font-weight: 700; } .bd.info { background: var(--info-bg); color: var(--info); } .bd.teal { background: var(--teal-bg); color: var(--teal); } .bd.warning { background: var(--warning-bg); color: var(--warning); } .bd.purple { background: var(--purple-100); color: var(--purple-600); }
.rows { display: grid; gap: 4px; padding-left: 44px; }
.row { display: flex; align-items: flex-start; gap: 6px; padding: 2px 6px; border-radius: 8px; border: 1px solid transparent; } .row:hover, .row:focus-within { border-color: var(--border); }
.row.flg { background: var(--warning-bg); border-color: #f2d49c; } .row.sus { background: var(--purple-50); }
.row textarea { flex: 1; min-width: 0; border: 0; outline: 0; resize: none; background: transparent; line-height: 1.6; padding: 4px 0; overflow: hidden; } .row.empty textarea { color: var(--subtle); font-style: italic; }
.row .pill { margin-top: 5px; } .ib { flex: none; width: 28px; height: 28px; margin-top: 2px; border: 0; background: none; color: var(--subtle); border-radius: 6px; display: grid; place-items: center; opacity: 0; } .row:hover .ib, .row:focus-within .ib { opacity: 1; } .ib:hover { background: var(--bg); color: var(--ink); }
.add { margin: 6px 0 0 44px; display: inline-flex; align-items: center; gap: 4px; border: 0; background: none; color: var(--purple-600); font-size: 13px; font-weight: 600; padding: 4px 6px; border-radius: 6px; } .add:hover { background: var(--purple-50); }
.sfoot { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; border-top: 1px solid var(--border); } .saved.bad { color: var(--danger); }
.ap { display: grid; gap: 10px; padding: 14px 16px 16px; border-top: 1px solid var(--border); }
.cf { display: flex; justify-content: flex-end; gap: 10px; }
@media (max-width: 1100px) { .two, .soap, .tr { grid-template-columns: 1fr; } .src { max-height: 420px; } .rows { padding-left: 0; } .add { margin-left: 0; } }
</style>
