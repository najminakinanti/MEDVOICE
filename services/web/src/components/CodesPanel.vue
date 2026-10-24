<script setup>
// Kode terminologi per butir (ICD-10 diagnosis, ICD-9-CM tindakan, dst.). Kode WAJIB dari tabel resmi (server memvalidasi).
import { computed, ref } from "vue";
import { Check, Search } from "lucide-vue-next";
import { api, errText } from "../api.js";

const props = defineProps({ sessionId: String, codes: { type: Array, default: () => [] }, items: { type: Array, default: () => [] }, readOnly: Boolean });
const emit = defineEmits(["updated", "error"]);

const GROUP = { ICD10: "DIAGNOSIS · ICD-10", ICD9CM: "TINDAKAN · ICD-9-CM", KFA: "OBAT · KFA", LOINC: "LABORATORIUM · LOINC", KPTL: "TINDAKAN · KPTL" };
const STATUS = { dinyatakan_dokter: "Dinyatakan dokter", dilaporkan_pasien: "Dilaporkan pasien", dinegasi: "Dinegasi", direncanakan: "Rencana" };
const REASON = {
  dugaan_tidak_dikodekan: "dugaan, tidak dikodekan", dinegasi_tidak_dikodekan: "dinegasi, tidak dikodekan", direncanakan_tidak_dikodekan: "direncanakan, tidak dikodekan",
  bukan_diagnosis_dokter: "bukan diagnosis dokter", llm_tidak_ada_yang_cocok: "tidak ada kandidat yang cocok", tidak_ada_kandidat: "tidak ada kandidat",
  keyakinan_rendah: "keyakinan rendah", kandidat_mirip: "kandidat mirip", bukan_peringkat_pertama: "bukan peringkat 1", butir_ditandai: "butir ditandai",
  kode_tidak_ada_di_tabel: "kode tidak ada di tabel",
};
const groups = computed(() => Object.keys(GROUP).map((sys) => ({ sys, label: GROUP[sys], rows: props.codes.filter((c) => c.system === sys) })).filter((g) => g.rows.length));
const itemOf = (c) => props.items.find((i) => i.id === c.item_id) || {};
const codeOf = (c) => c.final_code || c.suggested_code;
const dispOf = (c) => (c.final_code ? c.final_display : c.suggested_display);
const accepted = (c) => c.state === "terisi" || c.state === "dipilih_dokter";
const pct = (c) => (c.confidence == null ? null : Math.round(c.confidence * 100));
const tone = (c) => (c.confidence >= 0.85 ? "ok" : c.confidence >= 0.6 ? "mid" : "low");

const open = ref(null), q = ref(""), res = ref([]), busy = ref("");
let timer;
function toggle(c) { open.value = open.value === c.id ? null : c.id; q.value = ""; res.value = []; }
function search(c) {
  clearTimeout(timer); res.value = [];
  if (q.value.trim().length < 2) return;
  timer = setTimeout(async () => {
    try { res.value = await api(`/terminology/${c.system.toLowerCase()}/search?q=${encodeURIComponent(q.value.trim())}`); } catch { /* abaikan */ }
  }, 300);
}
async function set(c, code) {
  busy.value = c.id;
  try { Object.assign(c, await api(`/sessions/${props.sessionId}/codes/${c.id}`, { method: "PUT", json: { code } })); open.value = null; emit("updated"); }
  catch (e) { emit("error", errText(e)); } finally { busy.value = ""; }
}
</script>

