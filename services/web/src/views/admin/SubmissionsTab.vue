<script setup>
// Riwayat pengiriman SOAP ke SIMRS + Kirim ulang untuk yang gagal (idempoten: SOAP yang sudah terkirim tak dikirim dua kali).
import { onMounted, ref, watch } from "vue";
import { RotateCw } from "lucide-vue-next";
import { api, errText } from "../../api.js";
import { dateShort } from "../../format.js";

const PAGE = 15;
const status = ref(""), page = ref(1), data = ref(null), err = ref(""), notice = ref(""), loading = ref(false), busyId = ref("");
async function load() {
  loading.value = true; err.value = "";
  try { const p = new URLSearchParams({ limit: PAGE, offset: (page.value - 1) * PAGE }); if (status.value) p.set("status", status.value); data.value = await api("/admin/integration/submissions?" + p); }
  catch (e) { err.value = errText(e); } finally { loading.value = false; }
}
onMounted(load);
watch(status, () => { page.value = 1; load(); });
watch(page, load);

async function retry(it) {
  busyId.value = it.id; err.value = ""; notice.value = "";
  try {
    const r = await api(`/admin/integration/submissions/${it.id}/retry`, { method: "POST" });
    notice.value = r.ok ? `SOAP ${it.no_rawat} berhasil terkirim ke SIMRS.` : `Kirim ulang ${it.no_rawat} gagal lagi (${r.error_code || "tanpa kode"}).`;
    await load();
  } catch (e) { err.value = errText(e); await load(); } finally { busyId.value = ""; }
}
const STATUS = { succeeded: ["ok", "Berhasil"], failed: ["bad", "Gagal"], pending: ["warn", "Menunggu"] };
const pages = () => Math.max(1, Math.ceil((data.value?.total || 0) / PAGE));
</script>

<template>
  <section class="card adm-box" aria-label="Riwayat pengiriman">
    <header class="adm-cardhead">
      <h2>Riwayat pengiriman ke SIMRS</h2><span class="adm-count">{{ data?.total ?? 0 }}</span>
      <select v-model="status" class="input adm-spacer" style="width: 160px; height: 32px; font-size: 13px" aria-label="Filter status">
        <option value="">Semua status</option><option value="failed">Gagal</option><option value="succeeded">Berhasil</option>
      </select>
    </header>
    <p v-if="err" class="banner bad" role="alert" style="margin: 12px 20px">{{ err }}</p>
    <p v-if="notice" class="adm-ok" role="status" style="margin: 12px 20px">{{ notice }}</p>
    <div class="adm-scroll">
      <table class="adm-table adm-fig" style="min-width: 700px">
        <thead><tr><th>WAKTU</th><th>NO. RAWAT</th><th>DOKTER</th><th style="width: 110px">STATUS</th><th>KODE GALAT</th><th style="width: 130px" /></tr></thead>
        <tbody>
          <tr v-for="it in data?.items || []" :key="it.id">
            <td class="adm-sub" style="font-size: 13px; white-space: nowrap">{{ dateShort(it.submitted_at) }}</td>
            <td class="adm-mono" style="font-size: 13px">{{ it.no_rawat }}</td>
            <td class="adm-cell" style="white-space: normal">{{ it.doctor || "—" }}</td>
            <td><span class="adm-badge" :class="STATUS[it.status]?.[0]">{{ STATUS[it.status]?.[1] || it.status }}</span></td>
            <td class="adm-sub" style="font-size: 12px">{{ it.error_code || "—" }}<template v-if="it.response_code"> · HTTP {{ it.response_code }}</template></td>
            <td><button v-if="it.can_retry" class="btn adm-btn-sm" :disabled="busyId === it.id" @click="retry(it)"><RotateCw :size="13" />{{ busyId === it.id ? "Mengirim…" : "Kirim ulang" }}</button></td>
          </tr>
          <tr v-if="data && !data.items.length"><td colspan="6" class="adm-empty">{{ loading ? "Memuat…" : status ? "Tidak ada pengiriman dengan status ini." : "Belum ada pengiriman ke SIMRS." }}</td></tr>
        </tbody>
      </table>
    </div>
    <footer class="adm-cardhead" style="border-top: 1px solid var(--border); border-bottom: 0; justify-content: space-between">
      <span class="adm-hint">“Kirim ulang” hanya muncul untuk SOAP yang sudah disetujui dokter dan belum pernah berhasil terkirim.</span>
      <span class="adm-row"><button class="btn btn-sm" :disabled="page <= 1" @click="page--">Sebelumnya</button><span class="adm-sub">{{ page }} / {{ pages() }}</span>
        <button class="btn btn-sm" :disabled="page >= pages()" @click="page++">Berikutnya</button></span>
    </footer>
  </section>
</template>
