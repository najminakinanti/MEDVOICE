<script setup>
// Daftar & pengelolaan pengguna. `base` menentukan siapa yang dikelola:
//   /admin/users                          admin RS -> pengguna RS-nya; superadmin -> akun platform
//   /platform/hospitals/{id}/users        superadmin -> pengguna RS mana pun
// Pilihan peran datang dari server (data.roles), jadi UI tak pernah menawarkan peran yang akan ditolak.
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { KeyRound, MoreHorizontal, Pencil, Plus, Power, Search } from "lucide-vue-next";
import { ROLE_LABEL, api, errText } from "../../api.js";
import { dateShort, initials } from "../../format.js";
import Modal from "../../components/Modal.vue";
import SecretModal from "../../components/SecretModal.vue";

const props = defineProps({ base: { type: String, default: "/admin/users" }, heading: { type: String, default: "Pengguna" } });
const emit = defineEmits(["loaded"]);

const data = ref(null), q = ref(""), err = ref(""), notice = ref(""), loading = ref(false), menu = ref(null);
const form = ref(null), busy = ref(false), formErr = ref("");
const secret = ref(null), confirm = ref(null);
const roles = computed(() => data.value?.roles || ["dokter", "admin"]);
const EMPTY = { id: null, display_name: "", email: "", nip: "", simrs_user_id: "", role: "", title: "", password: "" };

async function load() {
  loading.value = true; err.value = "";
  try { data.value = await api(props.base + (q.value.trim() ? "?q=" + encodeURIComponent(q.value.trim()) : "")); emit("loaded", data.value); }
  catch (e) { err.value = errText(e); } finally { loading.value = false; }
}
let timer;
watch(q, () => { clearTimeout(timer); timer = setTimeout(load, 250); });
watch(() => props.base, () => { data.value = null; load(); });
const closeMenu = () => { menu.value = null; };
onMounted(() => { load(); document.addEventListener("click", closeMenu); window.addEventListener("scroll", closeMenu, true); window.addEventListener("resize", closeMenu); });
onUnmounted(() => { document.removeEventListener("click", closeMenu); window.removeEventListener("scroll", closeMenu, true); window.removeEventListener("resize", closeMenu); });

// Menu aksi digambar di luar tabel (position: fixed) agar tidak terpotong wadah tabel yang bisa digulir.
function openMenu(u, e) {
  if (menu.value?.u.id === u.id) { menu.value = null; return; }
  const r = e.currentTarget.getBoundingClientRect(), w = 230, h = u.is_self ? 60 : 170;
  menu.value = { u, left: Math.max(8, Math.min(r.right - w, window.innerWidth - w - 8)),
    top: r.bottom + h > window.innerHeight - 8 ? Math.max(8, r.top - h - 4) : r.bottom + 4 };
}

const items = computed(() => data.value?.items || []);
const label = (r) => data.value?.role_labels?.[r] || ROLE_LABEL[r] || r;

function openNew() { formErr.value = ""; form.value = { ...EMPTY, role: roles.value[0], _orig: null }; }
function openEdit(u) {
  formErr.value = ""; menu.value = null;
  form.value = { id: u.id, display_name: u.display_name, email: u.email || "", nip: u.nip || "", simrs_user_id: u.simrs_user_id || "", role: u.role, title: u.title || "", password: "", _orig: u, self: u.is_self };
}

async function save() {
  const f = form.value; formErr.value = ""; busy.value = true;
  try {
    if (!f.id) {
      const r = await api(props.base, { method: "POST", json: {
        display_name: f.display_name, email: f.email.trim() || null, nip: f.nip.trim() || null,
        simrs_user_id: f.simrs_user_id.trim() || null, role: f.role, title: f.title.trim() || null, password: f.password || null } });
      form.value = null;
      if (r.temporary_password) secret.value = { title: "Akun dibuat", who: f.display_name, login: f.email.trim() || f.nip.trim(), pw: r.temporary_password };
      else notice.value = `Akun ${f.display_name} dibuat.`;
    } else {
      const o = f._orig, patch = {};          // kirim hanya yang berubah (akun lama tanpa email/NIP tetap bisa diubah hal lain)
      if (f.display_name !== o.display_name) patch.display_name = f.display_name;
      if ((f.email.trim() || null) !== (o.email || null)) patch.email = f.email.trim() || null;
      if ((f.nip.trim() || null) !== (o.nip || null)) patch.nip = f.nip.trim() || null;
      if (f.simrs_user_id.trim() && f.simrs_user_id.trim() !== o.simrs_user_id) patch.simrs_user_id = f.simrs_user_id.trim();
      if (f.role !== o.role) patch.role = f.role;
      if ((f.title.trim() || null) !== (o.title || null)) patch.title = f.title.trim() || null;
      if (Object.keys(patch).length) await api(`${props.base}/${f.id}`, { method: "PUT", json: patch });
      form.value = null; notice.value = "Perubahan disimpan.";
    }
    await load();
  } catch (e) { formErr.value = errText(e); } finally { busy.value = false; }
}

