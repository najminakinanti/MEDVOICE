import json
from pathlib import Path

from app.validator import Item
from evaluation import metrics
from evaluation.run_eval import load_cases, main, run_case

CASES = Path(__file__).resolve().parent.parent / "evaluation" / "cases"


def test_wer():
    assert metrics.wer("tekanan darah seratus", "tekanan darah seratus") == 0
    assert metrics.wer("a b c d", "a x c") == 0.5          # 1 substitusi + 1 hapus / 4
    assert metrics.wer("", "") == 0 and metrics.wer("", "x") == 1
    assert metrics.wer("Halo, Dok!", "halo dok") == 0       # normalisasi


def test_match_status_harus_sama():
    g = [{"field": "alergi", "key": "alergi", "status": "dinegasi"}]
    ok = Item("alergi", "dinegasi", "tidak ada alergi", [0], "alergi obat")
    salah = Item("alergi", "dilaporkan_pasien", "tidak ada alergi", [0], "alergi obat")
    assert metrics.match_field([ok], g, "alergi") == (1, 0, 0)
    assert metrics.match_field([salah], g, "alergi") == (0, 1, 1)     # negasi dibalik = FP + FN


def test_dosis_dikarang_jadi_fp():
    g = [{"field": "obat", "key": "amlodipine", "status": "dinyatakan_dokter", "nama": "amlodipine", "dosis": "5 mg"}]
    benar = Item("obat", "dinyatakan_dokter", "x", [0], "", "amlodipine", "5 mg")
    palsu = Item("obat", "dinyatakan_dokter", "x", [0], "", "amlodipine", "10 mg")
    assert metrics.match_dosis([benar], g) == (1, 0, 0)
    assert metrics.match_dosis([palsu], g) == (0, 1, 1)


def test_prf_none_bila_kosong():
    assert metrics.prf(0, 0, 0) == (None, None)
    assert metrics.prf(3, 1, 1) == (0.75, 0.75)


def test_semua_kasus_valid():
    cases = load_cases(CASES)
    assert len(cases) >= 10
    for c in cases:
        for s in c["segments"]:
            assert s["speaker"] in ("dokter", "pasien") and s["end_ms"] >= s["start_ms"]
        assert c["gold"], c["id"]
        assert "SIMULASI" in c["annotated_by"]
    tags = {t for c in cases for t in c["tags"]}
    assert {"negasi", "rencana", "dosis_kosong", "singkatan", "inggris", "dugaan", "injeksi"} <= tags


def test_replay_llm_baik_vs_halusinasi():
    c = next(x for x in load_cases(CASES) if x["id"] == "01_hipertensi_dasar")
    good = [
        {"field": "tanda_vital", "teks": "TD 160/100", "status": "dinyatakan_dokter",
         "bukti": "Tekanan darah Bapak 160/100 mmHg", "segmen": [2]},
        {"field": "diagnosis", "teks": "hipertensi", "status": "dinyatakan_dokter",
         "bukti": "Diagnosisnya hipertensi", "segmen": [3]},
        {"field": "obat", "teks": "amlodipine", "nama": "amlodipine", "dosis": "5 mg", "status": "dinyatakan_dokter",
         "bukti": "Saya resepkan amlodipine 5 mg satu kali sehari", "segmen": [3]},
    ]
    bad = [
        {"field": "obat", "teks": "captopril", "nama": "captopril", "dosis": "25 mg", "status": "dinyatakan_dokter",
         "bukti": "Saya resepkan captopril 25 mg", "segmen": [3]},
        {"field": "diagnosis", "teks": "gagal jantung", "status": "dinyatakan_dokter",
         "bukti": "Diagnosisnya gagal jantung", "segmen": [3]},
    ]
    cr_p, _ = run_case(c, None, json.dumps({"items": good}))
    cr_h, _ = run_case(c, None, json.dumps({"items": good + bad}))
    assert cr_p["n_ditolak"] == 0
    assert cr_h["n_ditolak"] == 2                      # captopril & gagal jantung dikarang -> ditolak
    agg = metrics.aggregate([cr_h])
    assert agg["mentah"]["obat"]["fp"] == 1 and agg["lolos"]["obat"]["fp"] == 0
    assert agg["lolos"]["obat"]["precision"] == 1.0
    assert agg["mentah"]["dosis"]["fp"] == 1 and agg["lolos"]["dosis"]["fp"] == 0
    assert agg["mentah"]["diagnosis"]["fp"] == 1 and agg["lolos"]["diagnosis"]["fp"] == 0


def test_run_eval_cli_replay(tmp_path):
    cases = load_cases(CASES)
    f = tmp_path / "rusak.json"
    f.write_text(json.dumps({c["id"]: "bukan json" for c in cases}), encoding="utf-8")
    assert main(["--replay", str(f), "--out", str(tmp_path / "out")]) == 0
    s = json.loads(next((tmp_path / "out").glob("*_summary.json")).read_text(encoding="utf-8"))
    assert s["summary"]["_ringkasan"]["kasus_json_gagal"] == len(cases)


def test_kunci_gold_boleh_beberapa_varian():
    g = {"field": "alergi", "key": ["allergy", "alergi"], "status": "dinegasi"}
    assert metrics.item_matches_gold(Item("alergi", "dinegasi", "x", [0], "tidak ada alergi"), g)
    assert metrics.item_matches_gold(Item("alergi", "dinegasi", "x", [0], "no allergy"), g)
    assert not metrics.item_matches_gold(Item("alergi", "dinegasi", "x", [0], "demam"), g)
