"""Reports page (page 11): scenario report (PDF + CSV), evaluation report (PDF), model report
(PDF), audit log export (CSV, ADMIN only; in admin_routes.py).

Scenario report: every role (READ). Evaluation and model reports: ANALYST and ADMIN (REPORTS).
Every export is logged as REPORT_EXPORTED. A stale evaluation or model card refuses with 409
"... outdated - rerun ..." (the same checks as the Analytics and Model Insights pages).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.routes import AtQuery, get_predictor_or_none
from app.core.auth import READ, REPORTS, audit, require
from app.core.store import ScenarioStore, get_store
from app.db.session import get_db
from app.services import results
from app.services.reports import results_pdf
from app.services.reports.scenario import scenario_csv, scenario_data, scenario_pdf

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _file(body: bytes | str, media: str, name: str) -> Response:
    return Response(content=body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _logged(db, user, request, kind: str, **detail):
    audit(db, "REPORT_EXPORTED", user=user, request=request, detail={"report": kind, **detail})


@router.get("")
def report_status(store: ScenarioStore = Depends(get_store), _user=Depends(require(*READ))):
    """What can be exported now (the page shows a refusal before anyone clicks)."""
    ev = results.evaluation_view(eval_dir=results.EVAL_DIR)
    md = results_pdf.cards_status()
    return {"data_label": store.label(), "scenario_version": store.version,
            "evaluation": {"status": ev["status"], "reasons": ev["reasons"], "command": ev["command"]},
            "model": {"status": md["status"], "reasons": md["reasons"], "command": md["command"]}}


def _name(store: ScenarioStore, at: str, ext: str) -> str:
    return f"railopt_scenario_{store.version}_{at.replace(':', '')}.{ext}"


@router.get("/scenario.pdf")
def scenario_report_pdf(request: Request, at: str = AtQuery, store: ScenarioStore = Depends(get_store),
                        db: Session = Depends(get_db), predictor=Depends(get_predictor_or_none),
                        user=Depends(require(*READ))):
    data = scenario_data(store, at, user, predictor)
    body = scenario_pdf(data)
    _logged(db, user, request, "scenario.pdf", at=at, version=store.version)
    return _file(body, "application/pdf", _name(store, at, "pdf"))


@router.get("/scenario.csv")
def scenario_report_csv(request: Request, at: str = AtQuery, store: ScenarioStore = Depends(get_store),
                        db: Session = Depends(get_db), predictor=Depends(get_predictor_or_none),
                        user=Depends(require(*READ))):
    data = scenario_data(store, at, user, predictor)
    _logged(db, user, request, "scenario.csv", at=at, version=store.version)
    return _file(scenario_csv(data), "text/csv; charset=utf-8", _name(store, at, "csv"))


def _refuse(exc: results_pdf.Outdated):
    raise HTTPException(status_code=409, detail={"message": str(exc), "status": exc.status,
                                                 "reasons": exc.reasons, "command": exc.command})


@router.get("/evaluation.pdf")
def evaluation_report(request: Request, db: Session = Depends(get_db), user=Depends(require(*REPORTS))):
    try:
        body = results_pdf.evaluation_pdf(results.evaluation_view(eval_dir=results.EVAL_DIR), user)
    except results_pdf.Outdated as exc:
        _refuse(exc)
    _logged(db, user, request, "evaluation.pdf")
    return _file(body, "application/pdf", "railopt_evaluation_report.pdf")


@router.get("/model.pdf")
def model_report(request: Request, db: Session = Depends(get_db), user=Depends(require(*REPORTS))):
    try:
        body = results_pdf.model_pdf(results_pdf.cards_status(), user)
    except results_pdf.Outdated as exc:
        _refuse(exc)
    _logged(db, user, request, "model.pdf")
    return _file(body, "application/pdf", "railopt_model_report.pdf")
