<script setup>
// Kartu "Integrasi SIMRS" ringkas (kolom kanan layar admin, sesuai Figma). Nilainya nyata: adapter aktif, webhook,
// dan riwayat pengiriman SOAP ke SIMRS. Pengaturan lengkap (kunci API, origin, rahasia webhook) ada di halaman Integrasi SIMRS.
import { computed, onMounted, ref } from "vue";
import { Link2 } from "lucide-vue-next";
import { api, errText } from "../../api.js";
import { dateShort } from "../../format.js";

const d = ref(null), res = ref(null), busy = ref(false), err = ref("");
onMounted(async () => { try { d.value = await api("/admin/integration"); } catch (e) { err.value = errText(e); } });

async function test() {
  busy.value = true; res.value = null; err.value = "";
  try { res.value = await api("/admin/integration/test", { method: "POST" }); } catch (e) { err.value = errText(e); } finally { busy.value = false; }
}
const badge = computed(() => {
  const t = res.value ? { ok: res.value.ok } : d.value?.last_test;                       // hasil terbaru, atau uji terakhir yang tersimpan
  return t ? (t.ok ? ["ok", "Terhubung"] : ["bad", "Gagal tersambung"]) : ["", "Belum diuji"];
});
const lastText = computed(() => {
  if (!d.value) return "Memuat…";
  if (!d.value.last_submission_at) return "Belum ada pengiriman ke SIMRS";
  return `Pengiriman terakhir: ${dateShort(d.value.last_submission_at)} · ${d.value.failed_7d} gagal (7 hari)`;
});
</script>

<template>
  <section class="card adm-box" aria-label="Integrasi SIMRS">
    <div class="adm-sidehead"><Link2 :size="18" class="adm-ico" /><h2>Integrasi SIMRS</h2><span class="adm-badge" :class="badge[0]">{{ badge[1] }}</span></div>
    <div class="adm-field"><span>Adapter SIMRS</span><div class="adm-ro">{{ d?.adapter || "—" }}</div></div>
    <div class="adm-field"><span>Webhook</span><div class="adm-ro" :class="{ muted: !d?.webhook_url }" :title="d?.webhook_url || ''">{{ d?.webhook_url || "Belum diatur" }}</div></div>
    <p v-if="err" class="banner bad" role="alert">{{ err }}</p>
    <p v-else-if="res && !res.ok" class="banner bad" role="alert">Uji koneksi gagal ({{ res.detail }}).</p>
    <div class="adm-foot">
      <span>{{ lastText }}</span>
      <button class="btn adm-btn-sm" :disabled="busy" @click="test">{{ busy ? "Menguji…" : "Tes Koneksi" }}</button>
    </div>
    <router-link to="/admin/integrasi" class="adm-link">Kelola kunci API, webhook, dan origin →</router-link>
  </section>
</template>
