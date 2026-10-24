<script setup>
import { Check } from "lucide-vue-next";
// current: 1..6 (langkah aktif); langkah < current selesai. current = 7 -> semua selesai.
defineProps({ current: { type: Number, required: true } });
const STEPS = ["Rekam", "Transkripsi", "Ekstraksi", "SOAP & Kode", "Review", "Kirim"];
</script>

<template>
  <ol class="steps" aria-label="Tahap sesi">
    <li v-for="(s, i) in STEPS" :key="s" :class="{ done: i + 1 < current, on: i + 1 === current }">
      <span class="dot"><Check v-if="i + 1 < current" :size="13" :stroke-width="3.4" /><template v-else>{{ i + 1 }}</template></span>
      <span class="lbl">{{ s }}</span>
      <span v-if="i < STEPS.length - 1" class="bar" />
    </li>
  </ol>
</template>

<style scoped>
.steps { display: flex; align-items: center; gap: 0; list-style: none; margin: 0; padding: 0; }
li { display: flex; align-items: center; gap: 8px; color: var(--subtle); font-size: 13px; }
.dot { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; border: 1.5px solid var(--border); font-size: 11px; font-weight: 600; background: var(--surface); }
.bar { width: 24px; height: 2px; margin: 0 8px; background: var(--border); border-radius: 2px; }
li.done { color: var(--ink); } li.done .dot { background: var(--purple-600); border-color: var(--purple-600); color: #fff; } li.done .bar { background: var(--purple-600); }
li.on { color: var(--ink); font-weight: 600; } li.on .dot { background: var(--purple-600); border-color: var(--purple-600); color: #fff; }
@media (max-width: 1200px) { .lbl { display: none; } li.on .lbl { display: inline; } .bar { width: 14px; margin: 0 4px; } }
</style>
