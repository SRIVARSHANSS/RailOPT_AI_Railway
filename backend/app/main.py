"""RailOpt AI API (thin layer for the first UI slice).

Run from the backend folder:
    uvicorn app.main:app --reload
Interactive docs: http://127.0.0.1:8000/docs

A decision-support and simulation prototype: every response is labelled
SIMULATED. It advises a human controller and controls nothing.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="RailOpt AI (SIMULATED)",
    version="0.1.0",
    description="Decision-support and simulation prototype for a human railway traffic controller. "
                "All data and results are SIMULATED on a sample corridor. It does not control trains or signals.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "data_label": "SIMULATED"})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors, "data_label": "SIMULATED"})
