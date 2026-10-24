/* MedVoice widget: sematkan UI perekaman+review di web RS.
 *
 * SERVER Anda memanggil  POST /v1/sessions/{id}/widget-token  (dengan X-API-Key) dan memberikan {token} ke browser.
 * JANGAN menaruh API key di JavaScript/halaman web. Token hanya berlaku untuk satu sesi dan 1 jam.
 *
 *   <div id="mv"></div>
 *   <script src="https://ENGINE/ui/widget.js"></script>
 *   <script>
 *     const w = MedVoice.mount("#mv", { baseUrl: "https://ENGINE", sessionId: "...", token: "...",
 *                                       onEvent: (e) => console.log(e.type, e.status) });   // review_loaded | approved | submitted
 *   </script>
 */
(function () {
  "use strict";
  window.MedVoice = {
    mount: function (target, opts) {
      var host = typeof target === "string" ? document.querySelector(target) : target;
      if (!host) throw new Error("MedVoice: elemen tujuan tidak ditemukan");
      if (!opts || !opts.baseUrl || !opts.sessionId || !opts.token) throw new Error("MedVoice: baseUrl, sessionId, token wajib");
      var base = opts.baseUrl.replace(/\/$/, "");
      var f = document.createElement("iframe");
      f.src = base + "/ui/?embed=1#session=" + encodeURIComponent(opts.sessionId) + "&token=" + encodeURIComponent(opts.token);
      f.allow = "microphone";
      f.style.cssText = "width:100%;height:" + (opts.height || "720px") + ";border:0";
      f.title = "MedVoice";
      host.appendChild(f);
      function onMsg(ev) {
        if (ev.origin !== new URL(base).origin || !ev.data || ev.data.source !== "medvoice") return;
        if (opts.onEvent) opts.onEvent(ev.data);
      }
      window.addEventListener("message", onMsg);
      return { destroy: function () { window.removeEventListener("message", onMsg); f.remove(); } };
    },
  };
})();
