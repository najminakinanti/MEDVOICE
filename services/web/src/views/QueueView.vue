<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { CircleCheck, Clock, FileText, Mic, Plus, RefreshCw, Users } from "lucide-vue-next";
import { api, errText } from "../api.js";
import { dateLong, durLong, initials, sexAge } from "../format.js";
import { app } from "../store.js";
import AppShell from "../components/AppShell.vue";
import ConsentModal from "../components/ConsentModal.vue";

const router = useRouter();
const data = ref(null), err = ref(""), loading = ref(false), filter = ref("semua"), search = ref("");
const consentFor = ref(undefined);     // undefined = tertutup, null = sesi manual, objek = pasien antrean

async function load() {
  loading.value = true; err.value = "";
  try { data.value = await api("/queue"); } catch (e) { err.value = errText(e); } finally { loading.value = false; }
}
onMounted(load);

const items = computed(() => (data.value?.items || []).filter((i) => {
  const q = search.value.trim().toLowerCase();
  return !q || (i.name + " " + i.rm + " " + i.complaint).toLowerCase().includes(q);
}));
const counts = computed(() => {
  const all = data.value?.items || [];
  return { semua: all.length, menunggu: all.filter((i) => i.state === "menunggu").length, selesai: all.filter((i) => i.state === "selesai").length };
});
const shown = computed(() => items.value.filter((i) => filter.value === "semua" || i.state === filter.value));
const stats = computed(() => data.value?.stats || {});

const STATE = {
  selesai: ["pill-success", "Selesai"], diperiksa: ["pill-purple", "Sedang diperiksa"], menunggu: ["", "Menunggu"], belum_hadir: ["pill-warning", "Belum hadir"],
};
function open(i) { app.activeSessionId = i.session.id; router.push(`/session/${i.session.id}`); }
function started(id) { consentFor.value = undefined; app.activeSessionId = id; router.push({ path: `/session/${id}`, query: { autostart: "1" } }); }
</script>

