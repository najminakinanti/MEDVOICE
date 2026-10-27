<script setup>
// Halaman admin RS. Layar utama mengikuti Figma "09 Â· Admin": dua kolom (Pengguna | Integrasi SIMRS + Data & Privasi).
// Halaman Integrasi SIMRS dan Pengaturan tetap ada sebagai halaman detail. Superadmin: daftar rumah sakit + pengguna per rumah sakit.
// Profil sendiri ada di menu "Profil Saya" (semua peran).
import { computed } from "vue";
import { useRoute } from "vue-router";
import { isSuperadmin } from "../api.js";
import AppShell from "../components/AppShell.vue";
import AdminIntegration from "./admin/AdminIntegration.vue";
import AdminSettings from "./admin/AdminSettings.vue";
import AdminUsers from "./admin/AdminUsers.vue";
import SuperadminUsers from "./admin/SuperadminUsers.vue";

const route = useRoute();
const page = computed(() => (["integrasi", "pengaturan"].includes(route.params.page) ? route.params.page : "pengguna"));
const title = computed(() => ({ integrasi: "Integrasi SIMRS", pengaturan: "Pengaturan" }[page.value] || (isSuperadmin() ? "Pengguna & Rumah Sakit" : "Pengguna & Pengaturan")));
</script>

<template>
  <AppShell :title="title" crumb="Admin RS" :search="false">
    <template v-if="page === 'pengguna'">
      <SuperadminUsers v-if="isSuperadmin()" />
      <AdminUsers v-else />
    </template>
    <AdminIntegration v-else-if="page === 'integrasi'" />
    <AdminSettings v-else />
  </AppShell>
</template>
