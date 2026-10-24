import asyncio
import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from . import ratelimit, security
from .adapters import get_adapter
from .audit import audit
from .config import get_settings
from .db import get_conn
from .deps import Principal, get_principal, load_session, require_doctor
from .soap import EMPTY_TEXT
from .terminology import retrieve as term

router = APIRouter(prefix="/v1")
ALLOWED_EXT = {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac"}
EDITABLE = ("review", "failed")


def _later(bg: BackgroundTasks, session_id: str, event: str) -> None:
    """Jadwalkan webhook SETELAH transaksi request ter-commit."""
    from .worker import webhook_task
    bg.add_task(webhook_task.delay, session_id, event)


# ---------------------------------------------------------------- auth
class LoginIn(BaseModel):
    client: str
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, request: Request, conn=Depends(get_conn)):
    ip = request.client.host if request.client else "?"
    if not ratelimit.allow(f"login:{ip}", get_settings().login_rate_per_min):
        raise HTTPException(429, "rate_limited")
    row = conn.execute(text(
        "SELECT d.id, d.password_hash, c.id FROM doctors d JOIN clients c ON c.id=d.client_id "
        "WHERE c.name=:c AND d.username=:u AND d.active AND c.active"),
        dict(c=body.client, u=body.username)).first()
    ok = security.verify_password(body.password, row[1] if row else None)
    if not row or not ok:
        audit(conn, action="auth.login_failed", actor_type="dokter", actor_id=body.username, ip=ip)
        return JSONResponse({"detail": "invalid_credentials"}, status_code=401)   # bukan raise: audit tetap ter-commit
    audit(conn, action="auth.login", actor_type="dokter", actor_id=row[0], client_id=row[2], ip=ip)
    ttl = get_settings().jwt_ttl_minutes * 60
    return {"access_token": security.make_token(str(row[0]), str(row[2])), "token_type": "bearer", "expires_in": ttl}


# ---------------------------------------------------------------- sesi
class Consent(BaseModel):
    given: bool
    recorded_by: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=1000)


class DoctorRef(BaseModel):
    simrs_user_id: str
    display_name: str


class SessionIn(BaseModel):
    no_rawat: str = Field(min_length=1, max_length=100)
    consent: Consent
    doctor: DoctorRef | None = None


@router.post("/sessions", status_code=201)
def create_session(body: SessionIn, p: Principal = Depends(get_principal), conn=Depends(get_conn)):
    if p.session_scope:
        raise HTTPException(403, "scoped_token_cannot_create_session")
    if not body.consent.given:
        raise HTTPException(422, "consent_required")
    if p.kind == "doctor":
        doctor_id, simrs_id = p.doctor_id, p.doctor_simrs_id
    else:
        if not body.doctor:
            raise HTTPException(422, "doctor_required_for_api_key")
        doctor_id = conn.execute(text(
            "INSERT INTO doctors(client_id, simrs_user_id, username, display_name) VALUES (:c,:s,:s,:n) "
            "ON CONFLICT (client_id, simrs_user_id) DO UPDATE SET display_name=EXCLUDED.display_name "
            "RETURNING id"), dict(c=p.client_id, s=body.doctor.simrs_user_id, n=body.doctor.display_name)).scalar()
        simrs_id = body.doctor.simrs_user_id
    if not get_adapter(p.simrs_adapter).verify_patient_access(simrs_id, body.no_rawat):
        raise HTTPException(403, "patient_access_denied")
    if p.monthly_quota is not None:
        used = conn.execute(text(
            "SELECT count(*) FROM consult_sessions WHERE client_id=:c AND created_at >= date_trunc('month', now())"),
            dict(c=p.client_id)).scalar()
        if used >= p.monthly_quota:
            raise HTTPException(429, "monthly_quota_exceeded")
    sid = conn.execute(text(
        "INSERT INTO consult_sessions(client_id, doctor_id, no_rawat, consent_at, consent_by, consent_note) "
        "VALUES (:c,:d,:n, now(), :cb, :cn) RETURNING id"),
        dict(c=p.client_id, d=doctor_id, n=body.no_rawat, cb=body.consent.recorded_by,
             cn=body.consent.note)).scalar()
    audit(conn, action="session.create", actor_type="dokter" if p.kind == "doctor" else "api_client",
          actor_id=doctor_id if p.kind == "doctor" else p.client_id, client_id=p.client_id, session_id=sid,
          entity="consult_sessions", entity_id=sid, after={"consent": True}, ip=p.ip)
    return {"id": str(sid), "status": "recording"}