<template>
  <AppShell title="Antrean Pasien" crumb="Beranda" :unit="data?.unit || 'Poli Umum'" v-model:query="search">
    <p v-if="err" class="banner bad" role="alert">{{ err }}</p>

    <section class="stats">
      <div class="card st"><span class="ic p"><Users :size="22" /></span><div><div class="l">Pasien hari ini</div><div class="v">{{ stats.today ?? "–" }}</div></div></div>
      <div class="card st"><span class="ic g"><CircleCheck :size="22" /></span><div><div class="l">Selesai</div><div class="v">{{ stats.done ?? "–" }}</div></div></div>
      <div class="card st"><span class="ic w"><FileText :size="22" /></span><div><div class="l">SOAP perlu review</div><div class="v">{{ stats.review ?? "–" }}</div></div></div>
      <div class="card st"><span class="ic b"><Clock :size="22" /></span><div><div class="l">Rata-rata dokumentasi</div><div class="v">{{ durLong(stats.avg_doc_seconds) }}</div></div></div>
    </section>

    <section class="card tbl">
      <header class="th">
        <div class="t"><span class="h2">Antrean {{ data?.unit || "Poli Umum" }}</span><span class="caption">· {{ data?.date ? dateLong(data.date) : "" }}</span></div>
        <div class="acts">
          <button class="chip" :class="{ active: filter === 'semua' }" @click="filter = 'semua'">Semua ({{ counts.semua }})</button>
          <button class="chip" :class="{ active: filter === 'menunggu' }" @click="filter = 'menunggu'">Menunggu ({{ counts.menunggu }})</button>
          <button class="chip" :class="{ active: filter === 'selesai' }" @click="filter = 'selesai'">Selesai ({{ counts.selesai }})</button>
          <button class="btn btn-sm" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{ spin: loading }" />Sinkron SIMRS</button>
          <button class="btn btn-sm btn-navy" @click="consentFor = null"><Plus :size="15" />Sesi Manual</button>
        </div>
      </header>

      <div class="scroll">
        <table v-if="data?.supported">
          <thead><tr><th>JAM</th><th>PASIEN</th><th>DEMOGRAFI</th><th>KELUHAN AWAL</th><th>STATUS</th><th /></tr></thead>
          <tbody>
            <tr v-for="i in shown" :key="i.no_rawat" :class="{ cur: i.state === 'diperiksa' }">
              <td class="tm">{{ i.time }}</td>
              <td><div class="pt"><span class="avatar">{{ initials(i.name) }}</span><div><div class="nm">{{ i.name }}</div><div class="caption rm">RM {{ i.rm }}</div></div></div></td>
              <td class="dm">{{ sexAge(i) }}</td>
              <td>{{ i.complaint }}</td>
              <td><span class="pill" :class="STATE[i.state][0]">{{ STATE[i.state][1] }}</span></td>
              <td class="ac">
                <button v-if="i.state === 'selesai'" class="btn btn-sm" @click="open(i)">Lihat</button>
                <button v-else-if="i.state === 'diperiksa'" class="btn btn-sm btn-soft" @click="open(i)">Lanjutkan</button>
                <button v-else-if="i.state === 'belum_hadir'" class="btn btn-sm" disabled>Mulai Sesi</button>
                <button v-else class="btn btn-sm btn-primary" @click="consentFor = i"><Mic :size="14" />Mulai Sesi</button>
              </td>
            </tr>
            <tr v-if="!shown.length"><td colspan="6" class="empty">Tidak ada pasien pada daftar ini.</td></tr>
          </tbody>
        </table>
        <div v-else-if="data" class="empty big">
          <p class="h2">Antrean belum tersedia dari SIMRS ini</p>
          <p class="muted">Adapter SIMRS yang terpasang belum menyediakan daftar antrean. Mulai sesi dengan nomor rawat pasien.</p>
          <button class="btn btn-primary" @click="consentFor = null"><Plus :size="16" />Sesi Manual</button>
        </div>
        <div v-else class="empty"><span class="spinner" /></div>
      </div>
    </section>

    <ConsentModal v-if="consentFor !== undefined" :patient="consentFor" :unit="data?.unit || 'Poli Umum'" @close="consentFor = undefined" @started="started" />
  </AppShell>
</template>

<style scoped>
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.st { display: flex; align-items: center; gap: 16px; padding: 18px 20px; }
.ic { display: inline-grid; place-items: center; width: 44px; height: 44px; border-radius: 10px; }
.ic.p { background: var(--purple-100); color: var(--purple-600); } .ic.g { background: var(--success-bg); color: var(--success); }
.ic.w { background: var(--warning-bg); color: var(--warning); } .ic.b { background: var(--info-bg); color: var(--info); }
.l { font-size: 13px; color: var(--muted); } .v { font-size: 24px; font-weight: 700; color: var(--navy-900); line-height: 1.2; }
.tbl { overflow: hidden; }
.th { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 16px 20px; }
.t { display: flex; align-items: baseline; gap: 8px; } .acts { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; min-width: 760px; }
th { text-align: left; font-size: 11px; font-weight: 600; letter-spacing: .06em; color: var(--subtle); padding: 12px 16px; background: var(--bg); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
td { padding: 10px 16px; border-bottom: 1px solid var(--border); height: 60px; }
tr.cur td { background: var(--purple-50); }
.tm { color: var(--muted); width: 80px; } .dm { color: var(--muted); } .ac { text-align: right; width: 150px; }
.pt { display: flex; align-items: center; gap: 12px; } .nm { font-weight: 600; line-height: 1.25; } .rm { line-height: 1.2; }
.empty { padding: 40px; text-align: center; color: var(--muted); } .empty.big { display: grid; gap: 10px; justify-items: center; }
.spin { animation: spin .8s linear infinite; }
@media (max-width: 1100px) { .stats { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .stats { grid-template-columns: 1fr; } }
</style>
