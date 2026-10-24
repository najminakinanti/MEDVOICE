<script setup>
import { onMounted, ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { Eye, EyeOff, Lock, Mail, Mic, FileText, ShieldCheck, Server, Building2 } from "lucide-vue-next";
import { ApiError, errText, login } from "../api.js";
import Logo from "../components/Logo.vue";

const router = useRouter(), route = useRoute();
const REM = "mv.login";
const client = ref(""), user = ref(""), pass = ref(""), remember = ref(true), show = ref(false), busy = ref(false), err = ref(""), hint = ref(false);

onMounted(() => {
  try { const s = JSON.parse(localStorage.getItem(REM) || "{}"); client.value = s.client || ""; user.value = s.user || ""; } catch { /* abaikan */ }
});

async function submit() {
  err.value = ""; busy.value = true;
  try {
    await login(client.value.trim(), user.value.trim(), pass.value);
    pass.value = "";
    try { remember.value ? localStorage.setItem(REM, JSON.stringify({ client: client.value.trim(), user: user.value.trim() })) : localStorage.removeItem(REM); } catch { /* mode privat */ }
    router.replace(typeof route.query.next === "string" && route.query.next.startsWith("/") ? route.query.next : "/queue");
  } catch (e) {
    err.value = e instanceof ApiError && e.status === 401 ? "Rumah sakit, akun, atau kata sandi salah." : e instanceof ApiError ? errText(e) : "Tidak dapat terhubung ke server.";
  } finally { busy.value = false; }
}
</script>

<template>
  <div class="login">
    <section class="hero">
      <div class="top"><span class="sq"><Logo mark-only :size="0.55" /></span> MedVoice · AI Clinical Documentation</div>
      <div class="copy">
        <h1>Dokter fokus ke pasien, dokumentasi ditulis otomatis.</h1>
        <p>Percakapan konsultasi berubah jadi catatan SOAP lengkap dengan kode ICD-10 &amp; ICD-9-CM, siap dikirim ke SIMRS.</p>
        <ul>
          <li><span><Mic :size="14" /></span>Transkripsi real-time bahasa Indonesia</li>
          <li><span><FileText :size="14" /></span>Draft SOAP otomatis, dokter tinggal review</li>
          <li><span><ShieldCheck :size="14" /></span>Data pasien tetap di jaringan rumah sakit</li>
        </ul>
      </div>
      <div class="foot">© 2026 MedVoice · AI Clinical Documentation</div>
    </section>

    <section class="formside">
      <form class="form" @submit.prevent="submit">
        <div class="lg"><Logo :size="1.25" /></div>
        <h2 class="h1 c">Masuk ke akun Anda</h2>
        <p class="muted c sub">Gunakan akun rumah sakit Anda</p>

        <div class="field">
          <label for="lc">Rumah sakit</label>
          <div class="in"><Building2 :size="16" /><input id="lc" v-model="client" class="input" required autocomplete="organization" placeholder="Kode rumah sakit" /></div>
        </div>
        <div class="field">
          <label for="lu">Email atau NIP</label>
          <div class="in"><Mail :size="16" /><input id="lu" v-model="user" class="input" required autocomplete="username" placeholder="anisa.putri@rsmedika.co.id" /></div>
        </div>
        <div class="field">
          <div class="lrow"><label for="lp">Kata sandi</label><a href="#" class="forgot" @click.prevent="hint = !hint">Lupa kata sandi?</a></div>
          <div class="in">
            <Lock :size="16" />
            <input id="lp" v-model="pass" class="input" :type="show ? 'text' : 'password'" required autocomplete="current-password" />
            <button type="button" class="eye" :aria-label="show ? 'Sembunyikan' : 'Tampilkan'" @click="show = !show"><component :is="show ? EyeOff : Eye" :size="18" /></button>
          </div>
          <p v-if="hint" class="caption">Hubungi admin rumah sakit untuk mengatur ulang kata sandi.</p>
        </div>
        <label class="check"><input v-model="remember" type="checkbox" /><span class="muted">Ingat perangkat ini</span></label>
        <p v-if="err" class="banner bad" role="alert">{{ err }}</p>
        <button class="btn btn-primary btn-lg btn-block" :disabled="busy">{{ busy ? "Memeriksa…" : "Masuk" }}</button>
        <div class="or"><span>atau</span></div>
        <button type="button" class="btn btn-lg btn-block" disabled title="Belum tersedia pada integrasi ini"><Server :size="18" />Masuk dengan SSO SIMRS</button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.login { display: grid; grid-template-columns: 640px 1fr; min-height: 100%; background: var(--surface); }
.hero { background: var(--grad-hero); color: #fff; padding: 56px; display: flex; flex-direction: column; justify-content: space-between; }
.top { display: flex; align-items: center; gap: 12px; font-weight: 600; }
.sq { display: inline-grid; place-items: center; width: 52px; height: 44px; border-radius: 10px; background: #fff; }
.copy h1 { font-size: 40px; line-height: 1.15; font-weight: 700; letter-spacing: -.01em; max-width: 480px; }
.copy p { margin-top: 20px; font-size: 16px; line-height: 1.65; max-width: 520px; color: rgba(255,255,255,.92); }
.copy ul { list-style: none; padding: 0; margin: 28px 0 0; display: grid; gap: 14px; }
.copy li { display: flex; align-items: center; gap: 12px; }
.copy li span { display: inline-grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: rgba(255,255,255,.18); }
.foot { font-size: 12px; color: rgba(255,255,255,.75); }
.formside { display: grid; place-items: center; padding: 32px; }
.form { width: 100%; max-width: 400px; display: grid; gap: 18px; }
.lg { display: grid; place-items: center; margin-bottom: 10px; }
.c { text-align: center; } .sub { margin-top: -14px; }
.h1 { font-size: 24px; }
.in { position: relative; display: flex; align-items: center; }
.in > svg:first-child { position: absolute; left: 12px; color: var(--muted); pointer-events: none; }
.in .input { padding-left: 38px; }
.eye { position: absolute; right: 6px; width: 36px; height: 36px; display: grid; place-items: center; border: 0; background: none; color: var(--muted); }
.lrow { display: flex; justify-content: space-between; align-items: baseline; } .forgot { font-size: 13px; font-weight: 600; color: var(--purple-600); }
.or { display: flex; align-items: center; gap: 12px; color: var(--subtle); font-size: 12px; } .or::before, .or::after { content: ""; flex: 1; height: 1px; background: var(--border); }
@media (max-width: 960px) { .login { grid-template-columns: 1fr; } .hero { display: none; } }
</style>
