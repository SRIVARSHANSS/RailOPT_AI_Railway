"""Conflicts and Alerts page (page 5): full alert lists, alert history, acknowledge.

CONTROLLER and ANALYST read it (ADMIN is kept off the page; the console feed still shows
alerts); only a CONTROLLER acknowledges. An acknowledgement is an ALERT_ACKNOWLEDGED row in
audit_log (user, time, scenario run, alert key, sim clock): the page reads the acknowledged
state back from those rows, so it survives an API restart without its own table.
"""
from __future__ import annotations

import threading
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import AtQuery, _clock, _estimated, _ml_off, get_predictor_or_none
from app.core.auth import ALERTS, CONTROL, audit, require
from app.core.store import ScenarioStore, get_store
from app.db import models as m
from app.db.session import get_db
from app.schemas.api import HHMM
from app.services import alerts

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

ACK_ACTION = "ALERT_ACKNOWLEDGED"
_cache: OrderedDict = OrderedDict()
_cache_lock = threading.Lock()


def acknowledged(db: Session, run_ref: str) -> dict[str, dict]:
    """{alert key: who acknowledged it and when} for this scenario run (first acknowledgement)."""
    out: dict[str, dict] = {}
    rows = db.scalars(select(m.AuditLog).where(m.AuditLog.action == ACK_ACTION).order_by(m.AuditLog.id))
    for r in rows:
        d = r.detail or {}
        if d.get("scenario") == run_ref and d.get("key") not in out:
            out[d["key"]] = {"by": r.email, "at_utc": r.at.isoformat(timespec="seconds"), "sim_at": d.get("at")}
    return out


def compute(store: ScenarioStore, t: int, predictor) -> dict:
    """alerts_view without acknowledgements, cached per scenario run, version and clock."""
    off = _ml_off(store)
    key = (store.run_ref, store.version, t, off is None and predictor is not None)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    view = alerts.alerts_view(store, t, None if off else predictor, off, _estimated(store))
    with _cache_lock:
        _cache[key] = view
        while len(_cache) > 32:
            _cache.popitem(last=False)
    return view


def _with_acks(view: dict, acks: dict) -> dict:
    cur = [{**r, "acknowledged": acks.get(r["key"])} for r in view["current"]]
    hist = [{**e, "acknowledged": acks.get(e["key"])} for e in view["history"]]
    return {**view, "current": cur, "history": hist}


@router.get("")
def get_alerts(at: str = AtQuery, store: ScenarioStore = Depends(get_store), db: Session = Depends(get_db),
               predictor=Depends(get_predictor_or_none), _user=Depends(require(*ALERTS))):
    t = _clock(at)
    view = compute(store, t, predictor)
    return {"data_label": store.label(), "scenario_version": store.version, "at": at,
            **_with_acks(view, acknowledged(db, store.run_ref))}


class AckRequest(BaseModel):
    key: str = Field(min_length=3, max_length=200)
    at: str = Field(pattern=HHMM, examples=["10:05"])


@router.post("/ack")
def ack(req: AckRequest, request: Request, store: ScenarioStore = Depends(get_store),
        db: Session = Depends(get_db), predictor=Depends(get_predictor_or_none), user=Depends(require(*CONTROL))):
    t = _clock(req.at)
    view = compute(store, t, predictor)
    if req.key not in {r["key"] for r in view["current"]} | {e["key"] for e in view["history"]}:
        raise HTTPException(status_code=404, detail=f"no alert {req.key} in this scenario up to {req.at}")
    acks = acknowledged(db, store.run_ref)
    if req.key not in acks:
        audit(db, ACK_ACTION, user=user, request=request,
              detail={"scenario": store.run_ref, "version": store.version, "key": req.key, "at": req.at})
        acks = acknowledged(db, store.run_ref)
    return {"key": req.key, "acknowledged": acks[req.key]}
