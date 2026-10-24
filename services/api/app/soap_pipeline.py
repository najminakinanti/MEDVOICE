"""Pipeline asinkron tahap 3-7: STT -> ekstraksi -> validator -> SOAP (versi AI).
Dijalankan oleh worker setelah dokter menekan Selesai. Tidak pernah menulis ke SIMRS.

Keamanan: pesan exception TIDAK di-log/disimpan (bisa memuat isi transkrip); hanya kode."""
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from . import extraction, llm, soap, stt_client, vocab
from .audit import audit
from .config import get_settings
from .db import engine
from .terminology import mapper, retrieve
from .validator import Item, Segment, validate_all

log = logging.getLogger("medvoice.pipeline")

CHANNEL_SPEAKER = {"dokter": "dokter", "pasien": "pasien", "mixed": "tidak_diketahui"}
KINDS = ["stt", "extract", "validate", "map_codes", "soap"]


def _job(session_id: str, kind: str, status: str, error: str | None = None) -> None:
    running, finished = status == "running", status in ("succeeded", "failed")
    with engine().begin() as c:
        c.execute(text(
            "UPDATE jobs SET status=CAST(:st AS job_status), error_code=:er, "
            "attempts=attempts+CASE WHEN :run THEN 1 ELSE 0 END, "
            "started_at=CASE WHEN :run THEN COALESCE(started_at, now()) ELSE started_at END, "
            "finished_at=CASE WHEN :fin THEN now() END "
            "WHERE session_id=:s AND kind=:k"),
            dict(st=status, er=error, run=running, fin=finished, s=session_id, k=kind))


def _skip_rest(session_id: str, from_kind: str, reason: str) -> None:
    for k in KINDS[KINDS.index(from_kind):]:
        _job(session_id, k, "failed", reason)


def _set_status(session_id: str, status: str) -> None:
    with engine().begin() as c:
        c.execute(text("UPDATE consult_sessions SET status=:st WHERE id=:s"), dict(st=status, s=session_id))


def stage_stt(session_id: str, client_id: str) -> tuple[str, bool]:
    s = get_settings()
    d = Path(s.audio_dir) / session_id
    files = sorted(p for p in d.glob("*") if p.is_file()) if d.exists() else []
    merged: list[dict] = []
    model, lang = "none", None
    try:
        for p in files:
            speaker = CHANNEL_SPEAKER.get(p.stem, "tidak_diketahui")
            res = stt_client.transcribe(p.as_posix(), vocab.initial_prompt())
            model, lang = res.get("model", model), res.get("language", lang)
            for seg in res.get("segments", []):
                if seg["text"].strip():
                    merged.append({**seg, "speaker": speaker})
    finally:
        if d.exists():
            if s.keep_audio:                       # dev saja (KEEP_AUDIO=true): pindahkan, jangan hapus
                keep = Path(s.audio_dir) / "_kept" / session_id
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.rmtree(keep, ignore_errors=True)
                shutil.move(d.as_posix(), keep.as_posix())
            else:
                shutil.rmtree(d, ignore_errors=True)   # audio asli dihapus setelah STT (berhasil atau tidak)
    if s.gpu_timeshare:
        stt_client.unload()          # lepas VRAM sebelum LLM memuat model
    merged.sort(key=lambda x: (x["start_ms"], x["end_ms"]))
    empty = len(merged) == 0
    purge_after = datetime.now(timezone.utc) + timedelta(days=s.transcript_retention_days)
    with engine().begin() as c:
        tid = c.execute(text(
            "INSERT INTO transcripts(client_id, session_id, stt_model, language, is_empty, purge_after) "
            "VALUES (:c,:s,:m,:l,:e,:p) RETURNING id"),
            dict(c=client_id, s=session_id, m=model, l=lang, e=empty, p=purge_after)).scalar()
        for i, seg in enumerate(merged):
            c.execute(text(
                "INSERT INTO transcript_segments(transcript_id, idx, start_ms, end_ms, speaker, text) "
                "VALUES (:t,:i,:a,:b,:sp,:tx)"),
                dict(t=tid, i=i, a=seg["start_ms"], b=max(seg["end_ms"], seg["start_ms"]),
                     sp=seg["speaker"], tx=seg["text"].strip()))
        if not s.keep_audio:
            c.execute(text("UPDATE consult_sessions SET audio_deleted_at=now() WHERE id=:s"), dict(s=session_id))
        audit(c, action="audio.kept_dev" if s.keep_audio else "audio.deleted", actor_type="system",
              client_id=client_id, session_id=session_id, after={"files": len(files)})
    return str(tid), empty


