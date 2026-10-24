<script setup>
// Pendekatan logo dari desain (gelombang + mikrofon, gradien ungu). Ganti dengan berkas resmi dari Figma bila tersedia:
// taruh di src/assets/logo.svg dan pakai <img> di sini.
defineProps({ light: Boolean, markOnly: Boolean, size: { type: Number, default: 1 } });
</script>

<template>
  <div class="logo" :style="{ '--s': size }">
    <svg class="mark" viewBox="0 0 112 60" aria-hidden="true">
      <defs>
        <linearGradient id="lg1" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#9b7fe8" /><stop offset="1" stop-color="#3f2a96" />
        </linearGradient>
      </defs>
      <path d="M4 34h16l8-20 9 36 10-44 10 50 8-26h8" fill="none" stroke="url(#lg1)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" />
      <rect x="86" y="6" width="18" height="30" rx="9" fill="none" stroke="#5b3fc8" stroke-width="4" />
      <path d="M81 30a14 14 0 0 0 28 0M95 44v10M87 54h16" fill="none" stroke="#5b3fc8" stroke-width="4" stroke-linecap="round" />
      <path d="M91 16v10M95 12v18M99 16v10" stroke="#9b7fe8" stroke-width="2.4" stroke-linecap="round" />
    </svg>
    <div v-if="!markOnly" class="word">
      <div class="name"><span :class="light ? 'l1' : 'n'">Med</span><span :class="light ? 'l2' : 'p'">Voice</span></div>
      <div class="tag" :class="{ light }">AI Clinical Documentation</div>
    </div>
  </div>
</template>

<style scoped>
.logo { display: inline-flex; align-items: center; gap: calc(8px * var(--s)); }
.mark { width: calc(66px * var(--s)); height: calc(35px * var(--s)); }
.name { font-weight: 800; font-size: calc(26px * var(--s)); line-height: 1; letter-spacing: -0.02em; }
.n { color: var(--navy-900); } .p { color: var(--purple-600); } .l1, .l2 { color: #fff; }
.tag { font-size: calc(8.5px * var(--s)); color: var(--muted); margin-top: calc(3px * var(--s)); letter-spacing: .01em; }
.tag.light { color: rgba(255, 255, 255, .75); }
</style>