def _jobs(conn, session_id):
    rows = conn.execute(text("SELECT id, kind, status, error_code FROM jobs WHERE session_id=:s ORDER BY created_at, kind"),
                        dict(s=session_id)).all()
    return [{"id": str(r[0]), "kind": r[1], "status": r[2], "error_code": r[3]} for r in rows]


def _session_meta(conn, p: Principal, s: dict) -> dict:
    """Pasien (dari SIMRS bila adapter mendukung) + waktu mulai/selesai untuk header UI."""
    from .ui_api import patient_of
    t = conn.execute(text("SELECT started_at, finished_at FROM consult_sessions WHERE id=:i"), dict(i=s["id"])).first()
    return {"patient": patient_of(get_adapter(p.simrs_adapter), s["no_rawat"]),
            "started_at": t[0].isoformat() if t and t[0] else None,
            "finished_at": t[1].isoformat() if t and t[1] else None}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, p: Principal = Depends(get_principal), conn=Depends(get_conn)):
    s = load_session(conn, p, session_id)
    return {"id": str(s["id"]), "status": s["status"], "no_rawat": s["no_rawat"], "jobs": _jobs(conn, s["id"]),
            **_session_meta(conn, p, s)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, p: Principal = Depends(get_principal), conn=Depends(get_conn)):
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(404, "job_not_found") from None
    row = conn.execute(text("SELECT session_id, kind, status, error_code FROM jobs WHERE id=:i"), dict(i=job_id)).first()
    if not row:
        raise HTTPException(404, "job_not_found")
    load_session(conn, p, str(row[0]))
    return {"id": job_id, "kind": row[1], "status": row[2], "error_code": row[3]}


@router.post("/sessions/{session_id}/audio")
async def upload_audio(session_id: str, dokter: UploadFile | None = File(None), pasien: UploadFile | None = File(None),
                       mixed: UploadFile | None = File(None), p: Principal = Depends(get_principal),
                       conn=Depends(get_conn)):
    s = load_session(conn, p, session_id)
    if s["status"] != "recording":
        raise HTTPException(409, "session_not_recording")
    cfg = get_settings()
    limit = cfg.max_audio_mb * 1024 * 1024
    d = Path(cfg.audio_dir) / session_id
    d.mkdir(parents=True, exist_ok=True)
    saved = {}
    for name, up in (("dokter", dokter), ("pasien", pasien), ("mixed", mixed)):
        if up is None:
            continue
        ext = os.path.splitext(up.filename or "")[1].lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(415, "unsupported_audio_type")
        for old in d.glob(name + ".*"):
            old.unlink()
        size = 0
        with open(d / (name + ext), "wb") as f:
            while chunk := await up.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    f.close()
                    (d / (name + ext)).unlink(missing_ok=True)
                    raise HTTPException(413, "audio_too_large")
                f.write(chunk)
        saved[name] = size
    if not saved:
        raise HTTPException(422, "no_audio_file")
    audit(conn, action="audio.upload", actor_type="dokter" if p.kind == "doctor" else "api_client",
          actor_id=p.doctor_id or p.client_id, client_id=p.client_id, session_id=session_id,
          after={"channels": list(saved)}, ip=p.ip)
    return {"received": list(saved)}


