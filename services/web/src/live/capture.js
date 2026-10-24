// Satu sumber mikrofon -> AudioWorklet (PCM) -> detektor ucapan -> potongan PCM16 16 kHz untuk WebSocket.
import { RATE, FRAME, createDetector } from "./detector.js";

const FLUSH_FRAMES = 5;   // kirim tiap 100 ms audio (bukan tiap 20 ms: lebih sedikit pesan)

export function toPcm16(frames) {
  let n = 0;
  for (const f of frames) n += f.length;
  const out = new Int16Array(n);
  let o = 0;
  for (const f of frames) for (let i = 0; i < f.length; i++) out[o++] = Math.max(-1, Math.min(1, f[i])) * 32767;
  return out;
}

/** Turunkan sampel ke 16 kHz bila AudioContext tidak bisa dibuat 16 kHz (mis. Firefox). Interpolasi linear. */
export function makeResampler(fromRate) {
  if (fromRate === RATE) return (x) => x;
  const ratio = fromRate / RATE;
  let carry = new Float32Array(0), pos = 0;
  return (x) => {
    const buf = new Float32Array(carry.length + x.length);
    buf.set(carry); buf.set(x, carry.length);
    const out = [];
    for (; pos + 1 < buf.length; pos += ratio) {
      const i = Math.floor(pos), f = pos - i;
      out.push(buf[i] * (1 - f) + buf[i + 1] * f);
    }
    const keep = Math.floor(pos);
    carry = buf.slice(keep); pos -= keep;
    return Float32Array.from(out);
  };
}

/**
 * handlers: { onStart({id,startMs}), onAudio(pcm16), onEnd({id,discard}), onLevel(rms) }
 * Kembalikan { setPaused(b), activeId(), close() }.
 */
export async function openSource(stream, handlers) {
  let ctx;
  try { ctx = new AudioContext({ sampleRate: RATE }); } catch { ctx = new AudioContext(); }
  await ctx.resume();
  await ctx.audioWorklet.addModule(import.meta.env.BASE_URL + "pcm-worklet.js");
  const node = new AudioWorkletNode(ctx, "pcm-capture");
  const mute = ctx.createGain();
  mute.gain.value = 0;                                          // tanpa suara ke speaker
  ctx.createMediaStreamSource(stream).connect(node);
  node.connect(mute); mute.connect(ctx.destination);

  const resample = makeResampler(ctx.sampleRate);
  let out = [], paused = false, acc = new Float32Array(FRAME), n = 0;
  const flush = () => { if (out.length) { handlers.onAudio(toPcm16(out)); out = []; } };
  const det = createDetector({
    onStart: (e) => handlers.onStart(e),
    onFrames: (frames) => { out.push(...frames); if (out.length >= FLUSH_FRAMES) flush(); },
    onEnd: (e) => { flush(); handlers.onEnd(e); },
  });

  node.port.onmessage = (ev) => {
    if (paused) return;
    const d = resample(ev.data);
    for (let i = 0; i < d.length; i++) {
      acc[n++] = d[i];
      if (n === FRAME) { handlers.onLevel(det.push(acc.slice())); n = 0; }
    }
  };

  return {
    setPaused(p) { paused = p; if (p) { det.flush(); n = 0; } },
    activeId: () => det.activeId,
    close() { try { det.flush(); } catch { /* sudah tertutup */ } node.port.onmessage = null; ctx.close().catch(() => {}); },
  };
}