def _load_segments(transcript_id: str) -> list[Segment]:
    with engine().begin() as c:
        rows = c.execute(text(
            "SELECT idx, start_ms, end_ms, speaker, text FROM transcript_segments "
            "WHERE transcript_id=:t ORDER BY idx"), dict(t=transcript_id)).all()
    return [Segment(*r) for r in rows]


def stage_extract(session_id: str, client_id: str, transcript_id: str, model: str | None = None) -> tuple[str, bool]:
    segments = _load_segments(transcript_id)
    res = extraction.extract(segments, model=model)
    s = get_settings()
    with engine().begin() as c:
        eid = c.execute(text(
            "INSERT INTO extractions(client_id, session_id, transcript_id, llm_model, prompt_version, "
            "parse_attempts, manual_input, dropped_items) VALUES (:c,:s,:t,:m,:p,:a,:man,:d) RETURNING id"),
            dict(c=client_id, s=session_id, t=transcript_id, m=model or s.llm_model,
                 p=extraction.PROMPT_VERSION, a=res["attempts"], man=res["manual"],
                 d=res["dropped"])).scalar()
        for it in res["items"]:
            c.execute(text(
                "INSERT INTO extraction_items(extraction_id, field, value, status, evidence, start_ms, end_ms, "
                "segment_idxs) VALUES (:e,:f,CAST(:v AS jsonb),:st,:ev,0,0,:sg)"),
                dict(e=eid, f=it.field, v=json.dumps({"teks": it.teks, "nama": it.nama, "dosis": it.dosis}),
                     st=it.status, ev=it.evidence, sg=it.segment_idxs))
    return str(eid), res["manual"]


def stage_validate(session_id: str, extraction_id: str, transcript_id: str) -> None:
    s = get_settings()
    segments = _load_segments(transcript_id)
    with engine().begin() as c:
        rows = c.execute(text(
            "SELECT id, field, status, evidence, segment_idxs, value FROM extraction_items "
            "WHERE extraction_id=:e ORDER BY id"), dict(e=extraction_id)).all()
        dropped = c.execute(text("SELECT dropped_items FROM extractions WHERE id=:e"),
                            dict(e=extraction_id)).scalar()
    items = [Item(r[1], r[2], r[3], list(r[4]), r[5].get("teks", ""), r[5].get("nama"), r[5].get("dosis"))
             for r in rows]
    out = validate_all(items, segments, vocab.drug_names(), vocab.vocab_terms(), dropped,
                       s.low_quality_reject_ratio)
    with engine().begin() as c:
        for r, res in zip(rows, out["results"]):
            c.execute(text(
                "UPDATE extraction_items SET verdict=:v, verdict_reasons=CAST(:rs AS jsonb), "
                "segment_idxs=:sg, start_ms=:a, end_ms=:b WHERE id=:i"),
                dict(v=res.verdict, rs=json.dumps(res.reasons), sg=res.segment_idxs,
                     a=res.start_ms, b=res.end_ms, i=r[0]))
        for m in out["missed"]:
            c.execute(text(
                "INSERT INTO missed_items(extraction_id, kind, mention, start_ms, end_ms) "
                "VALUES (:e,:k,:m,:a,:b)"), dict(e=extraction_id, k=m.kind, m=m.mention, a=m.start_ms, b=m.end_ms))
        c.execute(text("UPDATE extractions SET low_quality=:l WHERE id=:e"),
                  dict(l=out["low_quality"], e=extraction_id))


