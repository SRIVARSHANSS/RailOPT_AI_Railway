"""RailOpt AI API.

Run from the backend folder:
    python -m alembic upgrade head      (once, and after every new migration)
    uvicorn app.main:app                 (dev: --reload)
Interactive docs: http://127.0.0.1:8000/docs

A decision-support and simulation prototype: every response carries its data label (SIMULATED,
REAL or HYPOTHETICAL on a real recorded day). It advises a human controller and controls nothing.
Every route except /api/health and /api/auth/login|refresh needs a signed-in user (Phase 8).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.admin_routes import router as admin_router
from app.api.alerts_routes import router as alerts_router
from app.api.report_routes import router as report_router
from app.api.auth_routes import router as auth_router
from app.api.routes import router

logging.basicConfig(level=logging.INFO)
FRONTEND_ORIGIN = "http://localhost:5173"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # first admin from RAILOPT_ADMIN_EMAIL / RAILOPT_ADMIN_PASSWORD, only if set (and no admin exists)
    from app.cli import admin_from_env
    admin_from_env()
    yield


app = FastAPI(
    title="RailOpt AI",
    version="0.2.0",
    description="Decision-support and simulation prototype for a human railway traffic controller. "
                "Data is SIMULATED (sample corridor) or a REAL recorded day replayed (with HYPOTHETICAL events "
                "on top), as labelled in every response. It does not control trains or signals.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],           # exact origin: cookies are sent with credentials
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition"],     # report downloads keep the file name the API gives
)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(router)
app.include_router(alerts_router)
app.include_router(report_router)


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "data_label": "SIMULATED"},
                        headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors, "data_label": "SIMULATED"})
