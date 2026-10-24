<script setup>
// Layar "Kirim ke SIMRS" (desain 07): ringkasan apa yang terkirim. Hanya fakta dari server; tidak ada angka karangan.
import { computed } from "vue";
import { Activity, ArrowRight, CircleCheck, Download, FileText, Pill, ShieldCheck, Stethoscope } from "lucide-vue-next";
import { clockHM, dateLong, durLong } from "../format.js";

const props = defineProps({ session: Object, review: Object });
const emit = defineEmits(["next", "back"]);
const print = () => window.print();

const soap = computed(() => props.review.soap);
const codes = computed(() => props.review.codes || []);
const final = (sys) => codes.value.filter((c) => c.system === sys && c.final_code).map((c) => c.final_code);
const accepted = computed(() => codes.value.filter((c) => c.final_code).length);
const edited = computed(() => new Set((soap.value?.sentences || []).filter((s) => s.origin === "dokter_edit" || s.origin === "dokter_baru").map((s) => s.section)).size);
const docSeconds = computed(() => (soap.value?.approved_at && props.session.finished_at ? Math.round((new Date(soap.value.approved_at) - new Date(props.session.finished_at)) / 1000) : null));
const drugs = computed(() => props.review.items.filter((i) => i.field === "obat" && i.verdict !== "ditolak").length);
const parts = computed(() => [
  { ic: FileText, t: "Catatan SOAP", s: `Composition · ${new Set((soap.value?.sentences || []).map((x) => x.section)).size} bagian`, st: ["pill-success", "Terkirim"] },
  { ic: Stethoscope, t: "Diagnosis ICD-10", s: final("ICD10").join(", ") || "Tidak ada kode", st: final("ICD10").length ? ["pill-success", "Terkirim"] : ["", "Tidak ada"] },
  { ic: Activity, t: "Tindakan ICD-9-CM", s: final("ICD9CM").join(", ") || "Tidak ada kode", st: final("ICD9CM").length ? ["pill-success", "Terkirim"] : ["", "Tidak ada"] },
  { ic: Pill, t: "Resep / Terapi", s: `${drugs.value} item obat · tercantum dalam catatan SOAP`, st: ["pill-info", "Dalam SOAP"] },
  { ic: ShieldCheck, t: "Audit & persetujuan dokter", s: soap.value?.approved_at ? `Disetujui ${clockHM(soap.value.approved_at)}` : "", st: ["pill-success", "Tercatat"] },
]);
</script>

<template>
  <div class="ok">
    <section class="card box">
      <span class="big"><CircleCheck :size="34" /></span>
      <h2 class="h1 t">Rekam medis terkirim ke SIMRS</h2>
      <p class="muted c">{{ session.patient ? `${session.patient.name} · RM ${session.patient.rm} · ` : "" }}{{ session.started_at ? "Kunjungan " + dateLong(session.started_at) + ", " + clockHM(session.started_at) : "" }}</p>
      <div class="kpi">
        <div><span>Waktu dokumentasi</span><b>{{ durLong(docSeconds) }}</b></div>
        <div><span>Kode diterima</span><b>{{ accepted }} / {{ codes.length }}</b></div>
        <div><span>Diedit dokter</span><b>{{ edited }} bagian</b></div>
      </div>
      <ul class="parts">
        <li v-for="p in parts" :key="p.t">
          <span class="pi"><component :is="p.ic" :size="20" /></span>
          <span class="pt"><b>{{ p.t }}</b><span class="caption">{{ p.s }}</span></span>
          <span class="pill" :class="p.st[0]">{{ p.st[1] }}</span>
        </li>
      </ul>
      <div class="acts no-print">
        <button class="btn btn-lg" @click="emit('back')"><FileText :size="18" />Lihat catatan</button>
        <button class="btn btn-lg" @click="print"><Download :size="18" />Unduh PDF</button>
        <button class="btn btn-primary btn-lg" @click="emit('next')">Kembali ke antrean<ArrowRight :size="18" /></button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.ok { display: grid; place-items: start center; } .box { width: 100%; max-width: 620px; padding: 32px; display: grid; gap: 14px; justify-items: center; }
.big { display: grid; place-items: center; width: 72px; height: 72px; border-radius: 50%; background: var(--success-bg); color: var(--success); } .t { text-align: center; font-size: 22px; } .c { text-align: center; }
.kpi { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; } .kpi div { display: grid; padding: 8px 18px; background: var(--bg); border-radius: var(--radius-sm); text-align: center; } .kpi span { font-size: 12px; color: var(--muted); } .kpi b { color: var(--navy-900); }
.parts { list-style: none; margin: 10px 0 0; padding: 0; width: 100%; } .parts li { display: flex; align-items: center; gap: 14px; padding: 14px 0; border-bottom: 1px solid var(--border); }
.pi { display: grid; place-items: center; width: 40px; height: 40px; border-radius: 8px; background: var(--purple-100); color: var(--purple-600); flex: none; } .pt { flex: 1; display: grid; }
.acts { display: flex; gap: 12px; width: 100%; margin-top: 10px; } .acts .btn { flex: 1; }
@media (max-width: 520px) { .acts { flex-direction: column; } }
</style>
