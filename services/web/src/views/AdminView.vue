<script setup>
// Halaman admin belum memiliki API di engine: pengelolaan klien/dokter/kunci/webhook dilakukan lewat CLI admin.
// Ditampilkan jujur sebagai panduan, bukan formulir yang tidak berfungsi.
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppShell from "../components/AppShell.vue";

const route = useRoute();
const PAGES = {
  pengguna: { title: "Pengguna & Poli", cmds: ["create-doctor <client> <username> <simrs_user_id> \"<nama>\"", "create-client <nama> --origin https://web.rs.example"], note: "Dokter dan klien (rumah sakit) dibuat lewat CLI admin." },
  integrasi: { title: "Integrasi SIMRS", cmds: ["create-key <client> --label simrs", "revoke-key <prefix>", "set-webhook <client> https://simrs.rs.example/hook", "webhook-secret <client>"], note: "Kunci API, webhook, dan adapter SIMRS diatur lewat CLI admin; adapter dipilih per klien (--adapter)." },
  pengaturan: { title: "Pengaturan", cmds: ["purge"], note: "Retensi transkrip/audio dan model diatur lewat variabel lingkungan (.env); 'purge' menghapus transkrip kedaluwarsa." },
};
const page = computed(() => PAGES[route.params.page] || PAGES.pengguna);
</script>

<template>
  <AppShell :title="page.title" crumb="Admin RS" :search="false">
    <section class="card box">
      <h2 class="h2">Belum tersedia di antarmuka</h2>
      <p class="muted">{{ page.note }} Jalankan di server engine:</p>
      <pre><code v-for="c in page.cmds" :key="c">docker compose exec api python -m app.admin {{ c }}
</code></pre>
    </section>
  </AppShell>
</template>

<style scoped>
.box { padding: 24px; max-width: 760px; display: grid; gap: 12px; }
pre { margin: 0; padding: 14px 16px; background: var(--bg); border-radius: var(--radius-sm); overflow-x: auto; font-size: 13px; line-height: 1.7; }
</style>
