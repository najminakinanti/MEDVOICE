// Mode widget (iframe di web RS): hanya id & status (tanpa data klinis) dikirim ke halaman induk.
import { auth } from "./api.js";

export function notifyParent(type, sessionId, status) {
  if (!auth.embed || window.parent === window) return;
  let target = "*";
  try { target = new URL(document.referrer).origin; } catch { /* tanpa referrer */ }
  window.parent.postMessage({ source: "medvoice", type, sessionId, status }, target);
}
