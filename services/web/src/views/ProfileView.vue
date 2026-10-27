<script setup>
import AppShell from "../components/AppShell.vue";
import ProfilePanel from "./admin/ProfilePanel.vue";
</script>

<template>
  <AppShell title="Profil Saya" crumb="Akun" :search="false">
    <ProfilePanel />
  </AppShell>
</template>
