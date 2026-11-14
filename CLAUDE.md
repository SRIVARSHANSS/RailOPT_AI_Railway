# RailOpt AI — project guide for Claude Code

Final-year CSE project (PSNA College of Engineering & Technology, batch 27D08), based on SIH25022.
RailOpt AI is a software-only decision-support and simulation prototype for a human railway
traffic controller: PREDICT -> DETECT -> SIMULATE -> OPTIMIZE -> EXPLAIN -> RECOMMEND,
re-run on every new event.

## Hard rules
- Never claim the system controls trains or signals, or replaces Indian Railways systems.
- Keep real data (timetables, Sept 2024 running records) separate from simulated data. Label every result as simulated.
- Never invent metrics, accuracy numbers or real-world improvements. Numbers come only from actual runs.
- Always account for knock-on (cascading) effects on the trains that follow.
- Use realistic constraints: minimum running time, minimum headway, section capacity, priority, track and platform availability.
- An LLM may only rephrase results. All decisions are deterministic (rules, ML, CP-SAT).
- Build logic before UI. Split ML data by scenario/run_id, never randomly. Always compare against baselines.

## Reference scenario (use in tests and the demo)
Corridor A -> B -> C -> D; B-C is the constrained section.
T101 Express (priority 1), T202 Passenger (priority 2), T303 Freight (priority 3).
At 10:03 T101 stops inside B-C for 15 minutes. T202 reaches B-C about 6 minutes later -> conflict.
Strategies: A) hold T202 and T303, B) reroute T202 on the alternate track, C) resequence.
Re-optimization test: stoppage, then T202 +5 min delay, then a track closure.

## Stack
- Backend: Python 3.11, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL, JWT (roles: admin, controller, analyst)
- Simulation: custom discrete-event loop (app/services/simulator/engine.py), NetworkX
- ML: pandas, NumPy, scikit-learn, XGBoost, SHAP, joblib
- Optimization: Google OR-Tools CP-SAT
- Frontend: React + TypeScript + Vite, Tailwind, React Router, React Query, Zustand, D3, Recharts, React Flow
- Tests: pytest. Packaging: Docker Compose (db, backend, frontend)

## Folder layout
```
Rail OPT/  (project root)
  backend/app/{api,core,models,schemas,services}
  backend/app/services/{network,simulator,conflicts,predictor,optimizer,whatif,explainer}
  backend/ml/        # training scripts, notebooks, saved models
  backend/data/      # stations.csv, sections.csv, trains.csv, schedule.csv, generated datasets
  backend/tests/
  frontend/src/{pages,components,charts,api,store}
  docker-compose.yml
  README.md
```

## Data files (backend/data)
- stations.csv: station_code,station_name,km_from_start,platforms,is_junction
- sections.csv: section_id,from_station,to_station,length_km,tracks,min_run_min,min_headway_min,status
- trains.csv: train_id,train_no,train_name,train_type,priority,runs_on
- schedule.csv: train_id,station_code,stop_seq,sched_arr,sched_dep
- events.csv: event_id,run_id,event_type,train_id,location,start_time,duration_min
  (event_type: STOPPAGE, DELAY, TRACK_UNAVAILABLE, PLATFORM_UNAVAILABLE)

## How to work
- Python 3.12 venv in backend/.venv (not 3.14: OR-Tools/XGBoost/SHAP support).
- Run tests from backend/: `python -m pytest -q`. Demos: `python -m app.services.simulator.run_demo`,
  `python -m app.services.conflicts.run_demo`. Data: `python -m app.services.datagen.generate --runs 3000 --seed 42`
  (writes backend/data/generated/, gitignored). Timetables: `load_network()` = 3-train reference,
  `load_network(timetable="full_day")` = 12 trains. Old tests use the reference; never change them.
- ML: `python -m ml.train` (from backend/, ~3 min) writes ml/models/*.joblib (gitignored) and
  ml/reports/{metrics.json,model_card.md,feature_importance.csv} (committed). metrics.json stores
  SHA-256 of the dataset and model files; after regenerating data, retrain or test_ml fails.
- Optimizer demo: `python -m app.services.optimizer.run_demo`. Call a plan optimal only when the
  CP-SAT status is OPTIMAL; strategy D is named COMBINED for that reason. All metrics come from the replay.
- API (thin layer, Phase 8 adds Postgres + JWT): from backend/ `uvicorn app.main:app --reload`, docs at
  http://127.0.0.1:8000/docs. Scenario state is in memory behind `app/core/store.py::ScenarioStore`;
  view logic in `app/services/live.py`. Knowledge is time-aware: STOPPAGE/DELAY known only when
  at >= start, TRACK_UNAVAILABLE known once posted; movement (/state, /timeline) uses all events.
  Every response carries data_label = SIMULATED.
- UI rule: an ml_watchlist item with resolved_by_plan = true is shown as "Risk resolved by accepted plan"
  (green, risk struck through), not as an active warning; keep showing ml_note.
- 66 tests passing.
- Frontend (frontend/): npm, Vite + React + TS, Tailwind 3.4, React Router, React Query, Zustand,
  Framer Motion, Radix, lucide-react. `npm run dev` -> http://localhost:5173 (exact origin, CORS).
  Do NOT use the website-builder skill here. Design tokens: src/styles/tokens.css + tailwind.config.ts;
  motion durations/easings only from src/lib/motion.ts; animate transform/opacity only; honour
  reduced motion. Every screen shows the SIMULATED badge. Never show invented numbers in the UI:
  data comes from the API, gallery examples are labelled as examples. framer-motion is pinned with
  npm overrides for motion-dom / motion-utils (12.18.1); keep them in step when upgrading.
- Login media: src/config/media.ts (video optional; poster-only drift supported; CSS fallback).
  Current clip is owner-supplied (licence to confirm before public use). The see-through login card
  only uses text-ink: contrast was measured over the clip's frames (worst 5.33:1); re-measure if it changes.
  Higgsfield: preflight get_cost, state credits and balance, wait for the user's go.
- Work one phase at a time. Write pytest tests with each module and run them before moving on.
- Keep services as plain Python, independent of FastAPI, so they can be tested directly.
- Before a large change, explain the plan briefly and wait for approval.
- Commit after each working step with a clear message.

## Build status (update as you go)
- [x] Phase 0: scope locked (corridor, trains, assumptions) - see docs/ASSUMPTIONS.md
- [x] Phase 1: network model + simulator (custom event loop, 14 tests passing)
- [x] Phase 2: full-day timetable (12 trains), simulator variability (rng), training-data generator (app/services/datagen)
- [x] Phase 3: conflict detector (rule-based, planned times; cascade via simulator)
- [x] Phase 4: ML models + baselines (backend/ml, app/services/predictor; see ml/reports/model_card.md)
- [x] Phase 5: CP-SAT optimizer + baselines (app/services/optimizer; strategies replayed through the simulator)
- [ ] Phase 6: what-if + re-optimization
- [ ] Phase 7: explainer
- [ ] Phase 8: FastAPI + PostgreSQL + auth
- [ ] Phase 9: React frontend - part 1 done (design system, app shell, login); part 2 = data pages
- [ ] Phase 10: evaluation
- [ ] Phase 11: Docker, README, demo script