function ask(u, kind) { menu.value = null; confirm.value = { u, kind }; err.value = ""; }
async function doConfirm() {
  const { u, kind } = confirm.value; busy.value = true;
  try {
    if (kind === "reset") {
      const r = await api(`${props.base}/${u.id}/reset-password`, { method: "POST", json: {} });
      confirm.value = null; secret.value = { title: "Kata sandi diatur ulang", who: u.display_name, login: u.email || u.nip || u.username, pw: r.temporary_password };
    } else {
      await api(`${props.base}/${u.id}`, { method: "PUT", json: { active: kind === "enable" } });
      confirm.value = null; notice.value = kind === "enable" ? `${u.display_name} diaktifkan kembali.` : `${u.display_name} dinonaktifkan; tidak bisa login lagi.`;
    }
    await load();
  } catch (e) { confirm.value = null; err.value = errText(e); } finally { busy.value = false; }
}
</script>

<template>
  <div class="adm-wrap adm-wide">
    <p v-if="err" class="banner bad" role="alert">{{ err }}</p>
    <p v-if="notice" class="adm-ok" role="status">{{ notice }}</p>

    <section class="card adm-box">
      <header class="adm-cardhead">
        <h2>{{ heading }}</h2><span class="adm-count">{{ data?.total ?? 0 }}</span>
        <label v-if="(data?.total ?? 0) > 8 || q" class="adm-grow" style="max-width: 260px; position: relative; margin-left: 8px">
          <Search :size="14" style="position: absolute; left: 10px; top: 9px; color: var(--subtle)" />
          <input v-model="q" class="input" style="height: 32px; padding-left: 30px; font-size: 13px" placeholder="Cari pengguna" aria-label="Cari pengguna" />
        </label>
        <button class="btn btn-primary adm-btn-sm adm-spacer" @click="openNew"><Plus :size="15" />Tambah pengguna</button>
      </header>
      <div class="adm-scroll">
        <table class="adm-table adm-fig">
          <thead><tr><th>NAMA</th><th style="width: 120px">PERAN</th><th style="width: 150px">JABATAN</th><th style="width: 130px">STATUS</th><th style="width: 56px" /></tr></thead>
          <tbody>
            <tr v-for="u in items" :key="u.id" :class="{ 'adm-off': !u.active }">
              <td><div class="adm-who"><span class="avatar" style="width: 30px; height: 30px">{{ initials(u.display_name) }}</span>
                <div><div class="adm-name">{{ u.display_name }}<span v-if="u.is_self" class="adm-sub"> (Anda)</span></div>
                  <div class="adm-sub">{{ u.email || u.nip || "@" + u.username }}</div></div></div></td>
              <td class="adm-cell">{{ label(u.role) }}</td>
              <td class="adm-cell">{{ u.title || "—" }}</td>
              <td><span class="adm-badge" :class="u.active ? 'ok' : ''">{{ u.active ? "Aktif" : "Nonaktif" }}</span></td>
              <td class="adm-act" @click.stop>
                <button class="adm-ib" :aria-label="'Aksi untuk ' + u.display_name" aria-haspopup="menu" :aria-expanded="menu?.u.id === u.id" @click.stop="openMenu(u, $event)"><MoreHorizontal :size="18" /></button>
              </td>
            </tr>
            <tr v-if="data && !items.length"><td colspan="5" class="adm-empty">{{ loading ? "Memuat…" : "Tidak ada pengguna yang cocok." }}</td></tr>
          </tbody>
        </table>
      </div>
    </section>

    <Teleport to="body">
      <div v-if="menu" class="adm-menu card" role="menu" :style="{ top: menu.top + 'px', left: menu.left + 'px' }" @click.stop>
        <button role="menuitem" @click="openEdit(menu.u)"><Pencil :size="14" />Ubah data</button>
        <template v-if="!menu.u.is_self">
          <button role="menuitem" @click="ask(menu.u, 'reset')"><KeyRound :size="14" />Atur ulang kata sandi</button>
          <button v-if="menu.u.active" role="menuitem" class="adm-danger" @click="ask(menu.u, 'disable')"><Power :size="14" />Nonaktifkan akun</button>
          <button v-else role="menuitem" @click="ask(menu.u, 'enable')"><Power :size="14" />Aktifkan kembali</button>
        </template>
      </div>
    </Teleport>
    <p class="adm-hint">Pengguna masuk dengan email atau NIP. Akun yang dinonaktifkan tidak bisa login, tetapi riwayat sesinya tetap tersimpan.</p>

    <!-- Tambah / ubah -->
    <Modal v-if="form" :width="600" :label="form.id ? 'Ubah pengguna' : 'Tambah pengguna'" @close="form = null">
      <form @submit.prevent="save">
        <h2 class="adm-modal-h">{{ form.id ? "Ubah pengguna" : "Tambah pengguna" }}</h2>
        <p class="adm-hint" style="margin-bottom: 14px">Isi minimal salah satu: email atau NIP. Itu dipakai untuk login.</p>
        <div class="adm-form">
          <div class="field adm-full"><label for="u-n">Nama lengkap</label><input id="u-n" v-model="form.display_name" class="input" required maxlength="200" placeholder="dr. Anisa Putri, Sp.PD" /></div>
          <div class="field"><label for="u-e">Email</label><input id="u-e" v-model="form.email" class="input" type="email" autocomplete="off" placeholder="anisa.putri@rs.co.id" /></div>
          <div class="field"><label for="u-i">NIP</label><input id="u-i" v-model="form.nip" class="input" autocomplete="off" placeholder="198503122010012003" /></div>
          <div class="field"><label for="u-s">ID dokter di SIMRS</label><input id="u-s" v-model="form.simrs_user_id" class="input" autocomplete="off" placeholder="Kosong = otomatis" /></div>
          <div class="field"><label for="u-r">Peran</label>
            <select id="u-r" v-model="form.role" class="input" :disabled="form.self || roles.length === 1"><option v-for="r in roles" :key="r" :value="r">{{ label(r) }}</option></select>
            <span v-if="form.self" class="adm-hint">Peran akun sendiri tidak bisa diubah.</span>
            <span v-else-if="roles.length === 1" class="adm-hint">Daftar ini hanya berisi {{ label(roles[0]) }}.</span></div>
          <div class="field adm-full"><label for="u-t">Jabatan (opsional)</label><input id="u-t" v-model="form.title" class="input" maxlength="80" placeholder="Dokter Umum, Sp.PD, Perawat…" />
            <span class="adm-hint">Teks bebas yang tampil di tabel dan di bawah nama pengguna. Tidak memengaruhi hak akses.</span></div>
          <div v-if="!form.id" class="field adm-full"><label for="u-p">Kata sandi awal (opsional)</label>
            <input id="u-p" v-model="form.password" class="input" type="text" autocomplete="off" placeholder="Kosong = dibuatkan otomatis dan ditampilkan sekali" />
            <span class="adm-hint">Minimal 10 karakter bila diisi sendiri.</span></div>
        </div>
        <p v-if="formErr" class="banner bad" role="alert" style="margin-top: 14px">{{ formErr }}</p>
        <div class="adm-modal-actions">
          <button type="button" class="btn" @click="form = null">Batal</button>
          <button class="btn btn-primary" :disabled="busy">{{ busy ? "Menyimpan…" : form.id ? "Simpan perubahan" : "Buat akun" }}</button>
        </div>
      </form>
    </Modal>

    <!-- Konfirmasi -->
    <Modal v-if="confirm" :width="460" label="Konfirmasi" @close="confirm = null">
      <h2 class="adm-modal-h">{{ { reset: "Atur ulang kata sandi?", disable: "Nonaktifkan akun?", enable: "Aktifkan kembali akun?" }[confirm.kind] }}</h2>
      <p class="muted">
        <template v-if="confirm.kind === 'reset'">Kata sandi <b>{{ confirm.u.display_name }}</b> diganti dengan kata sandi sementara yang ditampilkan sekali. Kata sandi lama tidak berlaku lagi.</template>
        <template v-else-if="confirm.kind === 'disable'"><b>{{ confirm.u.display_name }}</b> tidak akan bisa login. Sesi yang sudah ada dan riwayatnya tetap tersimpan.</template>
        <template v-else><b>{{ confirm.u.display_name }}</b> bisa login lagi dengan kata sandi yang sama seperti sebelumnya.</template>
      </p>
      <div class="adm-modal-actions">
        <button class="btn" @click="confirm = null">Batal</button>
        <button class="btn" :class="confirm.kind === 'disable' ? 'btn-danger' : 'btn-primary'" :disabled="busy" @click="doConfirm">{{ busy ? "Memproses…" : "Ya, lanjutkan" }}</button>
      </div>
    </Modal>

    <SecretModal v-if="secret" v-bind="secret" @close="secret = null" />
  </div>
</template>
