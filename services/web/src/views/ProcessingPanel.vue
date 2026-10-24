<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { Check, CircleAlert } from "lucide-vue-next";
import { api } from "../api.js";
import { mmss } from "../format.js";
import ChatBubble from "../components/ChatBubble.vue";

const props = defineProps({ session: Object });
const emit = defineEmits(["done"]);
const LABEL = { stt: "Mengubah suara menjadi teks", extract: "Mengekstrak informasi klinis", validate: "Memverifikasi dengan bukti ucapan", map_codes: "Mencocokkan kode ICD", soap: "Menyusun draft SOAP" };
const jobs = ref(props.session.jobs || []), segs = ref([]), shown = ref(false);
let timer = null, alive = true;

const rows = computed(() => Object.keys(LABEL).map((k) => ({ k, label: LABEL[k], st: (jobs.value.find((j) => j.kind === k) || {}).status || "queued" })));
const firstPending = computed(() => rows.value.findIndex((r) => r.st !== "succeeded"));

async function poll() {
  try {
    const s = await api(`/sessions/${props.session.id}`);
    jobs.value = s.jobs;
    if (s.status !== "processing") return emit("done");
    const stt = s.jobs.find((j) => j.kind === "stt");
    if (stt && stt.status === "succeeded" && !shown.value) {          // transkrip tampil segera, tanpa menunggu ekstraksi
      shown.value = true;
      try { segs.value = (await api(`/sessions/${props.session.id}/review`)).transcript.segments; } catch { /* tampil di layar hasil */ }
    }
  } catch { /* coba lagi */ }
  if (alive) timer = setTimeout(poll, 2500);
}
onMounted(poll);
onBeforeUnmount(() => { alive = false; clearTimeout(timer); });
</script>

<template>
  <div class="proc">
    <section class="card box">
      <h2 class="h1">Memproses rekaman…</h2>
      <p class="muted">Biasanya 1–3 menit tergantung panjang percakapan. Halaman ini diperbarui otomatis.</p>
      <ol class="jobs">
        <li v-for="(r, i) in rows" :key="r.k" :class="[r.st, { cur: i === firstPending && r.st !== 'failed' }]">
          <span class="ic"><Check v-if="r.st === 'succeeded'" :size="14" :stroke-width="3.4" /><CircleAlert v-else-if="r.st === 'failed'" :size="16" /><span v-else-if="r.st === 'running' || i === firstPending" class="spinner sm" /></span>
          {{ r.label }}
        </li>
      </ol>
    </section>
    <section v-if="segs.length" class="card box">
      <h3 class="h2">Transkrip</h3>
      <ChatBubble v-for="s in segs" :key="s.idx" :speaker="s.speaker" :time="mmss(s.start_ms)" :text="s.text" />
    </section>
  </div>
</template>

<style scoped>
.proc { max-width: 760px; margin: 0 auto; display: grid; gap: 16px; }
.box { padding: 24px; display: grid; gap: 10px; }
.jobs { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 12px; }
li { display: flex; align-items: center; gap: 12px; color: var(--subtle); } li.succeeded { color: var(--ink); } li.cur { color: var(--ink); font-weight: 600; } li.failed { color: var(--danger); }
.ic { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; border: 1.5px solid var(--border); } li.succeeded .ic { background: var(--success); border-color: var(--success); color: #fff; } li.failed .ic { border: 0; }
.spinner.sm { width: 14px; height: 14px; border-width: 2px; }
</style>