def stage_map_codes(session_id: str, client_id: str, extraction_id: str) -> int:
    """Pemetaan kode untuk butir yang lolos (diagnosis->ICD10, obat->KFA, penunjang->LOINC, tindakan->ICD9CM).
    Sistem yang tabelnya belum dimuat dilewati. Hasil hanya usulan; dokter memutuskan."""
    s = get_settings()
    with engine().begin() as c:
        loaded = {sy: retrieve.latest_system(c, sy) for sy in set(mapper.FIELD_SYSTEM.values())}
        rows = c.execute(text(
            "SELECT id, field, value, status, evidence, verdict, verdict_reasons FROM extraction_items "
            "WHERE extraction_id=:e AND verdict IN ('diterima','ditandai') AND field = ANY(:f) ORDER BY id"),
            dict(e=extraction_id, f=list(mapper.FIELD_SYSTEM))).all()
    if not loaded.get("ICD10"):
        raise RuntimeError("terminology_not_loaded")

    def retrieve_fn(system, queries, k):
        with engine().begin() as c:
            return retrieve.retrieve(c, system, queries, k)

    def exists_fn(system, code):
        with engine().begin() as c:
            return retrieve.code_exists(c, system, code)

    n = 0
    for iid, fld, val, status, evidence, verdict, reasons in rows:
        system = mapper.FIELD_SYSTEM[fld]
        if not loaded.get(system):
            continue
        item = {"teks": val.get("teks") or "", "nama": val.get("nama"), "dosis": val.get("dosis"),
                "evidence": evidence, "status": status, "verdict": verdict, "reasons": list(reasons)}
        res = mapper.map_item(
            item, field=fld, retrieve_fn=retrieve_fn, exists_fn=exists_fn,
            llm_fn=lambda sy, us: llm.call_llm(sy, us, json_mode=True), k=s.map_candidates_k,
            translate=s.map_translate, margin=s.map_margin)
        cands = [{"code": c["code"], "display": c["display"], "sim": round(c.get("sim", 0), 3)} for c in res.candidates]
        with engine().begin() as c:
            c.execute(text(
                "INSERT INTO code_suggestions(client_id, session_id, item_id, system, candidates, suggested_code, "
                "confidence, state, final_code, reason, system_version) "
                "VALUES (:c,:s,:i,:sy,CAST(:cd AS jsonb),:sc,:cf,:st,:fc,:rs,:sv) "
                "ON CONFLICT (item_id, system) DO NOTHING"),
                dict(c=client_id, s=session_id, i=iid, sy=system, cd=json.dumps(cands), sc=res.suggested_code,
                     cf=res.confidence, st=res.state, fc=res.suggested_code if res.state == "terisi" else None,
                     rs=res.reason, sv=loaded[system][1]))
        n += 1
    return n


def stage_soap(session_id: str, client_id: str, extraction_id: str) -> None:
    with engine().begin() as c:
        rows = c.execute(text(
            "SELECT id, field, status, value, verdict, verdict_reasons FROM extraction_items "
            "WHERE extraction_id=:e ORDER BY id"), dict(e=extraction_id)).all()
        items = [soap.SoapItem(str(r[0]), r[1], r[2], r[3].get("teks", ""), r[3].get("nama"),
                               r[3].get("dosis"), r[4], list(r[5])) for r in rows]
        sentences = soap.compose(items)
        ver = c.execute(text("SELECT COALESCE(MAX(version),0)+1 FROM soap_notes WHERE session_id=:s"),
                        dict(s=session_id)).scalar()
        sid = c.execute(text(
            "INSERT INTO soap_notes(client_id, session_id, version, source) VALUES (:c,:s,:v,'ai') RETURNING id"),
            dict(c=client_id, s=session_id, v=ver)).scalar()
        for s_ in sentences:
            c.execute(text(
                "INSERT INTO soap_sentences(soap_id, section, idx, text, evidence_item_ids, is_ai_suspicion, "
                "flagged, origin, ai_text) VALUES (:so,:sec,:i,:t,CAST(:ev AS uuid[]),:sus,:fl,'ai',:t)"),
                dict(so=sid, sec=s_.section, i=s_.idx, t=s_.text,
                     ev="{" + ",".join(s_.evidence_item_ids) + "}", sus=s_.is_ai_suspicion, fl=s_.flagged))
        audit(c, action="soap.ai_generated", actor_type="ai", client_id=client_id, session_id=session_id,
              entity="soap_notes", entity_id=sid, after={"version": ver, "sentences": len(sentences)})


