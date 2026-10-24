<script setup>
// Bar gelombang dari level mikrofon sebenarnya (bukan animasi palsu): level terbaru di kanan, bergulir ke kiri.
defineProps({ levels: { type: Array, required: true }, height: { type: Number, default: 48 }, still: Boolean });
</script>

<template>
  <div class="wave" :style="{ height: height + 'px' }" aria-hidden="true">
    <span v-for="(v, i) in levels" :key="i" :style="{ height: Math.max(3, (still ? 0 : v) * height) + 'px', opacity: 0.35 + 0.65 * (i / levels.length) }" />
  </div>
</template>

<style scoped>
.wave { display: flex; align-items: center; justify-content: flex-end; gap: 4px; overflow: hidden; min-width: 0; }
.wave span { width: 3px; border-radius: 2px; background: var(--purple-400); transition: height .08s linear; flex: none; }
</style>
