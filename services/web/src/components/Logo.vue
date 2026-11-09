<script setup>
// Logo resmi MedVoice: logo.png untuk latar terang, logo-hero.png (teks putih) untuk mode gelap.
import logo from "../assets/logo.png";
import logoDark from "../assets/logo-hero.png";
import { theme } from "../theme.js";
const props = defineProps({ size: { type: Number, default: 1 }, dark: Boolean });   // dark: paksa versi teks putih (latar gelap/ungu)
</script>

<template>
  <img class="logo" :class="{ dark: props.dark || theme.dark }" :style="{ '--s': size }" :src="props.dark || theme.dark ? logoDark : logo" alt="MedVoice — AI Clinical Documentation" />
</template>

<style scoped>
.logo { display: block; height: calc(40px * var(--s)); width: auto; }
.logo.dark { height: calc(54px * var(--s)); margin: calc(-7px * var(--s)) 0; }   /* kanvas logo-hero lebih tinggi, samakan ukuran tampilnya */
</style>
