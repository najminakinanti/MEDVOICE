import test from "node:test";
import assert from "node:assert/strict";
import { createDetector, FRAME } from "./detector.js";

const frame = (amp) => Float32Array.from({ length: FRAME }, (_, i) => amp * Math.sin(i / 5));
const run = (seq, opts) => {
  const ev = [];
  const d = createDetector({
    onStart: (e) => ev.push(["start", e.id, e.startMs]),
    onFrames: (f) => ev.push(["frames", f.length]),
    onEnd: (e) => ev.push(["end", e.id, e.discard]),
  }, opts);
  for (const [amp, n] of seq) for (let i = 0; i < n; i++) d.push(frame(amp));
  return { ev, d };
};

test("ucapan: mulai setelah onset, preroll ikut terkirim, selesai setelah hening 600 ms", () => {
  const { ev } = run([[0.001, 50], [0.2, 40], [0.001, 40]]);
  const starts = ev.filter((e) => e[0] === "start");
  const ends = ev.filter((e) => e[0] === "end");
  assert.equal(starts.length, 1);
  assert.equal(ends.length, 1);
  assert.equal(ends[0][2], false);
  const first = ev.find((e) => e[0] === "frames");
  assert.ok(first[1] >= 15, "preroll 300 ms terkirim bersama frame awal");
  assert.equal(starts[0][2], 700, "suara mulai di 1000 ms, preroll 300 ms");
});

test("klik/derau pendek (< onset) tidak memulai ucapan", () => {
  const { ev } = run([[0.001, 50], [0.3, 2], [0.001, 80]]);
  assert.equal(ev.filter((e) => e[0] === "start").length, 0);
});

test("ucapan sangat pendek dibuang (discard)", () => {
  const { ev } = run([[0.001, 50], [0.3, 4], [0.001, 60]]);
  const end = ev.find((e) => e[0] === "end");
  assert.ok(end && end[2] === true);
});

test("ucapan panjang dipecah paksa pada maxFrames lalu bisa mulai lagi", () => {
  const { ev } = run([[0.001, 50], [0.2, 700]]);
  assert.equal(ev.filter((e) => e[0] === "end").length, 1);
  assert.equal(ev.filter((e) => e[0] === "start").length, 2);
});

test("flush mengakhiri ucapan aktif", () => {
  const { ev, d } = run([[0.001, 50], [0.2, 30]]);
  assert.equal(d.active, true);
  d.flush();
  assert.equal(d.active, false);
  assert.equal(ev.filter((e) => e[0] === "end").length, 1);
});
