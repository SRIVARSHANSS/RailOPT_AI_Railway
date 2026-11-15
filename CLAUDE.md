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
- Evaluation (Phase 10): from backend/ `python -m eval.run_eval --scenarios 200 --seed 2026` (~a few min,
  needs the trained models) writes eval/reports/{eval_results.csv,eval_summary.json,eval_report.md,*.png}
  (committed). eval_report.md is generated from the JSON: never edit numbers by hand. Seed 42 is the
  training seed and is refused; tests/test_eval.py checks no scenario overlaps the training data.
  Phase 10b ML integration variants (B2/B3 buffers, round(3p) buffers, ML-triggered re-planning) are
  pre-registered in docs/ASSUMPTIONS.md 43-46 and run in the same evaluation; report every result.
- Optimizer demo: `python -m app.services.optimizer.run_demo`. Call a plan optimal only when the
  CP-SAT status is OPTIMAL; strategy D is named COMBINED for that reason. All metrics come from the replay.
- API (thin layer, Phase 8 adds Postgres + JWT): from backend/ `uvicorn app.main:app` (dev: --reload), docs at
  http://127.0.0.1:8000/docs. Scenario state is in memory behind `app/core/store.py::ScenarioStore`;
  view logic in `app/services/live.py`. Knowledge is time-aware: STOPPAGE/DELAY known only when
  at >= start, TRACK_UNAVAILABLE known once posted; movement (/state, /timeline) uses all events.
  Every response carries data_label = SIMULATED.
- UI rule: an ml_watchlist item with resolved_by_plan = true is shown as "Risk resolved by accepted plan"
  (green, risk struck through); with reduced_by_plan = true (wait lowered but not to zero, compared with
  the plan it replaced) as "Risk reduced by plan (X -> Y min wait)" in calm cyan. Neither is an active
  warning; keep showing ml_note.
- Phase 6 rules: an accepted plan goes stale when an event is known that its optimizer run did not
  know (plan block in /api/state and /api/scenario). /api/optimize re-plans on top of the accepted
  plan: started trips fixed, baselines = keep the current plan. /api/whatif works on a copy (all
  hypothetical events known at `at`), labelled HYPOTHETICAL; never touch the live store from it.
  A TRACK_UNAVAILABLE that would start while a train is inside the section is rejected (422 with
  the clear time). For demos run the API without --reload (the Windows watcher can stall).
- scenario_version ('<boot id>-<revision>', in /scenario, /state, /optimize, /decision) changes on every
  API start, reset, event and decision. The frontend caches the optimizer result with it and drops the
  cache (and the recommendation alert) when the server reports another version; the tab's own
  decision adopts the new version (useScenarioVersionGuard in api/hooks.ts, /scenario polled every 5 s).
- 85 tests passing.
- Frontend (frontend/): npm, Vite + React + TS, Tailwind 3.4, React Router, React Query, Zustand,
  Framer Motion, Radix, lucide-react. `npm run dev` -> http://localhost:5173 (exact origin, CORS).
  Do NOT use the website-builder skill here. Design tokens: src/styles/tokens.css + tailwind.config.ts;
  motion durations/easings only from src/lib/motion.ts; animate transform/opacity only; honour
  reduced motion. Every screen shows the SIMULATED badge. Never show invented numbers in the UI:
  data comes from the API, gallery examples are labelled as examples. framer-motion is pinned with
  npm overrides for motion-dom / motion-utils (12.18.1); keep them in step when upgrading.
- Timeline (src/pages/Timeline.tsx, src/features/timeline/): time-distance chart, D3 (scales, zoom,
  line) inside React. Rows, stops, waits, delays, closures and before_plan all come from /api/timeline
  (before_plan = replay under the plan the accepted one replaced, null without a plan); conflicts
  from /api/conflicts at the sim clock. Alternate (standby) sections are drawn as a lane offset
  LANE_DY px below their main section. Only exception to "transform/opacity only": the one-off
  first-load line drawing (pathLength / stroke-dashoffset, duration.draw), off under reduced motion.
- Console motion rules: trains glide only from the API state at minute m to m+1, sampled along the
  SVG track (getPointAtLength) and through the station node on a section change; any clock jump
  (scrub, reset, backwards) snaps. The UI never computes railway logic: positions, delays, `stopped`,
  conflicts and plans all come from the API.
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
- [x] Phase 6: what-if (POST /api/whatif, What-If Studio) + re-optimization on top of an accepted plan
- [ ] Phase 7: explainer
- [ ] Phase 8: FastAPI + PostgreSQL + auth
- [~] Phase 9: React frontend, 12 planned pages (project build guide); demo: docs/DEMO.md
  - [x] 1 Login  - [x] 2 Traffic Console  - [x] 3 Time-Distance Chart (/timeline)
  - [x] 4 Disruption Panel  - [~] 5 Conflicts and Alerts (partial: lives in the console alert feed,
    no page of its own)  - [x] 6 Strategy Comparison  - [x] 7 What-If Studio
  - [ ] 8 Analytics  - [ ] 9 Model Insights (ML metrics vs baselines, SHAP drivers)
  - [ ] 10 Network and Train Management (admin CRUD, CSV import)  - [ ] 11 Reports (CSV/PDF export)
  - [ ] 12 User Management (admin)
  - The Design system gallery (/design) is a dev page, not one of the 12.
- [x] Phase 10: evaluation on 200 SIMULATED scenarios (backend/eval; results: eval/reports/eval_report.md)
- [ ] Phase 11: Docker, README, demo script
