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
- [x] Phase 5: CP-SAT re-planning (hold, reroute, resequence, combined) vs no-re-planning and
  priority-dispatch baselines; every plan is replayed through the simulator
  (results: `backend/ml/reports/model_card.md`, all on SIMULATED data)
- 53 passing tests. Remaining phases: see `CLAUDE.md`

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
python -m app.services.datagen.generate --runs 3000 --seed 42   # SIMULATED training rows -> data/generated/
python -m ml.train                          # models -> ml/models/, reports -> ml/reports/ (~3 min)
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
  ml/                       split, preprocessing, training, SHAP; reports/ holds metrics + model card
  data/                     corridor CSVs (reference + full-day timetable), T101 event file
  tests/                    pytest suite
docs/ASSUMPTIONS.md         corridor, timetable and modelling assumptions
```
