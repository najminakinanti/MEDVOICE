<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ChevronDown, Download, Eye, Filter, MoreHorizontal, Search } from "lucide-vue-next";
import { api, errText } from "../api.js";
import { dateShort, dur, initials } from "../format.js";
import AppShell from "../components/AppShell.vue";

const route = useRoute(), router = useRouter();
const PAGE = 8;
const q = ref(typeof route.query.q === "string" ? route.query.q : ""), status = ref(""), page = ref(1);
const data = ref(null), err = ref(""), loading = ref(false), menu = ref(null);
const STATUS = {
  submitted: ["pill-info", "Terkirim"], approved: ["pill-success", "Disetujui"], review: ["pill-warning", "Perlu review"], failed: ["pill-danger", "Gagal"],
  processing: ["pill-purple", "Diproses"], recording: ["pill-danger", "Merekam"], cancelled: ["", "Dibatalkan"],
};

let timer;
async function load() {
  loading.value = true; err.value = "";
  try {
    const p = new URLSearchParams({ limit: PAGE, offset: (page.value - 1) * PAGE });
    if (q.value.trim()) p.set("q", q.value.trim());
    if (status.value) p.set("status", status.value);
    data.value = await api("/sessions?" + p);
  } catch (e) { err.value = errText(e); } finally { loading.value = false; }
}
onMounted(load);
watch([status, page], load);
watch(q, () => { clearTimeout(timer); timer = setTimeout(() => { page.value = 1; load(); }, 300); });
watch(() => route.query.q, (v) => { if (typeof v === "string" && v !== q.value) q.value = v; });

const total = computed(() => data.value?.total || 0);
const pages = computed(() => Math.max(1, Math.ceil(total.value / PAGE)));
const from = computed(() => (total.value ? (page.value - 1) * PAGE + 1 : 0));
const to = computed(() => Math.min(total.value, page.value * PAGE));
const open = (s) => router.push(`/session/${s.id}`);

function csv() {
  const rows = [["Waktu", "Pasien", "No. RM", "No. rawat", "Kode ICD-10", "Durasi", "Status"], ...(data.value?.items || []).map((s) => [
    dateShort(s.created_at), s.patient?.name || "", s.patient?.rm || "", s.no_rawat, s.icd10 || "", dur(s.duration_s), (STATUS[s.status] || [0, s.status])[1]])];
  const body = rows.map((r) => r.map((c) => '"' + String(c).replace(/"/g, '""') + '"').join(",")).join("\n");
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob(["﻿" + body], { type: "text/csv" })), download: "riwayat-sesi.csv" });
  a.click(); URL.revokeObjectURL(a.href);
}
</script>

<template>
  <AppShell title="Riwayat Sesi" crumb="Dokumentasi" :search="false">
    <div class="bar">
      <label class="srch"><Search :size="16" /><input v-model="q" placeholder="Cari nama atau no. RM" aria-label="Cari" /></label>
      <label class="sel"><Filter :size="16" />
        <select v-model="status" aria-label="Status">
          <option value="">Status: Semua</option><option v-for="(v, k) in STATUS" :key="k" :value="k">{{ v[1] }}</option>
        </select><ChevronDown :size="14" />
      </label>
      <button class="btn sp" :disabled="!data?.items.length" @click="csv"><Download :size="16" />Ekspor CSV</button>
    </div>
    <p v-if="err" class="banner bad" role="alert">{{ err }}</p>

    <section class="card">
      <div class="scroll">
        <table>
          <thead><tr><th>WAKTU</th><th>PASIEN</th><th>KODE ICD-10</th><th>DURASI REKAM</th><th>STATUS</th><th /></tr></thead>
          <tbody>
            <tr v-for="s in data?.items || []" :key="s.id" class="r" tabindex="0" @click="open(s)" @keydown.enter="open(s)">
              <td class="tm">{{ dateShort(s.created_at) }}</td>
              <td><div class="pt"><span class="avatar">{{ initials(s.patient?.name || s.no_rawat) }}</span><div><div class="nm">{{ s.patient?.name || s.no_rawat }}</div><div v-if="s.patient" class="caption">RM {{ s.patient.rm }}</div></div></div></td>
              <td class="cd">{{ s.icd10 || "—" }}</td>
              <td class="tm">{{ dur(s.duration_s) }}</td>
              <td><span class="pill" :class="(STATUS[s.status] || [''])[0]">{{ (STATUS[s.status] || [0, s.status])[1] }}</span></td>
              <td class="mn" @click.stop>
                <button class="ib" aria-label="Aksi" @click="menu = menu === s.id ? null : s.id"><MoreHorizontal :size="18" /></button>
                <div v-if="menu === s.id" class="menu card"><button @click="open(s)"><Eye :size="14" />Buka sesi</button></div>
              </td>
            </tr>
            <tr v-if="data && !data.items.length"><td colspan="6" class="empty">{{ loading ? "Memuat…" : "Belum ada sesi yang cocok." }}</td></tr>
          </tbody>
        </table>
      </div>
      <footer class="pg">
        <span class="caption">Menampilkan {{ from }}–{{ to }} dari {{ total }} sesi</span>
        <div class="pn">
          <button class="btn btn-sm" :disabled="page <= 1" @click="page--">Sebelumnya</button>
          <button v-for="n in Math.min(pages, 5)" :key="n" class="btn btn-sm num" :class="{ cur: n === page }" @click="page = n">{{ n }}</button>
          <button class="btn btn-sm" :disabled="page >= pages" @click="page++">Berikutnya</button>
        </div>
      </footer>
    </section>
  </AppShell>
</template>

<style scoped>
.bar { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.srch, .sel { display: flex; align-items: center; gap: 8px; height: 40px; padding: 0 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); color: var(--subtle); }
.srch { flex: 1; min-width: 220px; max-width: 320px; } .srch input { flex: 1; border: 0; outline: 0; background: none; color: var(--ink); min-width: 0; }
.sel select { appearance: none; border: 0; outline: 0; background: none; color: var(--ink); padding-right: 4px; cursor: pointer; } .sp { margin-left: auto; }
.scroll { overflow-x: auto; } table { width: 100%; border-collapse: collapse; min-width: 720px; }
th { text-align: left; font-size: 11px; font-weight: 600; letter-spacing: .06em; color: var(--subtle); padding: 14px 16px; border-bottom: 1px solid var(--border); }
td { padding: 10px 16px; border-bottom: 1px solid var(--border); height: 60px; } .r { cursor: pointer; } .r:hover td, .r:focus-visible td { background: var(--purple-50); }
.tm { color: var(--muted); font-variant-numeric: tabular-nums; } .cd { color: var(--purple-600); font-weight: 700; }
.pt { display: flex; align-items: center; gap: 12px; } .nm { font-weight: 600; line-height: 1.25; }
.mn { position: relative; width: 56px; } .ib { width: 32px; height: 32px; border: 0; background: none; border-radius: 6px; color: var(--muted); display: grid; place-items: center; } .ib:hover { background: var(--bg); }
.menu { position: absolute; right: 12px; top: 44px; z-index: 5; padding: 6px; box-shadow: var(--shadow-pop); } .menu button { display: flex; align-items: center; gap: 8px; border: 0; background: none; padding: 8px 12px; border-radius: 6px; white-space: nowrap; } .menu button:hover { background: var(--bg); }
.empty { text-align: center; color: var(--muted); padding: 40px; }
.pg { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; gap: 12px; flex-wrap: wrap; } .pn { display: flex; gap: 6px; }
.num.cur { background: var(--purple-600); border-color: var(--purple-600); color: #fff; }
</style>
