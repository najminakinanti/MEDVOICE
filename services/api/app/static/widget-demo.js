"use strict";
const h = new URLSearchParams(location.hash.replace(/^#/, ""));
window.w = MedVoice.mount("#mv", {
  baseUrl: location.origin, sessionId: h.get("session"), token: h.get("token"), height: "800px",
  onEvent: (e) => { document.getElementById("log").textContent += `${e.type} status=${e.status}\n`; },
});
