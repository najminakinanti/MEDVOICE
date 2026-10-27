<script setup>
import { onMounted, ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { Eye, EyeOff, Lock, Mail, Mic, FileText, ShieldCheck, Server } from "lucide-vue-next";
import { ApiError, errText, homePath, login } from "../api.js";
import Logo from "../components/Logo.vue";
import heroLogo from "../assets/logo-hero.png";   // versi untuk latar gelap (teks putih)

const router = useRouter(), route = useRoute();
const REM = "mv.login";
const user = ref(""), pass = ref(""), remember = ref(true), show = ref(false), busy = ref(false), err = ref(""), hint = ref(false);

onMounted(() => {
  try { const s = JSON.parse(localStorage.getItem(REM) || "{}"); user.value = s.user || ""; } catch { /* abaikan */ }
});

async function submit() {
  err.value = ""; busy.value = true;
  try {
    await login(user.value.trim(), pass.value);
    pass.value = "";
    try { remember.value ? localStorage.setItem(REM, JSON.stringify({ user: user.value.trim() })) : localStorage.removeItem(REM); } catch { /* mode privat */ }
    router.replace(typeof route.query.next === "string" && route.query.next.startsWith("/") ? route.query.next : homePath());
  } catch (e) {
    err.value = e instanceof ApiError && e.status === 401 ? "Email/NIP atau kata sandi salah." : e instanceof ApiError ? errText(e) : "Tidak dapat terhubung ke server.";
  } finally { busy.value = false; }
}
</script>

<template>
  <div class="login">
    <section class="hero">
      <div class="deco" aria-hidden="true">
        <i class="circ ring r1"></i><i class="circ ring r2"></i><i class="circ ring r3"></i>
        <i class="circ orb o1"></i><i class="circ orb o2"></i><i class="circ orb o3"></i>
        <i class="circ dot d1"></i><i class="circ dot d2"></i><i class="circ dot d3"></i>
      </div>
      <div class="top"><img class="hero-logo" :src="heroLogo" alt="MedVoice — AI Clinical Documentation" /></div>
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
.hero { position: relative; overflow: hidden; background: var(--grad-hero); color: #fff; padding: 56px; display: flex; flex-direction: column; justify-content: space-between; }
.hero > :not(.deco) { position: relative; z-index: 1; }

/* hiasan lingkaran: murni dekorasi, transparan agar teks tetap terbaca */
.deco { position: absolute; inset: 0; z-index: 0; pointer-events: none; }
.circ { position: absolute; display: block; border-radius: 50%; animation: drift 14s ease-in-out infinite; }
.ring { border: 3px solid rgba(255, 255, 255, .30); }
.r1 { width: 420px; height: 420px; top: -150px; right: -140px; }
.r2 { width: 260px; height: 260px; top: -70px; right: -60px; border-color: rgba(255, 255, 255, .20); animation-duration: 18s; }
.r3 { width: 300px; height: 300px; bottom: -110px; right: 30px; border-color: rgba(190, 168, 255, .55); animation-duration: 20s; animation-delay: -6s; }
.orb { background: radial-gradient(circle at 30% 28%, rgba(176, 150, 255, .85), rgba(91, 63, 200, 0) 72%); }
.o1 { width: 360px; height: 360px; bottom: -150px; left: -120px; animation-duration: 16s; }
.o2 { width: 150px; height: 150px; top: 46%; right: 36px; background: radial-gradient(circle at 30% 28%, rgba(255, 255, 255, .30), rgba(255, 255, 255, 0) 74%); animation-duration: 12s; animation-delay: -3s; }
.o3 { width: 90px; height: 90px; top: 30%; left: -26px; background: radial-gradient(circle at 30% 28%, rgba(190, 168, 255, .8), rgba(155, 127, 232, 0) 74%); animation-duration: 10s; animation-delay: -5s; }
.dot { background: rgba(255, 255, 255, .55); }
.d1 { width: 16px; height: 16px; bottom: 120px; right: 90px; animation-duration: 9s; }
.d2 { width: 12px; height: 12px; top: 22%; right: 64px; background: rgba(190, 168, 255, .95); animation-duration: 11s; animation-delay: -2s; }
.d3 { width: 14px; height: 14px; bottom: 150px; left: 40%; animation-duration: 13s; animation-delay: -7s; }
@keyframes drift { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-14px); } }
@media (prefers-reduced-motion: reduce) { .circ { animation: none; } }
.top { display: flex; align-items: center; }
.hero-logo { display: block; width: 240px; max-width: 100%; height: auto; }
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