@router.post("/sessions/{session_id}/finish", status_code=202)
def finish(session_id: str, bg: BackgroundTasks, p: Principal = Depends(get_principal), conn=Depends(get_conn)):
    s = load_session(conn, p, session_id)
    if s["status"] != "recording":
        raise HTTPException(409, "session_not_recording")
    conn.execute(text("UPDATE consult_sessions SET status='processing', finished_at=now() WHERE id=:s"), dict(s=session_id))
    for kind in ("stt", "extract", "validate", "map_codes", "soap"):
        conn.execute(text("INSERT INTO jobs(client_id, session_id, kind) VALUES (:c,:s,:k)"),
                     dict(c=p.client_id, s=session_id, k=kind))
    audit(conn, action="session.finish", actor_type="dokter" if p.kind == "doctor" else "api_client",
          actor_id=p.doctor_id or p.client_id, client_id=p.client_id, session_id=session_id, ip=p.ip)
    from .worker import run_pipeline_task
    bg.add_task(run_pipeline_task.delay, session_id)    # setelah commit
    return {"status": "processing", "jobs": _jobs(conn, session_id)}


# ---------------------------------------------------------------- review
def _soap_payload(conn, soap_id):
    n = conn.execute(text("SELECT id, version, source, approved_at FROM soap_notes WHERE id=:i"), dict(i=soap_id)).first()
    rows = conn.execute(text(
        "SELECT id, section, idx, text, evidence_item_ids, is_ai_suspicion, flagged, origin, ai_text "
        "FROM soap_sentences WHERE soap_id=:i ORDER BY array_position(ARRAY['S','O','A','P'], section::text), idx"),
        dict(i=soap_id)).all()
    return {"id": str(n[0]), "version": n[1], "source": n[2], "approved": n[3] is not None,
            "approved_at": n[3].isoformat() if n[3] else None,
            "sentences": [{"id": str(r[0]), "section": r[1], "idx": r[2], "text": r[3],
                           "evidence_item_ids": [str(x) for x in r[4]], "is_ai_suspicion": r[5],
                           "flagged": r[6], "origin": r[7], "ai_text": r[8]} for r in rows]}


def _latest_soap_id(conn, session_id):
    return conn.execute(text("SELECT id FROM soap_notes WHERE session_id=:s ORDER BY version DESC LIMIT 1"),
                        dict(s=session_id)).scalar()


def _codes_payload(conn, session_id):
    rows = conn.execute(text(
        "SELECT id, item_id, system, candidates, suggested_code, confidence, state, final_code, reason, system_version "
        "FROM code_suggestions WHERE session_id=:s ORDER BY item_id"), dict(s=session_id)).all()
    out = []
    for r in rows:
        disp = {}
        for code in {r[4], r[7]} - {None}:
            e = term.code_exists(conn, r[2], code)
            if e:
                disp[code] = e["display"]
        out.append({"id": str(r[0]), "item_id": str(r[1]), "system": r[2], "candidates": r[3],
                    "suggested_code": r[4], "suggested_display": disp.get(r[4]), "confidence": r[5],
                    "state": r[6], "final_code": r[7], "final_display": disp.get(r[7]), "reason": r[8],
                    "system_version": r[9]})
    return out


