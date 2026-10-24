from celery import Celery

from .config import get_settings

_s = get_settings()
celery = Celery("medvoice", broker=_s.redis_url or "memory://", backend=None)
celery.conf.update(
    task_always_eager=_s.celery_eager,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={"purge-expired": {"task": "medvoice.purge", "schedule": 3600.0}},
)


@celery.task(name="medvoice.run_pipeline")
def run_pipeline_task(session_id: str) -> None:
    from .soap_pipeline import run_pipeline
    run_pipeline(session_id)


@celery.task(name="medvoice.purge")
def purge_task() -> dict:
    from .soap_pipeline import purge_expired
    return purge_expired()


@celery.task(name="medvoice.webhook", bind=True, max_retries=5)
def webhook_task(self, session_id: str, event: str) -> None:
    """Kirim webhook bertanda tangan ke client. Payload tanpa data klinis: hanya id & status."""
    import json
    import time

    import httpx
    from sqlalchemy import text

    from . import security
    from .audit import audit
    from .db import engine
    with engine().begin() as c:
        row = c.execute(text(
            "SELECT s.client_id, s.status, cl.webhook_url FROM consult_sessions s JOIN clients cl ON cl.id=s.client_id "
            "WHERE s.id=:i"), dict(i=session_id)).first()
        jobs = c.execute(text("SELECT kind, status FROM jobs WHERE session_id=:i ORDER BY created_at, kind"),
                         dict(i=session_id)).all()
    if not row or not row[2]:
        return
    cid, status, url = str(row[0]), row[1], row[2]
    body = json.dumps({"event": event, "session_id": session_id, "status": status,
                       "jobs": {k: v for k, v in jobs}}, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    headers = {"Content-Type": "application/json", "X-MedVoice-Event": event, "X-MedVoice-Timestamp": ts,
               "X-MedVoice-Signature": security.sign_webhook(cid, ts, body)}
    try:
        r = httpx.post(url, content=body, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        with engine().begin() as c:
            audit(c, action="webhook.failed", actor_type="system", client_id=cid, session_id=session_id,
                  after={"event": event, "error": type(e).__name__, "attempt": self.request.retries + 1})
        if self.request.retries >= self.max_retries:
            return
        raise self.retry(countdown=min(10 * 2 ** self.request.retries, 600)) from None
    with engine().begin() as c:
        audit(c, action="webhook.sent", actor_type="system", client_id=cid, session_id=session_id, after={"event": event})
