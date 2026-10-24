<script setup>
import { onMounted, onUnmounted, ref } from "vue";
const props = defineProps({ width: { type: Number, default: 560 }, label: String });
const emit = defineEmits(["close"]);
const box = ref(null);
const onKey = (e) => { if (e.key === "Escape") emit("close"); };
let prev = null;
onMounted(() => { prev = document.activeElement; window.addEventListener("keydown", onKey); box.value?.focus(); });
onUnmounted(() => { window.removeEventListener("keydown", onKey); prev && prev.focus && prev.focus(); });
</script>

<template>
  <Teleport to="body">
    <div class="back" @mousedown.self="emit('close')">
      <div ref="box" class="modal" role="dialog" aria-modal="true" :aria-label="props.label" tabindex="-1" :style="{ maxWidth: width + 'px' }"><slot /></div>
    </div>
  </Teleport>
</template>

<style scoped>
.back { position: fixed; inset: 0; z-index: 100; background: rgba(14, 26, 46, .45); display: grid; place-items: center; padding: 16px; overflow-y: auto; }
.modal { width: 100%; background: var(--surface); border-radius: 16px; padding: 28px; box-shadow: var(--shadow-pop); outline: 0; }
</style>
