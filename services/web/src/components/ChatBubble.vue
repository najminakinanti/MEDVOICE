<script setup>
// Satu giliran bicara (desain "Transkrip Langsung"): avatar + nama + jam, lalu teks.
// Saat live: state listening ("Mendengarkan…"), partial (kata stabil tebal + sisa abu-abu), final.
import { computed } from "vue";
import { SPEAKER_LABEL } from "../live/useRecording.js";

const props = defineProps({
  speaker: String, time: String, text: { type: String, default: "" }, stable: { type: String, default: "" }, tail: { type: String, default: "" },
  state: { type: String, default: "final" }, highlight: Boolean, marks: { type: Array, default: () => [] },
});
const initials = computed(() => ({ dokter: "Dr", pasien: "Ps" }[props.speaker] || "Su"));
const live = computed(() => props.state === "listening" || props.state === "partial");
// Sorot kutipan bukti (Info Klinis) di dalam teks.
const parts = computed(() => {
  const t = props.text; if (!props.marks.length) return [{ s: t, m: false }];
  const lo = t.toLowerCase(); const hit = props.marks.map((m) => [lo.indexOf(m.toLowerCase()), m.length]).filter(([i]) => i >= 0).sort((a, b) => a[0] - b[0])[0];
  if (!hit) return [{ s: t, m: false }];
  return [{ s: t.slice(0, hit[0]), m: false }, { s: t.slice(hit[0], hit[0] + hit[1]), m: true }, { s: t.slice(hit[0] + hit[1]), m: false }].filter((p) => p.s);
});
</script>

<template>
  <div class="row" :class="[speaker, state, { hl: highlight }]">
    <span class="avatar lg" :class="speaker === 'dokter' ? 'dr' : speaker === 'pasien' ? 'ps' : ''">{{ initials }}</span>
    <div class="body">
      <div class="meta">
        <span class="who" :class="speaker">{{ SPEAKER_LABEL[speaker] || speaker }}</span>
        <span class="time">{{ time }}</span>
        <span v-if="live" class="listen"><i />{{ state === "listening" ? "Mendengarkan…" : "Mengetik…" }}</span>
      </div>
      <p v-if="state === 'final'" class="txt"><template v-for="(p, i) in parts" :key="i"><strong v-if="p.m" class="mk">{{ p.s }}</strong><template v-else>{{ p.s }}</template></template></p>
      <p v-else class="txt live-txt"><span v-if="stable" class="stable">{{ stable }}</span><span v-if="stable && tail"> </span><span class="tail">{{ tail }}</span><span class="caret" /></p>
    </div>
  </div>
</template>

<style scoped>
.row { display: flex; gap: 12px; padding: 10px 12px; border-radius: var(--radius-sm); }
.row.hl { background: var(--purple-100); }
.body { min-width: 0; flex: 1; }
.meta { display: flex; align-items: center; gap: 8px; font-size: 13px; line-height: 1.2; margin-bottom: 4px; }
.who { font-weight: 700; } .who.dokter { color: var(--navy-900); } .who.pasien { color: var(--teal); } .who.tidak_diketahui { color: var(--muted); }
.time { color: var(--subtle); font-size: 12px; font-variant-numeric: tabular-nums; }
.listen { display: inline-flex; align-items: center; gap: 6px; height: 20px; padding: 0 8px; border-radius: 999px; background: var(--purple-100); color: var(--purple-600); font-size: 12px; font-weight: 600; }
.listen i { width: 6px; height: 6px; border-radius: 50%; background: var(--purple-600); animation: pulse 1.1s ease-in-out infinite; }
.txt { font-size: 14px; line-height: 1.6; color: var(--ink); overflow-wrap: anywhere; }
.mk { color: var(--purple-700); font-weight: 700; }
.live-txt .stable { color: var(--ink); } .live-txt .tail { color: var(--subtle); }
.caret { display: inline-block; width: 2px; height: 1.05em; margin-left: 3px; vertical-align: text-bottom; background: var(--purple-600); animation: blink 1s steps(1) infinite; }
@keyframes blink { 50% { opacity: 0; } } @keyframes pulse { 50% { opacity: .35; transform: scale(.8); } }
</style>