@router.get("/sessions/{session_id}/review")
def review(session_id: str, p: Principal = Depends(require_doctor), conn=Depends(get_conn)):
    s = load_session(conn, p, session_id)
    jobs = _jobs(conn, session_id)
    tr = conn.execute(text("SELECT id, is_empty, purged_at FROM transcripts WHERE session_id=:s ORDER BY created_at DESC LIMIT 1"),
                      dict(s=session_id)).first()
    segs = []
    if tr and not tr[2]:
        segs = [{"idx": r[0], "start_ms": r[1], "end_ms": r[2], "speaker": r[3], "text": r[4]} for r in conn.execute(
            text("SELECT idx, start_ms, end_ms, speaker, text FROM transcript_segments WHERE transcript_id=:t ORDER BY idx"),
            dict(t=tr[0])).all()]
    ex = conn.execute(text("SELECT id, manual_input, low_quality FROM extractions WHERE session_id=:s ORDER BY created_at DESC LIMIT 1"),
                      dict(s=session_id)).first()
    items, missed = [], []
    if ex:
        items = [{"id": str(r[0]), "field": r[1], "status": r[2], **{k: r[3].get(k) for k in ("teks", "nama", "dosis")},
                  "evidence": r[4], "segment_idxs": r[5], "start_ms": r[6], "end_ms": r[7], "verdict": r[8],
                  "reasons": r[9]} for r in conn.execute(text(
                      "SELECT id, field, status, value, evidence, segment_idxs, start_ms, end_ms, verdict, verdict_reasons "
                      "FROM extraction_items WHERE extraction_id=:e ORDER BY id"), dict(e=ex[0])).all()]
        missed = [{"kind": r[0], "mention": r[1], "start_ms": r[2], "end_ms": r[3]} for r in conn.execute(
            text("SELECT kind, mention, start_ms, end_ms FROM missed_items WHERE extraction_id=:e ORDER BY start_ms"),
            dict(e=ex[0])).all()]
    codes = _codes_payload(conn, session_id)
    notices = []
    errs = {j["kind"]: j["error_code"] for j in jobs}
    if tr and tr[1]:
        notices.append("stt_kosong_isi_manual")
    if ex and ex[1]:
        notices.append("json_llm_rusak_isi_manual")
    if ex and ex[2]:
        notices.append("kualitas_draft_rendah")
    if s["status"] == "failed" and not notices:
        notices.append("pipeline_gagal_isi_manual")
    if tr and tr[2]:
        notices.append("transkrip_sudah_dihapus_sesuai_retensi")
    sid = _latest_soap_id(conn, session_id)
    audit(conn, action="review.view", actor_type="dokter", actor_id=p.doctor_id, client_id=p.client_id,
          session_id=session_id, ip=p.ip)
    return {"session": {"id": session_id, "status": s["status"], "no_rawat": s["no_rawat"], **_session_meta(conn, p, s)},
            "transcript": {"segments": segs, "is_empty": bool(tr and tr[1])}, "items": items,
            "missed": missed, "codes": codes, "soap": _soap_payload(conn, sid) if sid else None, "notices": notices,
            "job_errors": errs}


class SentenceIn(BaseModel):
    id: str | None = None
    section: str = Field(pattern="^[SOAP]$")
    text: str = Field(min_length=1, max_length=4000)


class SoapIn(BaseModel):
    sentences: list[SentenceIn]


@router.put("/sessions/{session_id}/soap")
def save_soap(session_id: str, body: SoapIn, p: Principal = Depends(require_doctor), conn=Depends(get_conn)):
    s = load_session(conn, p, session_id)
    if s["status"] not in EDITABLE:
        raise HTTPException(409, "session_not_editable")
    prev_id = _latest_soap_id(conn, session_id)
    prev = {}
    if prev_id:
        for r in conn.execute(text(
                "SELECT id, section, text, evidence_item_ids, is_ai_suspicion, flagged, origin, ai_text "
                "FROM soap_sentences WHERE soap_id=:i"), dict(i=prev_id)).all():
            prev[str(r[0])] = r
    ver = conn.execute(text("SELECT COALESCE(MAX(version),0)+1 FROM soap_notes WHERE session_id=:s"), dict(s=session_id)).scalar()
    nid = conn.execute(text(
        "INSERT INTO soap_notes(client_id, session_id, version, source, created_by) VALUES (:c,:s,:v,'dokter',:d) RETURNING id"),
        dict(c=p.client_id, s=session_id, v=ver, d=p.doctor_id)).scalar()
    stats = {"unchanged": 0, "edited": 0, "new": 0, "deleted": 0}
    kept: set[str] = set()
    by_section = {k: [] for k in "SOAP"}
    for sent in body.sentences:
        t = sent.text.strip()
        if not t:
            continue
        by_section[sent.section].append((sent, t))
    for sec in "SOAP":
        real = [(s_, t) for s_, t in by_section[sec] if t != EMPTY_TEXT]
        rows = real or [(SentenceIn(section=sec, text=EMPTY_TEXT), EMPTY_TEXT)]
        for n, (sent, t) in enumerate(rows):
            old = prev.get(sent.id) if sent.id else None
            if old and old[1] == sec:
                kept.add(sent.id)
                same = old[2] == t
                origin = old[6] if same else "dokter_edit"
                ai_text = old[7] if old[7] is not None else (old[2] if old[6] == "ai" else None)
                ev, sus, flagged = list(old[3]), old[4], (old[5] if same else False)
                stats["unchanged" if same else "edited"] += 1
            else:
                origin, ai_text, ev, sus, flagged = "dokter_baru", None, [], False, False
                if t != EMPTY_TEXT:
                    stats["new"] += 1
            conn.execute(text(
                "INSERT INTO soap_sentences(soap_id, section, idx, text, evidence_item_ids, is_ai_suspicion, flagged, "
                "origin, ai_text) VALUES (:so,:sec,:i,:t,CAST(:ev AS uuid[]),:sus,:fl,:o,:ai)"),
                dict(so=nid, sec=sec, i=n, t=t, ev="{" + ",".join(str(x) for x in ev) + "}", sus=sus, fl=flagged,
                     o=origin, ai=ai_text))
    stats["deleted"] = sum(1 for k, r in prev.items() if k not in kept and r[2] != EMPTY_TEXT)
    audit(conn, action="soap.edit", actor_type="dokter", actor_id=p.doctor_id, client_id=p.client_id,
          session_id=session_id, entity="soap_notes", entity_id=nid, before={"version": ver - 1},
          after={"version": ver, **stats}, ip=p.ip)
    return _soap_payload(conn, nid)


