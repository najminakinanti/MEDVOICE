import { reactive } from "vue";

const KEY = "medvoice-theme";

function stored() {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

export const theme = reactive({
  dark: (stored() ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark",
});

function apply() {
  document.documentElement.dataset.theme = theme.dark ? "dark" : "light";
}

export function toggleTheme() {
  theme.dark = !theme.dark;
  apply();
  try { localStorage.setItem(KEY, theme.dark ? "dark" : "light"); } catch { /* penyimpanan diblokir */ }
}

apply();
