<script setup>
import { useRouter } from "vue-router";
import { logout, setUnauthorizedHandler } from "./api.js";

const router = useRouter();
setUnauthorizedHandler(() => { logout(); router.replace({ path: "/login", query: { next: router.currentRoute.value.fullPath } }); });
</script>

<template><router-view /></template>
