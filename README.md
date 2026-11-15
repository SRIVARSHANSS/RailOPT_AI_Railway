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
- [x] Phase 6: what-if studio (HYPOTHETICAL copy) and re-optimization on top of an accepted plan
- 74 passing tests. Remaining phases: see `CLAUDE.md`

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
```

Frontend (second terminal):

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173 - needs the API on port 8000
```

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
| GET | `/api/timeline` | planned and actual occupancies for a time-distance chart |
| POST | `/api/whatif` | HYPOTHETICAL: 1-3 events on a copy of the scenario, compared with the current one |

Detection, prediction and re-planning only see events known at `at`. A
stoppage or delay is known once it starts; planned closures are known as soon
as they are posted. All responses are labelled `"data_label": "SIMULATED"`.
