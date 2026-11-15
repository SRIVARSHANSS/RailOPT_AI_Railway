# RailOpt AI

AI-powered predictive railway traffic conflict resolution and throughput
optimization platform. Final-year CSE project, PSNA College of Engineering &
Technology (batch 27D08), based on SIH25022.

RailOpt AI is a **software-only decision-support and simulation prototype**.
It advises a human traffic controller. It does not control trains or signals
and is not connected to Indian Railways systems. All results are simulated.

## Status

- [x] Phase 0: scope and assumptions (`docs/ASSUMPTIONS.md`)
- [x] Phase 1: network model + event-driven simulator
- [x] Phase 2: full-day timetable, random variability, synthetic training-data generator
- [x] Phase 3: rule-based conflict detector (predicts conflicts from planned times)
- [x] Phase 4: delay and conflict models with baselines, SHAP explanations
  (results: `backend/ml/reports/model_card.md`, all on SIMULATED data)
- [x] Phase 5: CP-SAT re-planning (hold, reroute, resequence, combined) vs no-re-planning and
  priority-dispatch baselines; every plan is replayed through the simulator
- [x] Thin FastAPI layer for the T101 demo (in-memory scenario; Postgres + auth in Phase 8)
- [x] Phase 9 part 1: design system "Midnight Signal", app shell, cinematic login (`frontend/`)
- [x] Phase 9 part 2: Traffic Console (live corridor map), Disruption Panel, Strategy Comparison
  - step-by-step demo with talking points: `docs/DEMO.md`
  - Timeline: time-distance (Marey) chart, planned vs actual and before vs after the accepted plan (D3)
- [x] Phase 6: what-if studio (HYPOTHETICAL copy) and re-optimization on top of an accepted plan
- [x] Phase 10: evaluation on 200 SIMULATED scenarios: no re-planning, priority dispatch, RailOpt
  single-shot, dynamic, and dynamic + ML risk buffers; deterministic and robustness replays,
  bootstrap CIs and paired tests (`backend/eval/reports/eval_report.md`, generated from the JSON)
  - Phase 10b: pre-registered ML integration variants (bigger and probability-scaled buffers,
    ML-triggered early re-planning), reported under "ML integration variants"
- [x] Analytics and Model Insights pages: the stored evaluation and ML metrics through `GET /api/evaluation`
  and `GET /api/model`, hash-checked ("Outdated - rerun" when the result files or models changed)
- [~] REAL data, Dindigul -> Madurai (kept apart from SIMULATED, labelled REAL): Step 1 done:
  corridor (8 stations, 7 single-track sections in this direction), 44 regular trains from the
  RSTGCN Sept 2024 dataset (CC BY-SA 4.0), recorded running times and an audit
  (`backend/data/real/dg_mdu/audit.md`). Sources and licence: `docs/DATA_SOURCES.md`
  - Step 2: delay at Madurai predicted from what is known at Dindigul, validated on the last
    week of recorded runs against carry-the-DG-delay and linear baselines
    (`backend/ml/reports/real/model_card_real.md`, pre-registered, all results reported)
  - Step 3: real-day replay (`POST /api/scenario/reset {"timetable": "dg_mdu", "mode": "replay",
    "date": "2024-09-12"}`): trains move by their recorded times (interpolated between recorded
    stations), hypothetical events and decisions on top are labelled "HYPOTHETICAL on a real recorded
    day"; loops per station (ASSUMED), headway calibrated on the recordings, HOLD / RESEQUENCE only
- The API starts on the REAL recorded demo day (Dindigul -> Madurai, 2024-09-12); set
  `RAILOPT_BOOT=simulated` to start on the SIMULATED sample corridor.
- 116 passing tests. Remaining phases: see `CLAUDE.md`

## Setup (Windows)

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```powershell
cd backend
python -m pytest -q                         # run all tests
python -m app.services.simulator.run_demo   # T101 scenario, before and after
python -m app.services.conflicts.run_demo   # predicted conflicts + knock-on delays
python -m app.services.optimizer.run_demo   # strategy comparison for the T101 scenario
uvicorn app.main:app                        # API on http://127.0.0.1:8000, docs at /docs (demos: no --reload)
python -m app.services.datagen.generate --runs 3000 --seed 42   # SIMULATED training rows -> data/generated/
python -m ml.train                          # models -> ml/models/, reports -> ml/reports/ (~3 min)
python -m eval.run_eval --scenarios 200 --seed 2026   # Phase 10 evaluation -> eval/reports/
```

Frontend (second terminal):

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173 - needs the API on port 8000
```

### Dependency audit (frontend)

`npm audit` (after the non-force `npm audit fix`) still lists 9 moderate advisories:

- **react-router / react-router-dom 6.30.6** (runtime): open redirect via a backslash path in
  `<Link>` / `useNavigate`, and an SSR hydration issue. Both are fixed only in React Router v7;
  the upgrade is deferred. Exposure here is low: the app only navigates to its own fixed internal
  routes (no user- or URL-supplied redirect targets) and does no server-side rendering.
- **typescript-eslint 8.72.2 and its minimatch** (dev only, linting): no fixed release published yet.

## Layout

```
backend/
  app/services/network/     stations, sections, trains, timetable, graph
  app/services/simulator/   event-driven simulator + safety checks
  app/services/conflicts/   rule-based conflict detector + cascade estimate
  app/services/datagen/     synthetic training-data generator (simulated)
  app/services/predictor/   loads the models; predict(features) with top SHAP drivers
  app/services/optimizer/   CP-SAT strategies + baselines, scored by simulator replay
  app/services/live.py      train states, conflicts + ML, recommendation, timeline (plain Python)
  app/api/, app/schemas/    FastAPI routes and Pydantic models; app/main.py; app/core/store.py
  ml/                       split, preprocessing, training, SHAP; reports/ holds metrics + model card
  data/                     corridor CSVs (reference + full-day timetable), T101 event file
  tests/                    pytest suite
docs/ASSUMPTIONS.md         corridor, timetable and modelling assumptions
```

## API (first UI slice)

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/api/health` | liveness |
| GET | `/api/network?timetable=reference\|full_day` | stations, sections, trains, schedule |
| POST | `/api/scenario/reset` | start a fresh scenario on a timetable |
| GET | `/api/scenario` | posted events, accepted plan, decision log |
| POST | `/api/events` | add a validated STOPPAGE / DELAY / TRACK_UNAVAILABLE event |
| GET | `/api/state?at=HH:MM` | every train's status, location, progress, delay + KPIs |
| GET | `/api/conflicts?at=HH:MM` | detector conflicts + ML probability and top drivers, ML watchlist |
| POST | `/api/optimize` | strategy comparison (replayed) + recommendation with explanation |
| POST | `/api/recommendation/{id}/decision` | accept (applies holds / reroutes) or reject; both logged |
| GET | `/api/evaluation` | stored Phase 10/10b evaluation (eval/reports), hash-checked; status ok / outdated / missing |
| GET | `/api/model` | stored ML metrics + SHAP importance (ml/reports), hash-checked against the model files |
| GET | `/api/timeline` | planned, actual and before-plan trips (stops, waits, delays) + closures for the time-distance chart |
| POST | `/api/whatif` | HYPOTHETICAL: 1-3 events on a copy of the scenario, compared with the current one |

Detection, prediction and re-planning only see events known at `at`. A
stoppage or delay is known once it starts; planned closures are known as soon
as they are posted. All responses are labelled `"data_label": "SIMULATED"`.
