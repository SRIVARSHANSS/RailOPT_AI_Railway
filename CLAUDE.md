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
- API (thin layer): from backend/ `uvicorn app.main:app` (dev: --reload), docs at
  http://127.0.0.1:8000/docs. Scenario state: computed in memory by `app/core/store.py::ScenarioStore`,
  persisted by `app/core/db_store.py::DbScenarioStore` (written after every change, reloaded on start);
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
  reset, event and decision. The boot id is stored with the scenario, so an API restart keeps the
  version (the restored state is the same; ASSUMPTIONS.md 85). The frontend caches the optimizer result with it and drops the
  cache (and the recommendation alert) when the server reports another version; the tab's own
  decision adopts the new version (useScenarioVersionGuard in api/hooks.ts, /scenario polled every 5 s).
- Results pages (read-only): GET /api/evaluation (eval/reports, hash-checked against the results CSV and
  model files via eval_summary.json `provenance`) and GET /api/model (ml/reports, hash-checked like
  test_ml) in app/services/results.py; status ok | outdated | missing. The UI never types a number:
  the ML conclusion sentence and its variant count are generated by the API from the summary.
- REAL data (DG -> MDU, RSTGCN Sept 2024, CC BY-SA 4.0; docs/DATA_SOURCES.md): never mix with
  SIMULATED. Raw zip in backend/data/real/raw/ (gitignored); committed extract in
  backend/data/real/dg_mdu/ (stations, sections, trains, schedule with time_source
  DATASET_ROUTE|DATASET_RECORDS|ESTIMATED, records, runs, audit.json/md, manifest). From backend/:
  `python -m app.services.realdata.extract` then `python -m app.services.realdata.audit`
  (audit.md is generated: never edit numbers by hand). DG chainage is DERIVED, platforms/headway/
  min run ASSUMED (ASSUMPTIONS.md 47-56). No scraping of NTES/IRCTC or any website.
- Real delay validation (Step 2, pre-registered in ASSUMPTIONS.md 57-63): from backend/
  `python -m ml.real_delay` (~10 s) writes ml/reports/real/{metrics_real.json, model_card_real.md,
  predictions_real.csv} (committed; card generated from the JSON). Split by DG date, train-mean
  feature from training dates only; carry-the-DG-delay is the baseline to beat. The SIMULATED
  Phase 4 models are not trained on real data.
- Real-day replay (Step 3): POST /api/scenario/reset {timetable:"dg_mdu", mode:"replay", date}
  (demo day 2024-09-12; GET /api/replay/days). app/services/realdata/replay.py builds the day:
  `timetable` (real, repaired), `movement` (recorded + INTERPOLATED, replays exactly on 16/32 days),
  `forecast(at)` = what is known at `at` (detection + optimizer use it, never later recorded times).
  Hypothetical events: history before the first event/plan is frozen (RailNetwork.frozen), after it
  simulated. data_label per response: SIMULATED | REAL | "HYPOTHETICAL on a real recorded day".
  Real corridor: headway CALIBRATED 0 (one train per block; calibrate.py), loops ASSUMED per station
  (no overtaking without a free loop: simulator, CP-SAT, find_violations), priorities ASSUMED
  PREMIUM 1 / SUPERFAST 2 / EXPRESS 3, weights = 4 - priority. Only HOLD and RESEQUENCE (no
  alternate line); every replay optimize also reports the headway-4 sensitivity. Simulated stations
  have loops = None: nothing changes there. ML models are not applied to real data.
- The API boots on the REAL demo day (dg_mdu replay, 2024-09-12; `boot_store()` in app/core/store.py).
  `RAILOPT_BOOT=simulated` boots on the SIMULATED reference corridor; tests use a fresh ScenarioStore() (reference).
- Phase 7 explainer (app/services/explainer): drivers.py (one template per model feature;
  "Model risk raised/lowered by: ...", never "because") and recommendation.py (Reason, What we
  recommend, Counterfactual, Expected impact + per train, Why not the others?, Constraints
  respected, Assumptions, Confidence, plain_text for "Copy explanation"). Every number in a sentence
  must come from the same payload (tests/test_explainer.py); "optimal" only for OPTIMAL.