class ApproveIn(BaseModel):
    soap_id: str
    acknowledge_flagged: bool = False


@router.post("/sessions/{session_id}/approve")
def approve(session_id: str, body: ApproveIn, bg: BackgroundTasks, p: Principal = Depends(require_doctor),
            conn=Depends(get_conn)):
    s = load_session(conn, p, session_id)
    if s["status"] not in EDITABLE:
        raise HTTPException(409, "session_not_approvable")
    latest = _latest_soap_id(conn, session_id)
    if not latest or str(latest) != body.soap_id:
        raise HTTPException(409, "not_latest_version")
    src = conn.execute(text("SELECT source FROM soap_notes WHERE id=:i"), dict(i=latest)).scalar()
    if src != "dokter":
        raise HTTPException(409, "doctor_version_required")     # dokter harus menyimpan/menyunting dulu
    real = conn.execute(text("SELECT count(*) FROM soap_sentences WHERE soap_id=:i AND text<>:e"),
                        dict(i=latest, e=EMPTY_TEXT)).scalar()
    if not real:
        raise HTTPException(409, "soap_kosong")                 # jangan kirim catatan tanpa isi ke SIMRS
    flagged = conn.execute(text("SELECT count(*) FROM soap_sentences WHERE soap_id=:i AND flagged"), dict(i=latest)).scalar()
    if flagged and not body.acknowledge_flagged:
        raise HTTPException(409, "flagged_not_acknowledged")
    conn.execute(text("UPDATE soap_notes SET approved_by=:d, approved_at=now() WHERE id=:i"), dict(d=p.doctor_id, i=latest))
    conn.execute(text("UPDATE consult_sessions SET status='approved' WHERE id=:s"), dict(s=session_id))
    audit(conn, action="soap.approve", actor_type="dokter", actor_id=p.doctor_id, client_id=p.client_id,
          session_id=session_id, entity="soap_notes", entity_id=latest,
          after={"flagged_acknowledged": int(flagged)}, ip=p.ip)
    _later(bg, session_id, "session.approved")
    return {"status": "approved", "soap_id": str(latest)}


class CodeIn(BaseModel):
    code: str | None = None


@router.put("/sessions/{session_id}/codes/{suggestion_id}")
def set_code(session_id: str, suggestion_id: str, body: CodeIn, p: Principal = Depends(require_doctor),
             conn=Depends(get_conn)):
    """Dokter memilih/mengganti/menghapus kode. Kode WAJIB ada di tabel resmi."""
    s = load_session(conn, p, session_id)
    if s["status"] not in EDITABLE:
        raise HTTPException(409, "session_not_editable")
    try:
        uuid.UUID(suggestion_id)
    except ValueError:
        raise HTTPException(404, "suggestion_not_found") from None
    row = conn.execute(text("SELECT system, final_code FROM code_suggestions WHERE id=:i AND session_id=:s"),
                       dict(i=suggestion_id, s=session_id)).first()
    if not row:
        raise HTTPException(404, "suggestion_not_found")
    if body.code is None:
        conn.execute(text("UPDATE code_suggestions SET final_code=NULL, state='kosong', decided_by=:d, decided_at=now() WHERE id=:i"),
                     dict(d=p.doctor_id, i=suggestion_id))
    else:
        if not term.code_exists(conn, row[0], body.code.strip()):
            raise HTTPException(422, "code_not_in_terminology")
        conn.execute(text("UPDATE code_suggestions SET final_code=:c, state='dipilih_dokter', decided_by=:d, decided_at=now() WHERE id=:i"),
                     dict(c=body.code.strip(), d=p.doctor_id, i=suggestion_id))
    audit(conn, action="code.set", actor_type="dokter", actor_id=p.doctor_id, client_id=p.client_id, session_id=session_id,
          entity="code_suggestions", entity_id=suggestion_id, before={"code": row[1]}, after={"code": body.code}, ip=p.ip)
    return next(c for c in _codes_payload(conn, session_id) if c["id"] == suggestion_id)


