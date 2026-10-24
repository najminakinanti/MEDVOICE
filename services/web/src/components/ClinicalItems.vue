<script setup>
// Butir klinis hasil ekstraksi (desain "Info Klinis"): tiap butir menautkan ke kutipan asli di transkrip.
import { computed } from "vue";
import { Activity } from "lucide-vue-next";
import { FIELD } from "../fields.js";
import { mmss } from "../format.js";

const props = defineProps({ items: { type: Array, default: () => [] }, selected: String });
const emit = defineEmits(["select"]);

const STATUS = { dinyatakan_dokter: "Dinyatakan dokter", dilaporkan_pasien: "Dilaporkan pasien", dinegasi: "Dinegasi", direncanakan: "Direncanakan" };
const order = Object.keys(FIELD);
const rows = computed(() => [...props.items].sort((a, b) => order.indexOf(a.field) - order.indexOf(b.field) || a.start_ms - b.start_ms));
const text = (i) => i.teks || [i.nama, i.dosis].filter(Boolean).join(" ") || i.evidence;
</script>

<template>
  <div class="list">
    <p v-if="!rows.length" class="empty">Tidak ada butir klinis yang terdeteksi.</p>
    <button v-for="i in rows" :key="i.id" class="it" :class="[FIELD[i.field]?.tone, { on: selected === i.id, rej: i.verdict === 'ditolak' }]" @click="emit('select', i.id)">
      <span class="ic"><component :is="FIELD[i.field]?.icon || Activity" :size="20" /></span>
      <span class="tx">
        <span class="lb">{{ FIELD[i.field]?.label || i.field }}
          <span v-if="i.verdict === 'ditandai'" class="pill pill-warning nodot">Perlu dicek</span>
          <span v-if="i.verdict === 'ditolak'" class="pill pill-danger nodot">Ditolak validator</span>
          <span v-if="i.status === 'dinegasi' || i.status === 'direncanakan'" class="pill nodot">{{ STATUS[i.status] }}</span>
        </span>
        <span class="vl">{{ text(i) }}</span>
        <span v-if="i.verdict !== 'diterima' && i.reasons && i.reasons.length" class="rs">{{ i.reasons.join(", ") }}</span>
      </span>
      <span class="tm">{{ mmss(i.start_ms) }}</span>
    </button>
  </div>
</template>

<style scoped>
.list { display: flex; flex-direction: column; gap: 10px; }
.it { display: flex; align-items: flex-start; gap: 14px; text-align: left; width: 100%; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); transition: border-color .12s, background .12s; }
.it:hover { border-color: var(--purple-200); } .it.on { background: var(--purple-50); border-color: var(--purple-200); box-shadow: inset 0 0 0 1px var(--purple-200); }
.it.rej { opacity: .6; } .it.rej .vl { text-decoration: line-through; }
.ic { flex: none; display: inline-grid; place-items: center; width: 40px; height: 40px; border-radius: 8px; }
.danger .ic { background: var(--danger-bg); color: var(--danger); } .danger .lb { color: var(--danger); }
.warning .ic { background: var(--warning-bg); color: var(--warning); } .warning .lb { color: var(--warning); }
.success .ic { background: var(--success-bg); color: var(--success); } .success .lb { color: var(--success); }
.info .ic { background: var(--info-bg); color: var(--info); } .info .lb { color: var(--info); }
.purple .ic { background: var(--purple-100); color: var(--purple-600); } .purple .lb { color: var(--purple-600); }
.teal .ic { background: var(--teal-bg); color: var(--teal); } .teal .lb { color: var(--teal); }
.navy .ic { background: var(--bg); color: var(--navy-900); } .navy .lb { color: var(--navy-900); }
.tx { flex: 1; min-width: 0; display: grid; gap: 1px; }
.lb { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; flex-wrap: wrap; }
.vl { color: var(--ink); font-size: 14px; line-height: 1.5; overflow-wrap: anywhere; } .rs { font-size: 12px; color: var(--muted); }
.tm { font-size: 12px; color: var(--subtle); font-variant-numeric: tabular-nums; }
.empty { color: var(--muted); padding: 20px 4px; }
</style>
