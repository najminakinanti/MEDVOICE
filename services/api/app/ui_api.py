"""Endpoint pendukung UI dokter: profil, antrean, riwayat sesi. Hanya membaca; tidak mengubah alur klinis."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from .adapters import get_adapter
from .db import get_conn
from .deps import Principal, require_doctor

router = APIRouter(prefix="/v1")
DONE = ("approved", "submitted")
ACTIVE = ("recording", "processing", "review", "failed")


def patient_of(adapter, no_rawat: str) -> dict | None:
    fn = getattr(adapter, "patient_info", None)
    try:
        return fn(no_rawat) if fn else None
    except Exception:  # noqa: BLE001 - SIMRS gangguan: UI tetap jalan tanpa nama pasien
        return None


@router.get("/me")
def me(p: Principal = Depends(require_doctor), conn=Depends(get_conn)):
    row = conn.execute(text("SELECT d.display_name, d.username, c.name FROM doctors d JOIN clients c ON c.id=d.client_id "
                            "WHERE d.id=:d"), dict(d=p.doctor_id)).first()
    if not row:
        raise HTTPException(404, "doctor_not_found")
    return {"display_name": row[0], "username": row[1], "client": row[2], "scoped": bool(p.session_scope)}


@router.get("/queue")
def queue(p: Principal = Depends(require_doctor), conn=Depends(get_conn)):
    """Antrean pasien hari ini dari SIMRS (bila adapter mendukung) + status sesi MedVoice per pasien."""
    adapter = get_adapter(p.simrs_adapter)
    fn = getattr(adapter, "list_queue", None)
    try:
        q = fn(p.doctor_simrs_id) if fn else None
    except Exception:  # noqa: BLE001
        q = None
    last = {}
    for r in conn.execute(text(
            "SELECT DISTINCT ON (no_rawat) no_rawat, id, status FROM consult_sessions WHERE doctor_id=:d "
            "ORDER BY no_rawat, created_at DESC"), dict(d=p.doctor_id)).all():
        last[r[0]] = {"id": str(r[1]), "status": r[2]}
    items = []
    for it in (q or {}).get("items", []):
        ses = last.get(it["no_rawat"])
        state = it.get("state", "menunggu")
        if ses and ses["status"] in DONE:
            state = "selesai"
        elif ses and ses["status"] in ACTIVE:
            state = "diperiksa"
        items.append({**it, "state": state, "session": ses})
    s = conn.execute(text(
        "SELECT count(*) FILTER (WHERE created_at::date = current_date), "
        "count(*) FILTER (WHERE created_at::date = current_date AND status IN ('approved','submitted')), "
        "count(*) FILTER (WHERE status='review') FROM consult_sessions WHERE doctor_id=:d"), dict(d=p.doctor_id)).first()
    avg = conn.execute(text(
        "SELECT avg(extract(epoch FROM (n.approved_at - s.finished_at))) FROM consult_sessions s "
        "JOIN soap_notes n ON n.session_id=s.id AND n.approved_at IS NOT NULL "
        "WHERE s.doctor_id=:d AND s.finished_at IS NOT NULL AND s.created_at > now() - interval '7 days'"),
        dict(d=p.doctor_id)).scalar()
    return {"supported": q is not None, "unit": (q or {}).get("unit"), "date": date.today().isoformat(), "items": items,
            "stats": {"today": len(items) if q is not None else s[0], "done": s[1], "review": s[2],
                      "avg_doc_seconds": round(avg) if avg is not None else None}}


@router.get("/sessions")
def list_sessions(q: str = "", status: str = "", limit: int = 8, offset: int = 0,
                  p: Principal = Depends(require_doctor), conn=Depends(get_conn)):
    """Riwayat sesi milik dokter ini (terbaru dulu). `q` mencocokkan no. rawat atau nama pasien dari SIMRS."""
    limit = min(max(limit, 1), 50)
    adapter = get_adapter(p.simrs_adapter)
    where, params = ["s.doctor_id=:d"], dict(d=p.doctor_id)
    if status:
        if status not in ("recording", "processing", "review", "approved", "submitted", "failed", "cancelled"):
            raise HTTPException(422, "invalid_status")
        where.append("s.status = CAST(:st AS session_status)")
        params["st"] = status
    rows = conn.execute(text(
        "SELECT s.id, s.no_rawat, s.status, s.created_at, s.started_at, s.finished_at, "
        "(SELECT string_agg(DISTINCT coalesce(c.final_code, c.suggested_code), ', ') FROM code_suggestions c "
        " WHERE c.session_id=s.id AND c.system='ICD10' AND coalesce(c.final_code, c.suggested_code) IS NOT NULL) "
        "FROM consult_sessions s WHERE " + " AND ".join(where) + " ORDER BY s.created_at DESC"), params).all()
    out = []
    needle = q.strip().lower()
    for r in rows:
        pat = patient_of(adapter, r[1])
        if needle and needle not in r[1].lower() and not (pat and needle in (pat["name"] + " " + pat["rm"]).lower()):
            continue
        dur = (r[5] - r[4]).total_seconds() if r[5] and r[4] else None
        out.append({"id": str(r[0]), "no_rawat": r[1], "status": r[2], "created_at": r[3].isoformat(),
                    "duration_s": round(dur) if dur is not None else None, "icd10": r[6], "patient": pat})
    return {"total": len(out), "items": out[offset:offset + limit]}
