<script setup>
// Halaman Pengguna untuk superadmin: data rumah sakit (kolom kanan) dan pengguna per rumah sakit (kolom kiri).
// Memilih rumah sakit di kanan menampilkan penggunanya di kiri. Entri "Akun platform" = akun superadmin sendiri.
import { computed, onMounted, ref } from "vue";
import { Building2, Plus, Power, SlidersHorizontal } from "lucide-vue-next";
import { api, errText } from "../../api.js";
import { dateShort } from "../../format.js";
import Modal from "../../components/Modal.vue";
import SecretModal from "../../components/SecretModal.vue";
import AdminUsers from "./AdminUsers.vue";

const PLATFORM = "platform";
const hospitals = ref(null), sel = ref(PLATFORM), err = ref(""), notice = ref(""), busy = ref(false);
const form = ref(null), formErr = ref(""), limits = ref(null), confirm = ref(null), secret = ref(null);
let firstLoad = true;

async function load() {
  try {
    hospitals.value = (await api("/platform/hospitals")).items;
    if (firstLoad) { firstLoad = false; if (hospitals.value.length) sel.value = hospitals.value[0].id; }
    else if (sel.value !== PLATFORM && !hospitals.value.some((h) => h.id === sel.value)) sel.value = PLATFORM;
  } catch (e) { err.value = errText(e); }
}
onMounted(load);

const current = computed(() => hospitals.value?.find((h) => h.id === sel.value) || null);
const base = computed(() => (sel.value === PLATFORM ? "/admin/users" : `/platform/hospitals/${sel.value}/users`));
const heading = computed(() => (sel.value === PLATFORM ? "Akun platform" : `Pengguna · ${current.value?.name || ""}`));
const quotaText = (h) => (h.monthly_quota ? `${h.sessions_this_month} dari ${h.monthly_quota}` : `${h.sessions_this_month} (tanpa kuota)`);

function openNew() { formErr.value = ""; form.value = { name: "", rate: 60, quota: "", display_name: "", email: "", nip: "", password: "" }; }
async function create() {
  const f = form.value; formErr.value = ""; busy.value = true;
  try {
    const r = await api("/platform/hospitals", { method: "POST", json: {
      name: f.name.trim(), rate_limit_per_min: Number(f.rate) || 60, monthly_quota: f.quota === "" ? null : Number(f.quota),
      admin: { display_name: f.display_name, email: f.email.trim() || null, nip: f.nip.trim() || null, password: f.password || null } } });
    form.value = null; notice.value = `Rumah sakit ${r.name} dibuat.`;
    if (r.admin.temporary_password) secret.value = { title: "Rumah sakit dibuat", who: f.display_name + " (admin " + r.name + ")", login: f.email.trim() || f.nip.trim(), pw: r.admin.temporary_password };
    await load(); sel.value = r.id;
  } catch (e) { formErr.value = errText(e); } finally { busy.value = false; }
}

function openLimits() { formErr.value = ""; const h = current.value; limits.value = { h, rate: h.rate_limit_per_min, quota: h.monthly_quota ?? "" }; }
async function saveLimits() {
  const l = limits.value; formErr.value = ""; busy.value = true;
  try {
    await api("/platform/hospitals/" + l.h.id, { method: "PUT", json: { rate_limit_per_min: Number(l.rate), monthly_quota: l.quota === "" ? null : Number(l.quota) } });
    limits.value = null; notice.value = `Batas ${l.h.name} disimpan.`; await load();
  } catch (e) { formErr.value = errText(e); } finally { busy.value = false; }
}
async function toggle() {
  const h = confirm.value; busy.value = true; err.value = "";
  try {
    await api("/platform/hospitals/" + h.id, { method: "PUT", json: { active: !h.active } });
    notice.value = h.active ? `${h.name} dinonaktifkan; semua penggunanya tidak bisa login.` : `${h.name} diaktifkan kembali.`;
    confirm.value = null; await load();
  } catch (e) { confirm.value = null; err.value = errText(e); } finally { busy.value = false; }
}
</script>

