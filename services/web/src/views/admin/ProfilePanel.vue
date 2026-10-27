<script setup>
import { computed, onMounted, ref } from "vue";
import { Eye, EyeOff, Lock } from "lucide-vue-next";
import { api, auth, errText } from "../../api.js";
import { dateShort, initials } from "../../format.js";

const me = computed(() => auth.me || {});
const cur = ref(""), next = ref(""), again = ref(""), show = ref(false), busy = ref(false), err = ref(""), ok = ref(false);

onMounted(async () => { try { auth.me = await api("/me"); } catch { /* data lama tetap tampil */ } });

const tooShort = computed(() => next.value.length > 0 && next.value.length < 10);
const mismatch = computed(() => again.value.length > 0 && next.value !== again.value);
const canSave = computed(() => cur.value && next.value.length >= 10 && next.value === again.value && !busy.value);

async function save() {
  err.value = ""; ok.value = false; busy.value = true;
  try {
    await api("/me/password", { method: "POST", json: { current_password: cur.value, new_password: next.value } });
    cur.value = next.value = again.value = ""; ok.value = true;
  } catch (e) { err.value = errText(e); } finally { busy.value = false; }
}
</script>

<template>
  <div class="adm-wrap">
    <section class="card adm-card">
      <div class="adm-head"><div><h2 class="h2">Data akun</h2><p>Data ini diatur oleh admin rumah sakit. Hubungi admin bila ada yang perlu diubah.</p></div></div>
      <div class="adm-who">
        <span class="avatar lg" style="background: var(--purple-600); color: #fff">{{ initials(me.display_name) }}</span>
        <div><div class="adm-name">{{ me.display_name }}</div><div class="adm-sub">{{ me.title || me.role_label }}<template v-if="me.role !== 'superadmin'"> · {{ me.client }}</template></div></div>
      </div>
      <dl class="adm-kv">
        <dt>Peran</dt><dd>{{ me.role_label || "—" }}</dd>
        <dt>Jabatan</dt><dd>{{ me.title || "—" }}</dd>
        <dt>Email</dt><dd>{{ me.email || "—" }}</dd>
        <dt>NIP</dt><dd>{{ me.nip || "—" }}</dd>
        <dt>Nama pengguna</dt><dd>{{ me.username }}</dd>
        <dt>ID dokter di SIMRS</dt><dd>{{ me.simrs_user_id || "—" }}</dd>
        <dt>Login terakhir</dt><dd>{{ me.last_login_at ? dateShort(me.last_login_at) : "—" }}</dd>
      </dl>
    </section>

    <form class="card adm-card" @submit.prevent="save">
      <div class="adm-head"><div><h2 class="h2">Ganti kata sandi</h2><p>Minimal 10 karakter. Anda tetap masuk di perangkat ini setelah mengganti.</p></div></div>
      <div class="adm-form">
        <div class="field adm-full"><label for="pw0">Kata sandi saat ini</label>
          <input id="pw0" v-model="cur" class="input" :type="show ? 'text' : 'password'" autocomplete="current-password" required /></div>
        <div class="field"><label for="pw1">Kata sandi baru</label>
          <input id="pw1" v-model="next" class="input" :type="show ? 'text' : 'password'" autocomplete="new-password" required />
          <span v-if="tooShort" class="adm-hint" style="color: var(--danger)">Minimal 10 karakter.</span></div>
        <div class="field"><label for="pw2">Ulangi kata sandi baru</label>
          <input id="pw2" v-model="again" class="input" :type="show ? 'text' : 'password'" autocomplete="new-password" required />
          <span v-if="mismatch" class="adm-hint" style="color: var(--danger)">Tidak sama dengan kata sandi baru.</span></div>
      </div>
      <p v-if="err" class="banner bad" role="alert">{{ err }}</p>
      <p v-if="ok" class="adm-ok" role="status">Kata sandi berhasil diganti.</p>
      <div class="adm-row">
        <button type="button" class="btn btn-sm" @click="show = !show"><component :is="show ? EyeOff : Eye" :size="16" />{{ show ? "Sembunyikan" : "Tampilkan" }}</button>
        <button class="btn btn-primary adm-spacer" :disabled="!canSave"><Lock :size="16" />{{ busy ? "Menyimpan…" : "Simpan kata sandi" }}</button>
      </div>
    </form>
  </div>
</template>
