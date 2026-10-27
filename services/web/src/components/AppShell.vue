<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Bell, ChevronRight, History, LayoutGrid, LogOut, Menu, Mic, Search,SlidersHorizontal, Stethoscope, UserRound, Users, Link2 } from "lucide-vue-next";
import { ROLE_LABEL, auth, canAdmin, isSuperadmin, logout } from "../api.js";
import { app } from "../store.js";
import { initials } from "../format.js";
import Logo from "./Logo.vue";

const props = defineProps({
  title: String, crumb: String, unit: { type: String, default: "Poli Umum" },
  search: { type: Boolean, default: true }, query: { type: String, default: "" }, bare: Boolean,
});
const emit = defineEmits(["update:query"]);
const route = useRoute(), router = useRouter();
const q = ref(props.query);
const bell = ref(false);
watch(() => props.query, (v) => { q.value = v; });
watch(() => route.fullPath, () => { app.navOpen = false; });

const showUnit = computed(() => /^\/(queue|history|session)/.test(route.path));   // poli belum dikelola di sistem
const nav = computed(() => [
  { to: "/queue", icon: LayoutGrid, label: "Antrean Pasien", on: route.path === "/queue" },
  { to: app.activeSessionId ? `/session/${app.activeSessionId}` : "/queue", icon: Mic, label: "Sesi Aktif", on: route.path.startsWith("/session") },
  { to: "/history", icon: History, label: "Riwayat Sesi", on: route.path === "/history" },
  { to: "/profil", icon: UserRound, label: "Profil Saya", on: route.path === "/profil" },
]);
const admin = computed(() => [
  { to: "/admin/pengguna", icon: Users, label: "Pengguna & Profil" },
  { to: "/admin/integrasi", icon: Link2, label: "Integrasi SIMRS" },
  { to: "/admin/pengaturan", icon: SlidersHorizontal, label: "Pengaturan" },
].map((i) => ({ ...i, on: route.path === i.to })));

function submit() {
  if (route.path === "/queue") return;                       // antrean menyaring langsung
  router.push({ path: "/history", query: q.value ? { q: q.value } : {} });
}
function out() { logout(); router.replace("/login"); }
</script>

<template>
  <div v-if="bare" class="bare"><slot /></div>
  <div v-else class="shell">
    <div v-if="app.navOpen" class="scrim" @click="app.navOpen = false" />
    <aside class="side no-print" :class="{ open: app.navOpen }">
      <div class="brand"><Logo /></div>
      <div v-if="showUnit" class="unit">
        <Stethoscope :size="18" class="unit-ic" />
        <div><div class="cap">Unit aktif</div><div class="unit-name">{{ unit }}</div></div>
      </div>
      <nav>
        <router-link v-for="n in nav" :key="n.label" :to="n.to" class="nav" :class="{ on: n.on }"><component :is="n.icon" :size="20" />{{ n.label }}</router-link>
        <div v-if="canAdmin()" class="sect">ADMIN RS</div>
        <router-link v-for="n in canAdmin() ? admin : []" :key="n.label" :to="n.to" class="nav" :class="{ on: n.on }"><component :is="n.icon" :size="20" />{{ n.label }}</router-link>
      </nav>
      <div class="me">
        <span class="avatar lg me-av">{{ initials(auth.me?.display_name) }}</span>
        <div class="me-t"><div class="me-n">{{ auth.me?.display_name }}</div><div class="cap">{{ auth.me?.title || auth.me?.role_label || ROLE_LABEL[auth.me?.role] || "Dokter" }}</div></div>
        <button class="ic" title="Keluar" aria-label="Keluar" @click="out"><LogOut :size="18" /></button>
      </div>
    </aside>

    <div class="main">
      <header class="top no-print">
        <button class="ic burger" aria-label="Menu" @click="app.navOpen = !app.navOpen"><Menu :size="20" /></button>
        <div class="ttl">
          <div class="crumb">{{ crumb }}</div>
          <h1 class="h1">{{ title }}</h1>
        </div>
        <div class="mid"><slot name="center" /></div>
        <form v-if="search" class="search" @submit.prevent="submit">
          <Search :size="16" />
          <input v-model="q" placeholder="Cari pasien, no. RM…" aria-label="Cari pasien" @input="emit('update:query', q)" />
        </form>
        <div class="bellwrap">
          <button class="ic bell" aria-label="Notifikasi" @click="bell = !bell"><Bell :size="18" /></button>
          <div v-if="bell" class="pop card" @click="bell = false">Tidak ada notifikasi.</div>
        </div>
      </header>
      <main class="content"><slot /></main>
    </div>
  </div>