<template>
  <section class="codes card">
    <header class="h"><h2 class="h2">Kode Terminologi</h2><span class="cnt">{{ codes.length }}</span></header>
    <div class="body">
      <p v-if="!codes.length" class="empty">Tidak ada diagnosis/tindakan yang dapat dikodekan.</p>
      <template v-for="g in groups" :key="g.sys">
        <div class="gl">{{ g.label }}</div>
        <article v-for="c in g.rows" :key="c.id" class="cd" :class="{ ok: accepted(c) }">
          <div class="r1">
            <span v-if="codeOf(c)" class="code">{{ codeOf(c) }}</span><span v-else class="code none">—</span>
            <span class="dn">{{ codeOf(c) ? dispOf(c) || itemOf(c).teks : itemOf(c).teks }}</span>
          </div>
          <div class="r2">
            <span class="meta">{{ STATUS[itemOf(c).status] || itemOf(c).status }}</span>
            <template v-if="pct(c) !== null"><span class="meta">·</span><span class="conf" :class="tone(c)">Keyakinan {{ pct(c) }}%</span></template>
            <span class="sp" />
            <template v-if="!readOnly">
              <button class="btn btn-sm" :disabled="busy === c.id" @click="toggle(c)">{{ codeOf(c) ? "Ganti" : "Cari kode" }}</button>
              <button v-if="c.state === 'saran' && c.suggested_code" class="btn btn-sm btn-primary" :disabled="busy === c.id" @click="set(c, c.suggested_code)"><Check :size="14" />Terima</button>
            </template>
            <span v-if="accepted(c)" class="pill pill-success nodot"><Check :size="13" :stroke-width="3" />Diterima</span>
          </div>
          <p v-if="c.reason && !accepted(c)" class="why">Catatan: {{ REASON[c.reason] || c.reason }}</p>
          <div v-if="open === c.id" class="pick">
            <button v-if="c.final_code" class="lnk" @click="set(c, null)">Kosongkan kode ini</button>
            <div v-for="k in c.candidates || []" :key="k.code" class="opt" @click="set(c, k.code)"><b>{{ k.code }}</b> {{ k.display }}</div>
            <div class="srch"><Search :size="14" /><input v-model="q" :placeholder="`Cari kode ${c.system}…`" @input="search(c)" /></div>
            <div v-for="r in res" :key="r.code" class="opt" @click="set(c, r.code)"><b>{{ r.code }}</b> {{ r.display }}</div>
          </div>
        </article>
      </template>
    </div>
    <slot name="footer" />
  </section>
</template>

<style scoped>
.codes { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.h { display: flex; align-items: center; gap: 8px; padding: 16px 18px; border-bottom: 1px solid var(--border); }
.cnt { display: inline-grid; place-items: center; min-width: 20px; height: 20px; padding: 0 6px; border-radius: 999px; background: var(--purple-100); color: var(--purple-600); font-size: 11px; font-weight: 700; }
.body { flex: 1; overflow-y: auto; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.gl { font-size: 11px; font-weight: 600; letter-spacing: .06em; color: var(--subtle); margin-top: 4px; }
.cd { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px 14px; display: grid; gap: 8px; } .cd.ok { background: var(--purple-50); border-color: var(--purple-200); }
.r1 { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; } .code { padding: 1px 8px; border-radius: 6px; background: var(--purple-100); color: var(--purple-600); font-weight: 700; font-size: 12px; } .code.none { background: var(--bg); color: var(--subtle); }
.dn { font-weight: 600; overflow-wrap: anywhere; }
.r2 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; } .meta { color: var(--subtle); } .sp { flex: 1; }
.conf { font-weight: 600; } .conf.ok { color: var(--success); } .conf.mid { color: var(--warning); } .conf.low { color: var(--danger); }
.why { font-size: 12px; color: var(--warning); }
.pick { display: grid; gap: 4px; border-top: 1px dashed var(--border); padding-top: 8px; }
.opt { padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 13px; } .opt:hover { background: var(--bg); }
.srch { display: flex; align-items: center; gap: 6px; padding: 0 10px; height: 34px; border: 1px solid var(--border); border-radius: 6px; color: var(--subtle); } .srch input { flex: 1; border: 0; outline: 0; background: none; color: var(--ink); min-width: 0; }
.lnk { justify-self: start; border: 0; background: none; color: var(--danger); font-size: 12px; font-weight: 600; padding: 4px 8px; }
.empty { color: var(--muted); padding: 16px 4px; }
</style>
