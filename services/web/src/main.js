import { createApp } from "vue";
import "@fontsource-variable/inter";
import "./styles/tokens.css";
import "./styles/base.css";
import { api, auth } from "./api.js";
import App from "./App.vue";
import { router } from "./router.js";

// Mode widget: token + sesi dari fragmen URL (#session=..&token=..; fragmen tidak dikirim ke server/log).
async function bootFromHash() {
  const h = new URLSearchParams(location.hash.replace(/^#/, ""));
  if (!h.get("token") || !h.get("session")) return;
  auth.token = h.get("token");
  auth.embed = new URLSearchParams(location.search).get("embed") === "1";
  history.replaceState(null, "", location.pathname + location.search + "#/session/" + encodeURIComponent(h.get("session")));
  try { auth.me = await api("/me"); } catch { auth.token = null; }
}

bootFromHash().finally(() => createApp(App).use(router).mount("#app"));
