// AudioWorklet: teruskan sampel mentah mikrofon ke halaman (dipakai deteksi suara & pratinjau langsung).
class PcmCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) { const copy = ch.slice(); this.port.postMessage(copy, [copy.buffer]); }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
