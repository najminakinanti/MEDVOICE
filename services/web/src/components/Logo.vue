<script setup>
// Logo resmi MedVoice (untuk latar terang). Versi latar gelap (panel kiri login): assets/logo-hero.png, dipakai di LoginView.
import logo from "../assets/logo.png";
defineProps({ size: { type: Number, default: 1 } });
</script>

<template>
  <img class="logo" :style="{ '--s': size }" :src="logo" alt="MedVoice — AI Clinical Documentation" />
</template>

<style scoped>
.logo { display: block; height: calc(40px * var(--s)); width: auto; }
</style>
