export const mmss = (ms) => { const s = Math.max(0, Math.floor(ms / 1000)); return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); };
export const clock = (d) => new Date(d).toLocaleTimeString("id-ID", { hour12: false }).replace(/\./g, ":");
export const clockHM = (d) => clock(d).slice(0, 5);
export const initials = (name = "") => name.replace(/^(dr\.?|drg\.?)\s+/i, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
export const dur = (s) => (s == null ? "—" : mmss(s * 1000));
export const durLong = (s) => (s == null ? "—" : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}d`);
export const dateLong = (iso) => new Date(iso).toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "short", year: "numeric" });
export const dateShort = (iso) => { const d = new Date(iso); return d.toLocaleDateString("id-ID", { day: "numeric", month: "short" }) + " " + d.toLocaleTimeString("id-ID", { hour12: false, hour: "2-digit", minute: "2-digit" }).replace(".", ":"); };
export const sexAge = (p) => (p ? `${p.sex} · ${p.age} th` : "");
