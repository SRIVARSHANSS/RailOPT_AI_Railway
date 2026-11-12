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
  `python -m app.services.conflicts.run_demo`.
- Work one phase at a time. Write pytest tests with each module and run them before moving on.
- Keep services as plain Python, independent of FastAPI, so they can be tested directly.
- Before a large change, explain the plan briefly and wait for approval.
- Commit after each working step with a clear message.

## Build status (update as you go)
- [x] Phase 0: scope locked (corridor, trains, assumptions) - see docs/ASSUMPTIONS.md
- [x] Phase 1: network model + simulator (custom event loop, 14 tests passing)
- [ ] Phase 2: data generator
- [x] Phase 3: conflict detector (rule-based, planned times; cascade via simulator; 24 tests passing)
- [ ] Phase 4: ML models + baselines
- [ ] Phase 5: CP-SAT optimizer + baselines
- [ ] Phase 6: what-if + re-optimization
- [ ] Phase 7: explainer
- [ ] Phase 8: FastAPI + PostgreSQL + auth
- [ ] Phase 9: React frontend
- [ ] Phase 10: evaluation
- [ ] Phase 11: Docker, README, demo script