<template>
  <div class="adm-split">
    <div class="adm-main">
      <p v-if="err" class="banner bad" role="alert" style="margin-bottom: 12px">{{ err }}</p>
      <p v-if="notice" class="adm-ok" role="status" style="margin-bottom: 12px">{{ notice }}</p>
      <AdminUsers :base="base" :heading="heading" @loaded="load" />
    </div>

    <aside class="adm-side">
      <section class="card adm-box" aria-label="Rumah sakit">
        <div class="adm-sidehead"><Building2 :size="18" class="adm-ico" /><h2>Rumah Sakit</h2><span class="adm-count">{{ hospitals?.length ?? 0 }}</span>
          <button class="btn btn-primary adm-btn-sm adm-spacer" @click="openNew"><Plus :size="15" />Tambah</button></div>
        <div class="adm-hlist" role="listbox" aria-label="Pilih rumah sakit">
          <button v-for="h in hospitals || []" :key="h.id" class="adm-hrow" :class="{ on: sel === h.id }" role="option" :aria-selected="sel === h.id" @click="sel = h.id">
            <span class="avatar"><Building2 :size="15" /></span>
            <span class="adm-hname"><b>{{ h.name }}</b><small>{{ h.active_users }} pengguna · {{ h.active_admins }} admin</small></span>
            <span class="adm-badge" :class="h.active ? 'ok' : ''">{{ h.active ? "Aktif" : "Nonaktif" }}</span>
          </button>
          <button class="adm-hrow" :class="{ on: sel === PLATFORM }" role="option" :aria-selected="sel === PLATFORM" @click="sel = PLATFORM">
            <span class="avatar" style="background: var(--navy-900); color: #fff"><Building2 :size="15" /></span>
            <span class="adm-hname"><b>Akun platform</b><small>superadmin · pengelola platform</small></span>
          </button>
        </div>
      </section>

      <section v-if="current" class="card adm-box" aria-label="Data rumah sakit">
        <div class="adm-sidehead"><h2>Data rumah sakit</h2><span class="adm-badge" :class="current.active ? 'ok' : ''">{{ current.active ? "Aktif" : "Nonaktif" }}</span></div>
        <dl class="adm-kv" style="grid-template-columns: minmax(120px, 150px) 1fr">
          <dt>Kode</dt><dd class="adm-mono">{{ current.name }}</dd>
          <dt>Adapter SIMRS</dt><dd>{{ current.adapter }}</dd>
          <dt>Pengguna aktif</dt><dd>{{ current.active_users }} <span class="adm-sub">({{ current.active_admins }} admin)</span>
            <span v-if="!current.active_admins" class="adm-badge warn" style="margin-left: 6px">Tanpa admin aktif</span></dd>
          <dt>Sesi bulan ini</dt><dd>{{ quotaText(current) }}</dd>
          <dt>Batas permintaan</dt><dd>{{ current.rate_limit_per_min }} per menit</dd>
          <dt>Dibuat</dt><dd>{{ dateShort(current.created_at) }}</dd>
        </dl>
        <div class="adm-row">
          <button class="btn adm-btn-sm" @click="openLimits"><SlidersHorizontal :size="14" />Atur batas</button>
          <button class="btn adm-btn-sm" :class="{ 'btn-danger': current.active }" @click="confirm = current"><Power :size="14" />{{ current.active ? "Nonaktifkan" : "Aktifkan kembali" }}</button>
        </div>
      </section>
      <section v-else class="card adm-box" aria-label="Akun platform">
        <div class="adm-sidehead"><h2>Akun platform</h2></div>
        <p class="adm-hint">Akun superadmin: pengelola platform yang membuat dan mengatur rumah sakit. Daftar akunnya ada di kiri; peran di sini hanya <b>Superadmin</b>.</p>
      </section>
    </aside>

    <Modal v-if="form" :width="620" label="Tambah rumah sakit" @close="form = null">
      <form @submit.prevent="create">
        <h2 class="adm-modal-h">Tambah rumah sakit</h2>
        <p class="adm-hint" style="margin-bottom: 14px">Setiap rumah sakit dibuat bersama satu akun admin, yang kemudian mengelola dokter-dokternya sendiri.</p>
        <div class="adm-form">
          <div class="field adm-full"><label for="h-n">Nama rumah sakit (kode)</label><input id="h-n" v-model="form.name" class="input" required placeholder="rs-harapan-bandung" autocomplete="off" />
            <span class="adm-hint">Huruf kecil, angka, dan tanda strip; 3-60 karakter. Tidak bisa diubah setelah dibuat.</span></div>
          <div class="field"><label for="h-r">Batas permintaan per menit</label><input id="h-r" v-model="form.rate" class="input" type="number" min="1" max="10000" required /></div>
          <div class="field"><label for="h-q">Kuota sesi per bulan</label><input id="h-q" v-model="form.quota" class="input" type="number" min="1" placeholder="Kosong = tanpa kuota" /></div>
          <div class="adm-full" style="font-weight: 700; margin-top: 4px">Admin pertama</div>
          <div class="field adm-full"><label for="h-an">Nama lengkap</label><input id="h-an" v-model="form.display_name" class="input" required maxlength="200" placeholder="dr. Anisa Putri" /></div>
          <div class="field"><label for="h-ae">Email</label><input id="h-ae" v-model="form.email" class="input" type="email" autocomplete="off" placeholder="admin@rs.co.id" /></div>
          <div class="field"><label for="h-ai">NIP</label><input id="h-ai" v-model="form.nip" class="input" autocomplete="off" /></div>
          <div class="field adm-full"><label for="h-ap">Kata sandi awal (opsional)</label><input id="h-ap" v-model="form.password" class="input" type="text" autocomplete="off" placeholder="Kosong = dibuatkan otomatis dan ditampilkan sekali" /></div>
        </div>
        <p v-if="formErr" class="banner bad" role="alert" style="margin-top: 14px">{{ formErr }}</p>
        <div class="adm-modal-actions"><button type="button" class="btn" @click="form = null">Batal</button><button class="btn btn-primary" :disabled="busy">{{ busy ? "Membuat…" : "Buat rumah sakit" }}</button></div>
      </form>
    </Modal>

    <Modal v-if="limits" :width="480" label="Atur batas pemakaian" @close="limits = null">
      <form @submit.prevent="saveLimits">
        <h2 class="adm-modal-h">Batas pemakaian — {{ limits.h.name }}</h2>
        <div class="adm-form" style="margin-top: 12px">
          <div class="field"><label for="l-r">Permintaan per menit</label><input id="l-r" v-model="limits.rate" class="input" type="number" min="1" max="10000" required /></div>
          <div class="field"><label for="l-q">Kuota sesi per bulan</label><input id="l-q" v-model="limits.quota" class="input" type="number" min="1" placeholder="Kosong = tanpa kuota" /></div>
        </div>
        <p class="adm-hint" style="margin-top: 10px">Sesi bulan ini: {{ limits.h.sessions_this_month }}.</p>
        <p v-if="formErr" class="banner bad" role="alert" style="margin-top: 12px">{{ formErr }}</p>
        <div class="adm-modal-actions"><button type="button" class="btn" @click="limits = null">Batal</button><button class="btn btn-primary" :disabled="busy">Simpan</button></div>
      </form>
    </Modal>

    <Modal v-if="confirm" :width="460" label="Konfirmasi" @close="confirm = null">
      <h2 class="adm-modal-h">{{ confirm.active ? "Nonaktifkan" : "Aktifkan kembali" }} {{ confirm.name }}?</h2>
      <p class="muted"><template v-if="confirm.active">Semua pengguna ({{ confirm.active_users }}) langsung tidak bisa login dan kunci API rumah sakit ini ditolak. Data dan riwayat tetap tersimpan, dan bisa diaktifkan kembali kapan saja.</template>
        <template v-else>Pengguna dan kunci API rumah sakit ini bisa dipakai lagi.</template></p>
      <div class="adm-modal-actions"><button class="btn" @click="confirm = null">Batal</button>
        <button class="btn" :class="confirm.active ? 'btn-danger' : 'btn-primary'" :disabled="busy" @click="toggle">{{ busy ? "Memproses…" : "Ya, lanjutkan" }}</button></div>
    </Modal>

    <SecretModal v-if="secret" v-bind="secret" @close="secret = null" />
  </div>
</template>
