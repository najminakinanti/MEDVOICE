<script setup>
// Kartu "Data & Privasi" (kolom kanan layar admin, sesuai Figma). Berbeda dari desain, tak ada sakelar palsu:
// consent dan approval dokter diwajibkan kode (tak bisa dimatikan), retensi diatur server, dan redaksi data pribadi belum ada.
import { computed, onMounted, ref } from "vue";
import { ShieldCheck } from "lucide-vue-next";
import { api, errText } from "../../api.js";

const d = ref(null), err = ref("");
onMounted(async () => { try { d.value = await api("/admin/settings"); } catch (e) { err.value = errText(e); } });
const audio = computed(() => (d.value?.keep_audio ? ["Ditahan (mode uji)", true] : ["Langsung dihapus", false]));
</script>

<template>
  <section class="card adm-box" aria-label="Data dan privasi">
    <div class="adm-sidehead"><ShieldCheck :size="18" class="adm-ico" /><h2>Data &amp; Privasi</h2></div>
    <p v-if="err" class="banner bad" role="alert">{{ err }}</p>
    <template v-if="d">
      <div class="adm-set"><div><b>Retensi transkrip</b><small>Transkrip dihapus otomatis setelah periode ini</small></div><span class="adm-selbox">{{ d.retention_days }} hari</span></div>
      <div class="adm-set"><div><b>Audio rekaman</b><small>Dihapus segera setelah diubah menjadi teks</small></div>
        <span class="adm-selbox" :style="audio[1] ? 'color: var(--danger); border-color: var(--danger)' : ''">{{ audio[0] }}</span></div>
      <div class="adm-set"><div><b>Redaksi data pribadi</b><small>Nama, NIK, no. HP, alamat</small></div><span class="adm-badge">Belum tersedia</span></div>
      <div class="adm-set"><div><b>Wajib consent sebelum rekam</b><small>Tidak bisa dimatikan per dokter</small></div><span class="adm-toggle locked" role="img" aria-label="Aktif, terkunci sistem" /></div>
      <div class="adm-set"><div><b>Wajib approval dokter</b><small>Hasil AI tidak bisa dikirim tanpa review</small></div><span class="adm-toggle locked" role="img" aria-label="Aktif, terkunci sistem" /></div>
      <p class="adm-hint">Dua pengaman di atas dikunci oleh sistem dan tidak bisa diubah dari sini. Retensi diatur pengelola server.</p>
      <router-link to="/admin/pengaturan" class="adm-link">Lihat pengaturan lengkap →</router-link>
    </template>
  </section>
</template>