- Phase 8 (ASSUMPTIONS.md 80-86): PostgreSQL 15 local service; DATABASE_URL and JWT_SECRET in the
  gitignored backend/.env (template backend/.env.example; no passwords in the repo). From backend/:
  `python -m alembic upgrade head` (never create_all outside tests), `python -m app.cli create-admin
  --email ...` / `create-user --role ...` / `list-users` (hidden password prompt). Models app/db/models.py,
  migrations alembic/versions (models == migrations is tested). Auth app/core/auth.py (roles READ /
  CONTROL / WHATIF / ADMIN_ONLY, `require(...)` on EVERY route; a new route must be added to the MATRIX
  in tests/test_auth.py), security.py (bcrypt directly, not passlib; JWT via python-jose), cookies
  httpOnly SameSite=Lax (COOKIE_SECURE=true over HTTPS), login lockout 5 failures / 15 min -> 429.
  Audit log via `audit(db, ACTION, user=...)`. Tests: conftest.py gives every test an in-memory SQLite
  DB and a CONTROLLER stand-in user; mark `real_auth` to use real cookies; `-m postgres` +
  TEST_DATABASE_URL runs migrations on a throwaway Postgres DB. Admin: app/api/admin_routes.py,
  app/services/netadmin.py (custom corridor in the DB, seeded from full_day; reference/full_day CSVs
  stay read-only). Frontend: lib/api.ts sends cookies and refreshes once on 401; lib/permissions.ts
  `useCan(action)` + Button `lockedReason` disable what a role cannot do (the API enforces it anyway).
- Pages 5 and 11 (ASSUMPTIONS.md 87-93): app/services/alerts.py (current lists + history: detection re-run
  every sim minute from the first departure with the knowledge of that minute; planned events known
  from `posted_at`, the clock the UI sends with POST /api/events, stored in events.posted_at_min,
  migration 0002; ML re-scored every 5 min and at each event/decision). app/api/alerts_routes.py:
  GET /api/alerts (CONTROLLER, ANALYST; not ADMIN), POST /api/alerts/ack (CONTROLLER) = an
  ALERT_ACKNOWLEDGED audit row keyed by store.run_ref (no table). Reports: app/services/reports/
  (pdf.py: reportlab + matplotlib's DejaVu Sans for ALL text, incl. table and bullet fonts; footer =
  data label per page, LabelMark switches it; charts.py; scenario.py calls the route functions so
  numbers equal the API; results_pdf.py raises Outdated -> 409 unless results and model cards are
  fresh). app/api/report_routes.py (scenario READ; evaluation/model REPORTS = ADMIN + ANALYST); audit
  CSV in admin_routes. Every export logs REPORT_EXPORTED. pypdf is test-only
  (backend/requirements-dev.txt). CORS exposes Content-Disposition for downloads.
- 251 tests passing (+1 optional postgres test).
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
- [x] Phase 7: explainable recommendations (template text only; ASSUMPTIONS.md 72-79)
- [x] Phase 8: PostgreSQL persistence, JWT auth (roles, rate limit, audit log), admin pages
- [x] Phase 9: React frontend, 12 planned pages (project build guide): 12 of 12 exist; demo: docs/DEMO.md
  - [x] 1 Login  - [x] 2 Traffic Console  - [x] 3 Time-Distance Chart (/timeline)
  - [x] 4 Disruption Panel  - [x] 5 Conflicts and Alerts (/alerts: lists, history, acknowledge)
  - [x] 6 Strategy Comparison  - [x] 7 What-If Studio
  - [x] 8 Analytics (/analytics)  - [x] 9 Model Insights (/model: ML metrics vs baselines, SHAP drivers)
  - [x] 10 Network and Train Management (/admin/network: custom corridor CRUD, CSV import, REAL read-only)
  - [x] 11 Reports (/reports: scenario PDF + CSV, evaluation PDF, model PDF, audit CSV)
  - [x] 12 User Management (/admin/users: users, roles, audit log)
  - The Design system gallery (/design) is a dev page, not one of the 12.
- [x] Phase 10: evaluation on 200 SIMULATED scenarios (backend/eval; results: eval/reports/eval_report.md)
- [ ] Phase 11: Docker, README, demo script
- [~] Real data phase, Dindigul -> Madurai: [x] Step 1 corridor, timetable, extract, audit
  (backend/data/real/dg_mdu/audit.md)  [x] Step 2 real delay model validation
  (ml/reports/real/model_card_real.md)
  [x] Step 3 real-day replay mode (Act 3 in docs/DEMO.md)
