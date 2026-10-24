// Pendeteksi ucapan berbasis energi (RMS) dengan lantai derau adaptif. Murni (tanpa DOM) agar bisa diuji.
// Frame = 20 ms @ 16 kHz = 320 sampel Float32. Satu "ucapan" = dari suara mulai sampai jeda cukup panjang.
export const RATE = 16000;
export const FRAME = 320;
export const FRAME_MS = 20;

const DEFAULTS = {
  preroll: 15,        // 300 ms audio sebelum suara terdeteksi ikut dikirim (awal kata tidak terpotong)
  onsetFrames: 3,     // 60 ms suara berturut-turut sebelum dianggap mulai bicara (klik/derau pendek diabaikan)
  endSilence: 24,     // 480 ms hening = ucapan selesai (lebih pendek = teks akhir lebih cepat)
  maxFrames: 600,     // 12 dtk: pecah paksa agar teks akhir tidak menunggu terlalu lama
  minVoiced: 8,       // ucapan dengan < 160 ms suara dibuang
  minRms: 0.006,      // ~-44 dBFS: suara pelan dari mikrofon asli tetap terdeteksi (derau ruangan biasanya < 0.004)
  floorMul: 3,
};

export function rms(fr) {
  let s = 0;
  for (let i = 0; i < fr.length; i++) s += fr[i] * fr[i];
  return Math.sqrt(s / fr.length);
}

/** callbacks: onStart({id,startMs}), onFrames(frames[]), onEnd({id, discard}) */
export function createDetector(cb, opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  let floor = 0.003, t = 0, nextId = 1, pre = [], onset = 0, utt = null;

  const end = () => {
    const u = utt; utt = null; pre = []; onset = 0;
    cb.onEnd({ id: u.id, discard: u.voiced < o.minVoiced });
  };

  return {
    /** Beri satu frame; kembalikan RMS-nya (untuk indikator level). */
    push(fr) {
      const level = rms(fr);
      if (level < floor * 1.5) floor = 0.95 * floor + 0.05 * level;
      else floor = Math.min(floor * 1.0003, 0.02);
      const voiced = level > Math.max(o.minRms, floor * o.floorMul);
      t += FRAME_MS;
      if (!utt) {
        pre.push(fr);
        if (pre.length > o.preroll + o.onsetFrames) pre.shift();
        onset = voiced ? onset + 1 : 0;
        if (onset >= o.onsetFrames) {
          const startMs = t - pre.length * FRAME_MS;   // awal frame pertama yang dikirim (termasuk preroll)
          utt = { id: nextId++, n: pre.length, voiced: onset, silent: 0 };
          cb.onStart({ id: utt.id, startMs });
          cb.onFrames(pre);
          pre = [];
        }
        return level;
      }
      cb.onFrames([fr]);
      utt.n++;
      if (voiced) { utt.voiced++; utt.silent = 0; } else utt.silent++;
      if (utt.silent >= o.endSilence || utt.n >= o.maxFrames) end();
      return level;
    },
    /** Akhiri ucapan yang sedang berjalan (jeda/berhenti merekam). */
    flush() { if (utt) end(); pre = []; onset = 0; },
    get active() { return !!utt; },
    get activeId() { return utt ? utt.id : null; },
  };
}