@router.get("/terminology/{system}/search")
def search_terminology(system: str, q: str, limit: int = 10, p: Principal = Depends(get_principal), conn=Depends(get_conn)):
    """Pencarian kode untuk dokter (trigram + full-text; tanpa LLM)."""
    system = system.upper()
    if system not in ("ICD10", "KFA", "LOINC", "ICD9CM") or len(q.strip()) < 2:
        raise HTTPException(422, "invalid_query")
    res = term.retrieve(conn, system, [q.strip()], min(max(limit, 1), 25), use_vectors=False)
    return [{"code": r["code"], "display": r["display"]} for r in res]


@router.post("/sessions/{session_id}/submit")
def submit(session_id: str, bg: BackgroundTasks, p: Principal = Depends(get_principal), conn=Depends(get_conn)):
    s = load_session(conn, p, session_id)
    done = conn.execute(text("SELECT id FROM simrs_submissions WHERE session_id=:s AND status='succeeded'"), dict(s=session_id)).first()
    if done:
        return {"status": "submitted", "submission_id": str(done[0]), "idempotent": True}
    if s["status"] != "approved":
        raise HTTPException(409, "not_approved")
    soap_id = conn.execute(text("SELECT id FROM soap_notes WHERE session_id=:s AND approved_at IS NOT NULL "
                                "ORDER BY version DESC LIMIT 1"), dict(s=session_id)).scalar()
    if not soap_id:
        raise HTTPException(409, "not_approved")
    doctor_simrs = conn.execute(text("SELECT simrs_user_id FROM doctors WHERE id=:d"), dict(d=s["doctor_id"])).scalar()
    sentences = _soap_payload(conn, soap_id)["sentences"]
    payload = {k: [x["text"] for x in sentences if x["section"] == k] for k in "SOAP"}
    payload["codes"] = [{"system": c["system"], "code": c["final_code"], "display": c["final_display"]}
                        for c in _codes_payload(conn, session_id) if c["final_code"]]
    adapter = get_adapter(p.simrs_adapter)
    try:
        res = adapter.submit_soap(no_rawat=s["no_rawat"], doctor_simrs_id=doctor_simrs, soap=payload,
                                  idempotency_key=str(soap_id))
    except Exception as e:  # noqa: BLE001
        from .adapters.base import SubmitResult
        res = SubmitResult(False, None, type(e).__name__)
    sub = conn.execute(text(
        "INSERT INTO simrs_submissions(client_id, session_id, soap_id, adapter, status, response_code, error_code) "
        "VALUES (:c,:s,:so,:a,:st,:rc,:ec) RETURNING id"),
        dict(c=p.client_id, s=session_id, so=soap_id, a=adapter.name, st="succeeded" if res.ok else "failed",
             rc=res.http_status, ec=res.error_code)).scalar()
    audit(conn, action="simrs.submit", actor_type="dokter" if p.kind == "doctor" else "api_client",
          actor_id=p.doctor_id or p.client_id, client_id=p.client_id, session_id=session_id,
          entity="simrs_submissions", entity_id=sub, after={"ok": res.ok, "error_code": res.error_code}, ip=p.ip)
    if res.ok:
        conn.execute(text("UPDATE consult_sessions SET status='submitted' WHERE id=:s"), dict(s=session_id))
        _later(bg, session_id, "session.submitted")
        return {"status": "submitted", "submission_id": str(sub)}
    return JSONResponse({"detail": "simrs_submit_failed", "error_code": res.error_code}, status_code=502)