</template>

<style scoped>
.shell { display: grid; grid-template-columns: var(--sidebar-w) 1fr; height: 100%; }
.bare { height: 100%; }
.side { background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; padding: 16px; gap: 14px; min-height: 0; }
.brand { padding: 4px 8px 4px; }
.unit { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; }
.unit-ic { color: var(--purple-600); flex: none; }
.cap { font-size: 11px; color: var(--subtle); line-height: 1.2; }
.unit-name { font-weight: 600; font-size: 14px; }
nav { display: flex; flex-direction: column; gap: 4px; flex: 1; overflow-y: auto; }
.nav { display: flex; align-items: center; gap: 12px; height: 40px; padding: 0 12px; border-radius: 10px; color: var(--muted); font-weight: 500; }
.nav:hover { background: var(--bg); }
.nav.on { background: var(--purple-100); color: var(--purple-700); font-weight: 600; }
.nav.on svg { color: var(--purple-600); }
.sect { margin: 18px 12px 6px; font-size: 11px; font-weight: 600; letter-spacing: .06em; color: var(--subtle); }
.me-av { background: linear-gradient(135deg, #9b7fe8 0%, #4c33b0 71%); color: #fff; font-size: 13px; font-weight: 600; }
.me { display: flex; align-items: center; gap: 10px; padding-top: 12px; border-top: 1px solid var(--border); }
.me-t { flex: 1; min-width: 0; } .me-n { font-weight: 600; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ic { display: inline-grid; place-items: center; width: 36px; height: 36px; border-radius: var(--radius-sm); border: 0; background: transparent; color: var(--muted); }
.ic:hover { background: var(--bg); }

.main { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.top { height: var(--topbar-h); flex: none; display: flex; align-items: center; gap: 20px; padding: 0 28px 0 28px; background: var(--surface); border-bottom: 1px solid var(--border); }
.ttl { min-width: 0; } .crumb { font-size: 12px; color: var(--subtle); line-height: 1.2; min-height: 14px; }
.mid { flex: 1; min-width: 0; display: flex; justify-content: center; }
.search { display: flex; align-items: center; gap: 8px; width: 300px; height: 40px; padding: 0 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg); color: var(--subtle); margin-left: auto; }
.search input { flex: 1; border: 0; outline: 0; background: transparent; min-width: 0; color: var(--ink); }
.mid:not(:empty) + .search { margin-left: 0; }
.bell { border: 1px solid var(--border); }
.bellwrap { position: relative; } .pop { position: absolute; right: 0; top: 44px; padding: 12px 16px; white-space: nowrap; box-shadow: var(--shadow-pop); z-index: 20; color: var(--muted); }
.content { flex: 1; min-height: 0; overflow-y: auto; padding: 24px 28px 28px; }
.burger { display: none; }
.scrim { display: none; }

@media (max-width: 960px) {
  .shell { grid-template-columns: 1fr; }
  .side { position: fixed; inset: 0 auto 0 0; width: var(--sidebar-w); z-index: 40; transform: translateX(-100%); transition: transform .2s; }
  .side.open { transform: none; box-shadow: var(--shadow-pop); }
  .scrim { display: block; position: fixed; inset: 0; background: rgba(14, 26, 46, .4); z-index: 30; }
  .burger { display: inline-grid; margin-left: -8px; }
  .top { padding: 0 16px; gap: 12px; } .content { padding: 16px; } .search { display: none; } .mid { display: none; }
}
</style>