def run_pipeline(session_id: str, model: str | None = None) -> None:
    with engine().begin() as c:
        row = c.execute(text("SELECT client_id FROM consult_sessions WHERE id=:s"), dict(s=session_id)).first()
    if not row:
        return
    client_id = str(row[0])
    stage = "stt"
    try:
        _job(session_id, "stt", "running")
        transcript_id, empty = stage_stt(session_id, client_id)
        if empty:
            _job(session_id, "stt", "succeeded")
            _skip_rest(session_id, "extract", "skipped_stt_empty")
            _set_status(session_id, "failed")
            _notify(session_id)
            return
        _job(session_id, "stt", "succeeded")

        stage = "extract"
        _job(session_id, "extract", "running")
        extraction_id, manual = stage_extract(session_id, client_id, transcript_id, model)
        if manual:
            _job(session_id, "extract", "failed", "llm_json_invalid")
            _skip_rest(session_id, "validate", "skipped_extraction_manual")
            _set_status(session_id, "failed")
            _notify(session_id)
            return
        _job(session_id, "extract", "succeeded")

        stage = "validate"
        _job(session_id, "validate", "running")
        stage_validate(session_id, extraction_id, transcript_id)
        _job(session_id, "validate", "succeeded")

        stage = "map_codes"
        _job(session_id, "map_codes", "running")
        try:
            stage_map_codes(session_id, client_id, extraction_id)
            _job(session_id, "map_codes", "succeeded")
        except Exception as e:  # noqa: BLE001 - pemetaan kode tidak boleh menghalangi SOAP
            log.error("map_codes_failed error=%s", type(e).__name__)
            _job(session_id, "map_codes", "failed",
                 str(e) if str(e) == "terminology_not_loaded" else type(e).__name__)

        stage = "soap"
        _job(session_id, "soap", "running")
        stage_soap(session_id, client_id, extraction_id)
        _job(session_id, "soap", "succeeded")
        _set_status(session_id, "review")
        _notify(session_id)
    except Exception as e:  # noqa: BLE001 - hanya kode galat yang disimpan
        code = type(e).__name__
        log.error("pipeline_failed stage=%s error=%s", stage, code)
        _job(session_id, stage, "failed", code)
        if stage != "soap":
            _skip_rest(session_id, KINDS[KINDS.index(stage) + 1], "skipped_prior_failure")
        _set_status(session_id, "failed")
        _notify(session_id)


def _notify(session_id: str) -> None:
    """Webhook 'session.processed' (gagal kirim tidak boleh menggagalkan pipeline)."""
    try:
        from .worker import webhook_task
        webhook_task.delay(session_id, "session.processed")
    except Exception as e:  # noqa: BLE001
        log.error("webhook_enqueue_failed error=%s", type(e).__name__)


def purge_expired() -> dict:
    """Hapus transkrip yang lewat masa retensi + sisa audio basi (>24 jam). Return ringkasan jumlah."""
    s = get_settings()
    purged = 0
    with engine().begin() as c:
        rows = c.execute(text(
            "SELECT t.id, t.client_id, t.session_id FROM transcripts t "
            "WHERE t.purged_at IS NULL AND t.purge_after < now()")).all()
        for tid, cid, sid in rows:
            c.execute(text("DELETE FROM transcript_segments WHERE transcript_id=:t"), dict(t=tid))
            c.execute(text("UPDATE transcripts SET purged_at=now() WHERE id=:t"), dict(t=tid))
            audit(c, action="transcript.purged", actor_type="system", client_id=cid, session_id=sid,
                  entity="transcripts", entity_id=tid)
            purged += 1
    stale = 0
    base = Path(s.audio_dir)
    if base.exists():
        cutoff = datetime.now().timestamp() - 24 * 3600
        for d in base.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                stale += 1
    return {"transcripts_purged": purged, "stale_audio_dirs_removed": stale}
