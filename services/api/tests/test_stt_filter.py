"""Filter halusinasi & pemecahan ucapan di layanan STT (tanpa memuat model Whisper)."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS

STT_DIR = Path(__file__).resolve().parents[2] / "stt"
sys.path.insert(0, str(STT_DIR))     # main.py mengimpor stream.py
SPEC = importlib.util.spec_from_file_location("stt_main", STT_DIR / "main.py")
stt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stt)


def W(word, start, end):
    return NS(word=word, start=start, end=end)


def test_kalimat_penutup_video_dibuang_tapi_ucapan_klinis_tidak():
    for t in ("Sampai jumpa di video selanjutnya", "Terima kasih telah menonton!", "Jangan lupa subscribe ya",
              "Subtitle by Amara.org", "Thanks for watching"):
        assert stt.is_hallucination(t), t
    for t in ("Terima kasih, Dok.", "Sampai jumpa dua minggu lagi ya, Pak.", "Kontrol minggu depan, video endoskopi nanti"):
        assert not stt.is_hallucination(t), t


def test_segmen_bukan_ucapan_menurut_model_dibuang():
    seg = NS(text="hmm", no_speech_prob=0.9, avg_logprob=-1.2)
    assert stt.is_hallucination("hmm", seg)
    ok = NS(text="Batuk dua hari", no_speech_prob=0.05, avg_logprob=-0.2)
    assert not stt.is_hallucination("Batuk dua hari", ok)


def test_pecah_per_giliran_bicara_dan_buang_halusinasi():
    s1 = NS(text=" Selamat siang. Gimana kabarnya?", start=0, end=5, no_speech_prob=0.0, avg_logprob=-0.1,
            words=[W(" Selamat", 0.0, 0.6), W(" siang.", 0.6, 1.1), W(" Gimana", 4.0, 4.4), W(" kabarnya?", 4.4, 5.0)])
    s2 = NS(text=" Sampai jumpa di video selanjutnya", start=60, end=63, no_speech_prob=0.0, avg_logprob=-0.1,
            words=[W(" Sampai", 60.0, 60.4), W(" jumpa", 60.4, 60.8)])
    out = stt.utterances([s1, s2], 1.0)
    assert [u["text"] for u in out] == ["Selamat siang.", "Gimana kabarnya?"]       # jeda 2,9 dtk memecah; penutup video dibuang
    assert out[1]["start_ms"] == 4000 and out[0]["end_ms"] == 1100
