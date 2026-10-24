<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, auth, errText } from "../api.js";
import { app } from "../store.js";
import AppShell from "../components/AppShell.vue";
import Stepper from "../components/Stepper.vue";
import ProcessingPanel from "./ProcessingPanel.vue";
import RecordPanel from "./RecordPanel.vue";
import ResultPanel from "./ResultPanel.vue";

const route = useRoute(), router = useRouter();
const session = ref(null), err = ref(""), step = ref(1);
const mobile = ref(window.matchMedia("(max-width: 760px)").matches);
const mq = window.matchMedia("(max-width: 760px)");
const onMq = (e) => { mobile.value = e.matches; };
mq.addEventListener("change", onMq);
onBeforeUnmount(() => mq.removeEventListener("change", onMq));

async function load() {
  err.value = "";
  try { session.value = await api(`/sessions/${route.params.id}`); app.activeSessionId = route.params.id; }
  catch (e) { err.value = errText(e); }
}
onMounted(load);
watch(() => route.params.id, () => { session.value = null; load(); });

const phase = computed(() => {
  const s = session.value && session.value.status;
  return s === "recording" ? "record" : s === "processing" ? "process" : "result";
});
const autostart = computed(() => route.query.autostart === "1");
const title = computed(() => (phase.value === "record" ? "Sesi Konsultasi" : "Hasil Sesi"));
const crumb = computed(() => "Antrean › " + (session.value?.patient?.name || session.value?.no_rawat || ""));
const stepNo = computed(() => (phase.value === "record" ? 1 : phase.value === "process" ? 2 : step.value));

function finished() { router.replace({ path: route.path }); load(); }       // buang ?autostart agar muat ulang tidak merekam lagi
function exit() { router.push("/queue"); }
</script>

<template>
  <AppShell :bare="auth.embed || (phase === 'record' && mobile)" :title="title" :crumb="crumb" :search="false">
    <template #center><Stepper v-if="session && !(phase === 'record')" :current="stepNo" /></template>
    <div v-if="err" class="banner bad" role="alert">{{ err }} <router-link to="/queue" class="lnk">Kembali ke antrean</router-link></div>
    <div v-else-if="!session" class="load"><span class="spinner" /></div>
    <div v-else class="body" :class="{ rec: phase === 'record' }">
      <RecordPanel v-if="phase === 'record'" :session="session" :autostart="autostart" :mobile="mobile" @finished="finished" @exit="exit" />
      <ProcessingPanel v-else-if="phase === 'process'" :session="session" @done="load" />
      <ResultPanel v-else :session="session" @step="(n) => (step = n)" @reload="load" @next="exit" />
    </div>
  </AppShell>
</template>

<style scoped>
.load { display: grid; place-items: center; padding: 60px; } .lnk { color: var(--purple-600); font-weight: 600; margin-left: 8px; }
.body.rec { height: 100%; }
</style>
