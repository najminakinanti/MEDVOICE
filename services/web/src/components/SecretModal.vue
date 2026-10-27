<script setup>
// Dialog "tampil sekali" untuk kata sandi sementara (pengguna baru, atur ulang, admin pertama RS baru).
import { ref } from "vue";
import { Check, Copy } from "lucide-vue-next";
import Modal from "./Modal.vue";

defineProps({ title: String, who: String, login: String, pw: String });
const emit = defineEmits(["close"]);
const copied = ref(false);
async function copy(text) {
  try { await navigator.clipboard.writeText(text); copied.value = true; setTimeout(() => (copied.value = false), 1500); } catch { /* izin clipboard ditolak */ }
}
</script>

<template>
  <Modal :width="520" label="Kata sandi sementara" @close="emit('close')">
    <h2 class="adm-modal-h">{{ title }}</h2>
    <p class="muted">Berikan data ini ke <b>{{ who }}</b> lewat jalur aman. Kata sandi <b>hanya tampil sekali</b> dan tidak bisa dilihat lagi setelah jendela ini ditutup.</p>
    <dl class="adm-kv" style="margin-top: 14px">
      <dt>Login (email/NIP)</dt><dd class="adm-mono">{{ login }}</dd>
      <dt>Kata sandi sementara</dt>
      <dd><div class="adm-secret"><span class="adm-mono">{{ pw }}</span>
        <button class="btn btn-sm" @click="copy(pw)"><component :is="copied ? Check : Copy" :size="14" />{{ copied ? "Tersalin" : "Salin" }}</button></div></dd>
    </dl>
    <div class="adm-modal-actions"><button class="btn btn-primary" @click="emit('close')">Sudah saya catat</button></div>
  </Modal>
</template>
