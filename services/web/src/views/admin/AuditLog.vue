<script setup>
// Log audit rumah sakit: siapa melakukan apa, kapan, dari IP mana. Hanya metadata (tak ada isi transkrip/kata sandi/kunci).
import { onMounted, ref, watch } from "vue";
import { Download, Search } from "lucide-vue-next";
import { api, auth, errText } from "../../api.js";

const GROUPS = [["", "Semua"], ["login", "Masuk"], ["klinis", "Klinis"], ["simrs", "SIMRS & webhook"], ["admin", "Admin"]];
const PAGE = 25;
const group = ref(""), q = ref(""), page = ref(1), data = ref(null), err = ref(""), loading = ref(false), busy = ref(false);

const query = () => { const p = new URLSearchParams(); if (group.value) p.set("group", group.value); if (q.value.trim()) p.set("q", q.value.trim()); return p; };
async function load() {
  loading.value = true; err.value = "";
  try { const p = query(); p.set("limit", PAGE); p.set("offset", (page.value - 1) * PAGE); data.value = await api("/admin/audit?" + p); }
  catch (e) { err.value = errText(e); } finally { loading.value = false; }
}
onMounted(load);
watch([group, page], load);
let timer;
watch(q, () => { clearTimeout(timer); timer = setTimeout(() => { page.value = 1; load(); }, 300); });
const pick = (g) => { group.value = g; page.value = 1; };

async function exportCsv() {
  busy.value = true; err.value = "";
  try {                                     // token hanya di memori halaman (bukan cookie), jadi unduh lewat fetch + blob
    const r = await fetch("/v1/admin/audit.csv?" + query(), { headers: { Authorization: "Bearer " + auth.token } });
    if (!r.ok) throw new Error(String(r.status));
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(await r.blob()), download: "log-audit.csv" });
    a.click(); URL.revokeObjectURL(a.href);
  } catch { err.value = "Ekspor gagal. Coba lagi."; } finally { busy.value = false; }
}
const when = (iso) => new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).replace(/\./g, ":");
const total = () => data.value?.total || 0;
const pages = () => Math.max(1, Math.ceil(total() / PAGE));
const TONE = { "auth.login_failed": "pill-warning", "webhook.failed": "pill-danger" };
</script>

<template>
  <section class="card adm-box" aria-label="Log audit">
    <header class="adm-cardhead">
      <h2>Log audit</h2><span class="adm-count">{{ total() }}</span>
      <div class="adm-row" style="gap: 6px; margin-left: 8px">
        <button v-for="g in GROUPS" :key="g[0]" class="chip" :class="{ active: group === g[0] }" @click="pick(g[0])">{{ g[1] }}</button>
      </div>
      <label class="adm-grow adm-spacer" style="max-width: 240px; position: relative">
        <Search :size="14" style="position: absolute; left: 10px; top: 9px; color: var(--subtle)" />
        <input v-model="q" class="input" style="height: 32px; padding-left: 30px; font-size: 13px" placeholder="Cari pelaku, aksi, IP" aria-label="Cari log audit" />
      </label>
      <button class="btn adm-btn-sm" :disabled="busy || !total()" @click="exportCsv"><Download :size="14" />Ekspor CSV</button>
    </header>
    <p v-if="err" class="banner bad" role="alert" style="margin: 12px 20px">{{ err }}</p>
    <div class="adm-scroll">
      <table class="adm-table adm-fig" style="min-width: 720px">
        <thead><tr><th style="width: 150px">WAKTU</th><th style="width: 190px">PELAKU</th><th>AKSI</th><th>KETERANGAN</th><th style="width: 120px">IP</th></tr></thead>
        <tbody>
          <tr v-for="i in data?.items || []" :key="i.id">
            <td class="adm-sub" style="font-size: 13px; white-space: nowrap">{{ when(i.at) }}</td>
            <td><div class="adm-name" style="font-size: 13px">{{ i.actor }}</div><div class="adm-sub">{{ i.actor_type }}</div></td>
            <td><span class="pill nodot" :class="TONE[i.action]">{{ i.label }}</span></td>
            <td class="adm-sub" style="font-size: 12px; word-break: break-word">{{ i.detail || "—" }}</td>
            <td class="adm-mono" style="font-size: 12px">{{ i.ip || "—" }}</td>
          </tr>
          <tr v-if="data && !data.items.length"><td colspan="5" class="adm-empty">{{ loading ? "Memuat…" : "Belum ada catatan yang cocok." }}</td></tr>
        </tbody>
      </table>
    </div>
    <footer class="adm-cardhead" style="border-top: 1px solid var(--border); border-bottom: 0; justify-content: space-between">
      <span class="adm-hint">Hanya metadata. Isi transkrip, kata sandi, dan kunci tidak pernah masuk log. Ekspor CSV juga tercatat di sini.</span>
      <span class="adm-row"><button class="btn btn-sm" :disabled="page <= 1" @click="page--">Sebelumnya</button>
        <span class="adm-sub">{{ page }} / {{ pages() }}</span>
        <button class="btn btn-sm" :disabled="page >= pages()" @click="page++">Berikutnya</button></span>
    </footer>
  </section>
</template>