@router.get("/sessions/{session_id}/audit")
def get_audit(session_id: str, p: Principal = Depends(get_principal), conn=Depends(get_conn)):
    load_session(conn, p, session_id)
    rows = conn.execute(text("SELECT ts, actor_type, actor_id, action, entity, entity_id, after FROM audit_log "
                             "WHERE session_id=:s ORDER BY id"), dict(s=session_id)).all()
    return [{"ts": r[0].isoformat(), "actor_type": r[1], "actor_id": r[2], "action": r[3], "entity": r[4],
             "entity_id": r[5], "after": r[6]} for r in rows]


@router.get("/health")
def health():
    from sqlalchemy import text as t

    from .db import engine
    try:
        with engine().connect() as c:
            c.execute(t("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception:
        return {"status": "degraded", "db": "error"}


@router.post("/sessions/{session_id}/widget-token")
def widget_token(session_id: str, p: Principal = Depends(get_principal), conn=Depends(get_conn)):
    """Dipanggil SERVER client (API key) untuk menyematkan widget: token singkat yang hanya berlaku untuk satu sesi
    dan bertindak sebagai dokter pemilik sesi. API key tidak pernah dikirim ke browser."""
    if p.kind != "api_key":
        raise HTTPException(403, "api_key_required")
    s = load_session(conn, p, session_id)
    ttl = 3600
    tok = security.make_token(str(s["doctor_id"]), p.client_id, session_id=str(session_id), ttl_s=ttl)
    audit(conn, action="widget.token_issued", actor_type="api_client", actor_id=p.client_id, client_id=p.client_id,
          session_id=session_id, ip=p.ip)
    return {"token": tok, "expires_in": ttl, "ui_path": f"/ui/?embed=1#session={session_id}&token={tok}"}


@router.post("/sessions/{session_id}/warmup", status_code=202)
def warmup_session(session_id: str, bg: BackgroundTasks, p: Principal = Depends(get_principal), conn=Depends(get_conn)):
    """Dipanggil saat layar rekam dibuka: siapkan model STT (dan, bila GPU digilir, kosongkan VRAM dari LLM)."""
    s = load_session(conn, p, session_id)
    if s["status"] != "recording":
        raise HTTPException(409, "session_not_recording")
    from . import llm, stt_client
    if get_settings().gpu_timeshare:
        bg.add_task(llm.unload_llm)
    bg.add_task(stt_client.warmup)
    return {"status": "warming"}


@router.post("/sessions/{session_id}/live")
async def live_chunk(session_id: str, chunk: UploadFile = File(...), accurate: str = Form(""), partial: str = Form(""),
                     p: Principal = Depends(get_principal), conn=Depends(get_conn)):
    """Pratinjau transkrip langsung: potongan audio mandiri -> teks. HANYA tampilan: tidak disimpan,
    tidak dipakai untuk SOAP (SOAP dibuat dari rekaman penuh setelah Selesai)."""
    s = load_session(conn, p, session_id)
    if s["status"] != "recording":
        raise HTTPException(409, "session_not_recording")
    ext = os.path.splitext(chunk.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, "unsupported_audio_type")
    data = await chunk.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "chunk_too_large")
    d = Path(get_settings().audio_dir) / ("live-" + uuid.uuid4().hex)
    d.mkdir(parents=True, exist_ok=True)
    f = d / ("c" + ext)
    try:
        f.write_bytes(data)
        from . import stt_client, vocab
        try:
            res = await asyncio.to_thread(      # jangan memblokir event loop selama STT berjalan
                stt_client.transcribe, f.as_posix(), vocab.initial_prompt() if accurate else "",
                "partial" if partial else ("refine" if accurate else True))
        except stt_client.STTError:
            raise HTTPException(502, "stt_unavailable") from None
        segs = [{"start_ms": x["start_ms"], "end_ms": x["end_ms"], "text": x["text"]} for x in res.get("segments", [])]
        return {"text": " ".join(x["text"] for x in segs).strip(), "segments": segs}
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
