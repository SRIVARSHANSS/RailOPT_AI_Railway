# Phase 0: scope and assumptions

All values below belong to the **sample corridor** used to build and test the
system. They are illustrative and simulated, not real Indian Railways figures.
When the real Tamil Nadu corridor is chosen, the real timetable replaces
`schedule.csv` and `trains.csv`; any value still not publicly available stays
listed here as an assumption.

## Corridor

| Station | km | Platforms |
| --- | --- | --- |
| A | 0 | 3 (junction) |
| B | 22 | 2 |
| C | 40 | 2 |
| D | 65 | 3 (junction) |

| Section | Tracks | Min run (min) | Min headway (min) | Status |
| --- | --- | --- | --- | --- |
| S_AB (A-B) | 2 | 16 | 3 | open |
| S_BC (B-C) | 1 | 12 | 5 | open, the constrained section |
| S_BC_ALT (B-C) | 1 | 16 | 5 | standby alternate line, used only by reroute |
| S_CD (C-D) | 2 | 18 | 3 | open |

## Trains (simulated)

| Train | Type | Priority | A dep | B | C | D arr |
| --- | --- | --- | --- | --- | --- | --- |
| T101 | Express | 1 | 09:38 | 09:54-09:56 | 10:08-10:10 | 10:28 |
| T202 | Passenger | 2 | 09:50 | 10:09-10:13 | 10:27-10:29 | 10:50 |
| T303 | Freight | 3 | 10:10 | 10:34 (pass) | 10:52 (pass) | 11:16 |

The timetable is conflict-free on a normal day (tested).

## Modelling assumptions

1. **Headway** = minimum gap between one train clearing a track and the next train entering it.
2. **Capacity**: a section with *n* tracks holds at most *n* trains at once, all in the same direction (one-direction corridor in this phase).
3. **Running time** = the timetabled time on the planned section, never below the section minimum. On the alternate line a train needs the extra minimum time of that line (S_BC_ALT: +4 min).
4. **Dwell**: a train keeps its timetabled stop length and never departs before its scheduled time. No recovery margins yet.
5. **Waiting**: a train that cannot enter a section waits at the station signal before it.
6. **Dispatch rule** in the simulator: first-come-first-served by ready time, ties broken by priority. This is also the "no re-planning" baseline.
7. **Stoppage** applies only if the train is inside that section at the stoppage start time.
8. **Track closure**: a train may not enter if its trip through the section would overlap the closure.
9. **Platforms** are not modelled yet; PLATFORM_UNAVAILABLE events are reported as ignored.
10. **Simulator choice**: a custom discrete-event loop (heap of timed requests) instead of SimPy. It is deterministic, easy to test and easy to explain; the project brief allows either.

## Reference result (simulated, no re-planning)

T101 stops in B-C at 10:03 for 15 min:

| Train | Waits before B-C | Arrival delay at D |
| --- | --- | --- |
| T101 | 0 (stopped 15 min inside) | 15 min |
| T202 | 15 min | 15 min |
| T303 | 13 min | 13 min |

Total delay 43 min. This is the baseline the optimizer must beat in Phase 5.

## Phase 2: full-day timetable (simulated)

`trains.csv` / `schedule.csv` stay the 3-train reference scenario above.
`trains_full_day.csv` / `schedule_full_day.csv` hold the full day
(`load_network(timetable="full_day")`): the same T101, T202, T303 rows
unchanged, plus 9 more simulated trains, 12 in total, 06:08 to 13:18.

| Train | Type | A dep | S_BC (B-C) | D arr |
| --- | --- | --- | --- | --- |
| T401 | Passenger | 06:08 | 06:30-06:44 | 07:07 |
| T501 | Freight | 06:28 | 06:52-07:10 | 07:34 |
| T102 | Express | 07:00 | 07:18-07:30 | 07:50 |
| T402 | Passenger | 07:18 | 07:40-07:54 | 08:17 |
| T101, T202, T303 | (reference) | | | |
| T103 | Express | 10:44 | 11:02-11:14 | 11:34 |
| T403 | Passenger | 11:00 | 11:22-11:36 | 11:59 |
| T502 | Freight | 11:20 | 11:44-12:02 | 12:26 |
| T404 | Passenger | 11:50 | 12:12-12:26 | 12:49 |
| T503 | Freight | 12:12 | 12:36-12:54 | 13:18 |

- Trains are 8-10 min apart on S_BC, so the normal day is conflict-free
  (tested), but random slowdowns can make the next train wait.
- No new train runs between about 09:15 and 10:40, so the T101 reference
  result (15/15/13) is the same on the full day. There the knock-on also
  reaches T103, T403 and T502.

## Phase 2: random variability (assumptions)

The simulator is deterministic unless it is given a random generator
(`simulate(..., rng=random.Random(seed))`). With one, per section trip:

| Train type | Running time slower than planned by |
| --- | --- |
| EXPRESS | 0-5 % |
| PASSENGER | 0-10 % |
| FREIGHT | 0-20 % |

11. Slowdown is uniform in that range, rounded to whole minutes, so a train
    is never faster than planned and never below `min_run_min`.
12. At a station where the train has a timetabled stop it may leave 0-3 min
    (whole minutes, uniform) later than the dwell rule allows. Trains passing
    without stopping get no overrun.
13. `project_plan` and `detect_conflicts` never see this randomness. They use
    only the timetable and known disruptions. The gap between their answer
    and the randomised outcome is what the Phase 4 model has to learn.

## Phase 2: synthetic training data (assumptions)

14. Each run: every train gets a 0-5 min starting delay (a DELAY at its origin,
    treated as known), plus 1-3 random disruptions (STOPPAGE, DELAY or
    TRACK_UNAVAILABLE), each 5-30 min. No platform events yet.
    - STOPPAGE: random train and one of its sections, starting inside its
      planned trip; the event records that offset (`offset_min`). If random
      variability means the train is not inside at that minute, the simulator
      applies the stoppage at the train's actual entry + the same offset and
      records it in `applied_events`. With `rng=None` the Phase 1 rule is
      unchanged: a stoppage that misses the train is ignored.
    - DELAY: random train, at one of its stations, at its planned departure.
    - TRACK_UNAVAILABLE: random main section, start uniform in 06:00-14:00,
      never on a section that has a stoppage in the same run. The model has
      no rule for a closure that begins while a stopped train is stranded
      inside, and a moved stoppage can land at any time.
15. State time = the first disruption's start. Features use only what is known
    then: the timetable, starting delays and disruptions already started.
    Labels use everything plus the random variability, with no re-planning.
16. Rows: one per (run, train, section) that the plan has the train entering
    after state time. When no train is ahead on that section,
    `headway_gap_min` = 999 and the preceding-train fields are NONE / 0.
17. `current_delay_min` = planned entry minus timetabled departure for that
    section (the train's known lateness, projected forward). `hour_of_day` is
    the hour of the planned entry.
18. The Phase 4 train/test split is by `run_id`, never by random rows.

## Phase 5: re-planning optimizer (assumptions)

19. **Holds** (simulator): a held train requests its section only when the
    hold ends; it books nothing earlier. Its wait is still counted from the
    moment it was ready. Plans from the optimizer are replayed this way.
20. **Dispatch** (simulator): `fcfs` (default, the "no re-planning" baseline)
    books the next free slot as soon as a train is ready. `priority` (the
    "priority dispatch" baseline) lets a blocked train wait without booking;
    each time a track frees, the highest-priority waiting train enters first.
    Neither mode pre-empts a train that has already entered.
21. **History**: the optimizer takes everything entered at or before state
    time from the no-re-planning simulation of the known events, and fixes
    it. This includes trains inside a section at state time, with their
    known stoppage.
22. **Rolling horizon**: only trips that `project_plan` starts within 120 min
    of state time are re-planned. For a train whose route goes beyond the
    horizon, the objective uses its delay at the last station inside it. The
    timetable has no recovery margins, so that delay carries on. Later trips
    are not held; in the replay they run first come, first served.
23. **Model**: integer minutes. Each re-planned trip is an interval
    [entry, exit + headway (+ optional risk buffer)].
    - Capacity: 1-track sections use NoOverlap; multi-track sections use
      Cumulative with capacity = tracks.
    - Entry rules: entry >= scheduled departure, >= previous exit + timetabled
      dwell, and >= the end of a known DELAY at that station.
    - Closures: a trip's [entry, exit) must not overlap a closure. The headway
      tail may, which is the simulator's rule.
    - Reroute: exactly one of S_BC / S_BC_ALT, with the alternate line's
      longer running time.
    - Planning window: 24 h after state time. No schedule within it means
      INFEASIBLE.
24. **Objective**: minimise sum(weight x arrival delay), with weights
    EXPRESS 3, PASSENGER 2, FREIGHT 1, plus 1 weighted-minute per reroute
    (`app/services/optimizer/config.py`).
25. **Strategies**:
    - HOLD: timetable order on every section, main line only.
    - REROUTE: timetable order, alternate line allowed.
    - RESEQUENCE: free order, main line only.
    - COMBINED: free order + alternate line.
    "Timetable order" = order of scheduled departure onto the section (ties
    by priority), between trains that both use it.
26. **Solver**: CP-SAT, 1 worker, fixed seed, 10 s limit, so results are
    deterministic. A plan is called optimal only when CP-SAT returns OPTIMAL,
    meaning optimal for that strategy's model. FEASIBLE is reported as "not
    proven optimal".
27. **Scoring**: every plan is replayed through the simulator (rng=None), and
    all reported metrics come from the replay. The replay must have zero
    capacity, headway, closure or early-departure violations.
28. **ML risk buffers** (optional, off by default): +1 min headway on trips
    the conflict model flags at its recall >= 0.80 threshold.

### Reference result (simulated, from `python -m app.services.optimizer.run_demo`)

T101 stops in B-C at 10:03 for 15 min, weights 3/2/1. All four strategies
solved to OPTIMAL.

| Plan | Weighted delay | Total delay | T101 / T202 / T303 | Action |
| --- | --- | --- | --- | --- |
| No re-planning | 88 | 43 | 15 / 15 / 13 | - |
| Priority dispatch | 88 | 43 | 15 / 15 / 13 | - |
| HOLD | 88 | 43 | 15 / 15 / 13 | hold T202 to 10:28, T303 to 10:47 |
| RESEQUENCE | 88 | 43 | 15 / 15 / 13 | same holds (no better order exists) |
| REROUTE | 53 | 19 | 15 / 4 / 0 | reroute T202 via S_BC_ALT |
| COMBINED | 53 | 19 | 15 / 4 / 0 | reroute T202 via S_BC_ALT |

On the full-day timetable the same event costs 124 weighted / 58 total
without re-planning, because the knock-on reaches T103, T403 and T502.
Rerouting T202 cuts that to 53 / 19.

## API layer (assumptions)

29. **Knowledge is time-aware**, using the same no-leakage rule as Phase 2.
    STOPPAGE and DELAY events are surprises: known only from their start
    time. TRACK_UNAVAILABLE is planned maintenance: known as soon as it is
    posted. Detection, the ML predictor and the optimizer only see known
    events. Train movement (`/state`, `/timeline`) uses every posted event.
30. An **accepted recommendation** becomes the scenario's controller plan
    (holds and reroutes). The detector plans with it, so a resolved conflict
    disappears. The ML features still describe the timetable plan without it,
    because the model was trained on runs with no re-planning; the API says
    so in `ml_note`.
    A watchlist item is marked `resolved_by_plan` when, in a deterministic
    replay (rng=None) of the accepted plan on the known events, that train
    does not wait before the flagged trip (same stations, either line). It is
    marked `reduced_by_plan` when that wait is above zero but lower than in a
    replay of the plan the accepted one replaced (no plan if there was none),
    e.g. T303 16 -> 2 min in demo act 2.
31. **Train state at a clock time**:
    - Status, from the simulated timeline: not started, at station, waiting
      at signal (ready but not entered, including held trains), in section,
      or arrived.
    - Current delay, in a section: max(departure delay, clock − scheduled
      arrival at the next station).
    - Current delay, at a station or signal: max(arrival delay, clock −
      scheduled departure).
    - Average delay is taken over active trains.
    - Progress in a section is the share of *running* time covered: minutes standing
      in a stoppage do not move the train, and `stopped` is true while it stands.

## Phase 6: what-if and re-optimization (assumptions)

32. **Stale plan**: an accepted plan remembers the events its optimizer run knew. It becomes
    stale at clock time `at` when an event is known then that the run did not know (a
    surprise that has since started, or anything posted after the run).
33. **Re-planning from the current state**: the optimizer simulates history with the
    accepted plan, fixes every trip started at state time (an accepted reroute in progress
    stays on its line), and decides only future trips in the 120-min horizon. Replays apply
    the started trips at their recorded times plus the new decisions. With an accepted plan
    the baselines mean "keep the current plan" (no new re-planning).
34. **Accepting a new plan** replaces the old one; the decision log records which plan it
    replaced.
35. **What-if**: hypothetical events are applied to a copy of the scenario (events + accepted
    plan) and all count as known at `at` (the point of a what-if is to assume they happen).
    The result is labelled HYPOTHETICAL and SIMULATED and its recommendation cannot be
    accepted. The live scenario is never modified (tested byte for byte).
36. **Closing an occupied section is not modelled**: a TRACK_UNAVAILABLE (posted or
    hypothetical) is rejected if, in the scenario's current timeline, a train is inside the
    section at the closure's start (entered before it, leaves after it). The message gives
    the first start after the section is clear (checked repeatedly, since another train may
    already be inside when the first leaves).

### Three-event re-optimization (simulated, reference timetable, from tests/test_phase6.py)

| Step | Re-optimized at | Recommended | Weighted (T101 / T202 / T303) |
| --- | --- | --- | --- |
| T101 stoppage 10:03, 15 min | 10:03 | REROUTE (accepted) | 53 (15 / 4 / 0) |
| T202 +5 min at C (10:33) | 10:33 | HOLD, no action: nothing improves on the plan | 63 (15 / 9 / 0) |
| S_CD closure | 10:40 | HOLD, no action | 63 (15 / 9 / 0) |

All CP-SAT statuses OPTIMAL, zero violations in every replay, started trips unchanged.
S_CD is occupied without a gap from 10:25 to 11:16 (T101, then the delayed T202, then T303),
so a closure at 11:00 was rejected ("T303 is inside S_CD at 11:00 ... clears (11:16)") and the
first legal start, 11:16, affects no train.

### Demo act 2: maintenance block re-plan (simulated, reference timetable)

After the accepted reroute R1, S_BC is closed for planned maintenance 10:30-10:50 (posted
10:25, known on posting). Re-optimized at 10:25, every replay with zero violations:

| Plan | Weighted | T101 / T202 / T303 | What happens to T303 |
| --- | --- | --- | --- |
| Keep R1 (no new re-planning) | 69 | 15 / 4 / 16 | held at B until 10:50 |
| REROUTE (recommended, OPTIMAL) | 59 | 15 / 4 / 6 | via S_BC_ALT 10:36-10:58, after T202 clears |

A later T202 +5 min delay at C (10:33) re-optimizes to "no strategy improves on keeping the
accepted plan" (weighted 69): the recommendation repeats the plan already in force.

## Phase 10: evaluation (assumptions)

37. **Evaluation scenarios**: the Phase 2 generator logic (`sample_run`, full-day timetable,
    12 trains, 1-3 disruptions of 5-30 min, 0-5 min starting delays) with seed 2026. The
    3000 training scenarios (seed 42) are rebuilt and fingerprinted; no evaluation scenario
    may match one (checked in tests/test_eval.py and by the CLI).
38. **Closure posting rule**: a TRACK_UNAVAILABLE is posted 30 min before it starts, or at
    06:00 if that is later; it is known from posting. Stoppages and delays are known at their
    start; starting delays are known from the start (as in Phase 2).
39. **RailOpt methods** use the COMBINED strategy. Single-shot solves once, when the first
    disruption becomes known; dynamic solves again at every time a new event becomes known,
    on top of the plan in force (started trips fixed, 120-min horizon); dynamic + ML adds the
    optional risk buffers (+1 min headway on trips the conflict model flags). A method adopts
    the solver's plan whenever the solve returns one (OPTIMAL or FEASIBLE).
40. **Settings**: deterministic = one replay with all events, rng=None. Robustness = the same
    plans, fixed in advance, replayed 5 times under the Phase 2 variability with the same
    seeds for every method (common random numbers); a scenario's value is the mean of its 5
    replays. In use, RailOpt would re-plan again as actual times drift; that is not modelled.
41. **Metrics** come from replays only: delay at destination (average per train, total,
    priority-weighted with 3/2/1, maximum), throughput, trains that waited at least once and
    total wait minutes (planned holds count as waiting). Every replay is checked for
    violations (asserted zero).
42. **Statistics**: per-scenario values; 95% percentile bootstrap CIs (10,000 resamples,
    seeded) for mean and median; paired differences vs no re-planning, called significant
    only when the CI of the mean difference excludes 0 (Wilcoxon p reported alongside).

## Phase 10b: ML integration variants (pre-registered before any run)

Written down before implementing or running them; all results are reported, helpful or not.
Same 200 scenarios (seed 2026), both settings, same statistics; each variant is compared
with plain DYNAMIC (the ML-free reference) and with no re-planning.

43. **A - fixed buffers of 2 and 3 min** (`DYNAMIC_ML_B2`, `DYNAMIC_ML_B3`): exactly
    `DYNAMIC_ML` (features on the plan-free projection, flag = conflict probability >= the
    deployed recall >= 0.80 threshold), but each flagged trip gets +2 / +3 min headway.
44. **B - proportional buffers** (`DYNAMIC_ML_PROP`): every upcoming trip gets
    round(3 x p) min headway (half rounds up; p < 1/6 gives 0), flagged or not. Same features.
45. **C - ML-triggered early re-planning** (`DYNAMIC_ML_TRIGGER`): DYNAMIC (re-solve at every
    newly known event, no buffers) plus model checks every 10 min from the first decision
    point to the last timetabled arrival. At each check the features are built on the
    current plan's projection (accepted holds and reroutes) with the events known then. A
    train is "newly high-risk" when the model flags one of its upcoming trips (p >= the
    deployed threshold), the rule-based detector has no conflict for that trip, and the
    train was not flagged at any earlier check. Any newly high-risk train triggers a COMBINED
    re-solve on top of the current plan (started trips fixed). Flags seen at an event-time
    check count as seen.
46. Batch scoring for 10b uses the same preprocessing and conflict model as the deployed
    predictor (probabilities only, no SHAP); tests check it matches `Predictor.predict`.


## REAL data: Dindigul -> Madurai corridor (Step 1)

REAL and SIMULATED never mix: real files live in `backend/data/real/` and carry
`data_label = REAL`; sources and licence in `docs/DATA_SOURCES.md`.

47. **Corridor**: direction DG -> MDU only, stations DG, ABI, KQN, VDP, SDN, SER, KON, MDU;
    7 block sections with 1 track each in this direction (the line is double, "twin single
    line"). Chainages ABI..MDU: SR Madurai division system map 2024 (owner-supplied values).
48. **DG chainage DERIVED**: the 2024 division map and the 2021 SR zonal map URLs returned
    404 on 2026-11-15, so DG = ABI 444.02 - 11 km (DG-ABI in the dataset's route file) =
    433.02 km. The dataset's route distances are whole km and disagree with the map at the
    other stations by about 1 km (KQN, SDN, KON, MDU imply DG about 428.9-429.2); ABI is the
    outlier (+3 km). Owner's rule kept; to revisit if the map becomes readable.
49. **ASSUMED platforms** usable by DG -> MDU trains: DG 5, MDU 7, intermediate stations 2.
50. **ASSUMED minimum running time** per section = ceil(length / 110 km/h); no scheduled
    section is faster; 4 of 994 recorded station-to-station runs are (flagged in the audit
    as likely source artifacts, not removed).
51. **ASSUMED minimum headway** 5 min on every section.
52. **Priority**: all real trains are expresses/superfasts/premium; priority 1 for all
    (ASSUMED; no public priority order). Type from the IR numbering (12/20/22xxx superfast),
    "Vande Bharat"/"Tejas" in the name = PREMIUM, 4-digit numbers = 0xxxx specials (excluded).
53. **Timetable**: `train_routes_Sep2024.csv` is the primary source; times only at the
    stations it lists. Where its times are degenerate (every station at one clock time:
    12665, 20494, 20601) the modal scheduled times from the running records are used
    (`DATASET_RECORDS`). Stations a train does not list are ESTIMATED by linear
    interpolation on km between the neighbouring listed times (passing, no stop).
    Passenger/MEMU: not in the dataset (it excludes local trains), not modelled, no times
    invented. Freight: not public, synthetic freight only in SIMULATED scenarios.
54. **Dates**: the dataset `date` is the journey START date; times are unrolled along the
    route (a day added whenever the clock goes backwards). Records are keyed by the DG date.
55. **Delays** are recomputed (signed) from the scheduled and actual clock times; they agree
    with the dataset's delay column on every record. The source never records an actual time
    earlier than scheduled.
56. **runs_on** is DERIVED from the records: a DG weekday counts when the train was recorded on
    at least half of that weekday's dates in September. Missing train-days are counted against
    this, so the missing share is a lower bound.

## REAL data Step 2: delay model validation (pre-registered before any training)

Written and committed before the first model was fitted. Every result below is reported,
including any where ML does not help. Data label REAL; the SIMULATED Phase 4 models are not
changed and were never trained on real data.

57. **DG km** stays 433.02 (DERIVED, about +-4 km; published timetables give DG-MDU = 62 km).
    Not used as a feature, so it does not affect Step 2.
58. **Task**: predict the arrival delay at MDU (minutes, signed from clock times) from what is
    known when the train departs DG: DG departure delay, DG arrival delay, upstream (last
    recorded pre-DG station) departure delay, train type, terminates_at_MDU, scheduled DG
    departure hour (sin/cos), day of week (DG date), and the train's mean past MDU delay.
59. **Train identity**: no one-hot of train numbers. `train_mean_past_delay` = mean MDU arrival
    delay of that train in the TRAINING dates only. For training rows it is leave-one-out
    (the row's own target excluded); trains with no other training run get the training-set
    mean. Test rows use the full training mean of their train.
60. **Split by DG date**: train = DG dates up to 2024-09-22, test = 2024-09-23 onwards (the
    last week of September plus the 1-2 Oct arrivals of journeys started on 29-30 Sept).
61. **Rows**: main analysis excludes the 39 runs flagged in the Step 1 audit (MDU exactly on
    time after DG departure >= 10 min late), from both train and test. Sensitivity S1 keeps
    them. Sensitivity S2 = main rows with every delay (target and delay features) capped at
    180 min. Note: the S1 flag is defined from the target, so the main analysis removes cases
    where the carry baseline would fail; S1 shows the effect.
62. **Methods, fixed, no tuning** (small data, no validation split):
    - B0 carry: predicted MDU delay = DG departure delay.
    - B1 linear regression (OLS) on the features of 58 (one-hot train type and weekday).
    - RF: RandomForestRegressor(n_estimators=500, min_samples_leaf=5, random_state=0).
    - XGB: XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,
      colsample_bytree=0.8, random_state=0, n_jobs=1).
63. **Metrics** on the test set: MAE, RMSE, R2, median absolute error; overall, terminating at
    MDU, through. 95% percentile bootstrap CIs over test rows (10,000 resamples, seed 2024).
    Comparison vs B0: paired bootstrap CI of the MAE difference (model - carry); "better"
    only when the whole CI is below 0. A train-clustered bootstrap of the same difference is
    reported as a check (rows of one train are correlated).

## REAL data Step 3: real-day replay (DG -> MDU)

64. **Headway CALIBRATED to 0 min** on the real corridor (`app/services/realdata/calibrate.py`,
    `backend/data/real/dg_mdu/calibration.json`). Headway 0 still enforces ONE train per block
    section (absolute block): a train may enter a section only after the train ahead has cleared
    the next station. Evidence: of the 75 recorded section pairs where both timestamps are
    recorded, none overlap; the smallest gaps are 0, 4 and 7 min, so 0 is the largest headway all
    of them respect (4 if the single gap-0 pair is set aside). The evidence is thin (75 pairs, mostly
    DG-ABI and ABI-KQN). Every optimizer run on a replay is repeated with headway 4 and the
    recommendation and ranking are reported side by side.
65. **Loops ASSUMED** (not public): DG 4, ABI 1, KQN 2, VDP 1, SDN 2, SER 1, KON 0, MDU 4. Rule
    (simulator, optimizer, safety check): when a train arrives at an intermediate station at most
    `loops` other trains may be standing there, so a train can be overtaken only where a loop is
    free and never at KON. Stations of the SIMULATED corridor have no loops value: the rule does
    not apply there and every simulated result is unchanged.
66. **Priorities ASSUMED** on the real corridor: PREMIUM (Vande Bharat, Tejas) 1, SUPERFAST 2,
    EXPRESS 3; objective weight = 4 - priority (3/2/1), the same mapping the simulated types
    already had (EXPRESS 1 -> 3, PASSENGER 2 -> 2, FREIGHT 3 -> 1). Labelled ASSUMED in the API and UI.
67. **Replay day** = every train whose DG date is that date; minutes from that date's midnight
    (may pass 24:00). Recorded times are kept; other stations get the scheduled time plus the delay
    interpolated on km between recorded neighbours (INTERPOLATED). The 39 flagged MDU arrivals
    (Step 1) are not used; a recorded time implying a run faster than the ASSUMED minimum running
    time from the previous recorded station is treated as unreliable and interpolated (4 times in
    the month).
68. **Repair of interpolated paths**: where two interpolated paths cross inside a single-track
    block, the overtaken train waits at the last loop station before the crossing until the other
    train has cleared the next block; where a train would enter a block before the leader cleared
    it, it waits at the block entrance (or the leader runs that block faster). Recorded times never
    change. The day's timetable (ESTIMATED passing times) is repaired the same way. 16 of 32 days
    then replay exactly through the simulator; on the others some recorded pairs stay unresolved
    (listed per day; e.g. two recorded DG departures inside one block's running time) and history
    is kept as recorded. Demo day 2024-09-12 (Thursday, 22 trains) replays exactly and contains the
    recorded overtake of 16343 by 22627.
69. **Hypothetical events on a replay**: movement before the first event (or accepted plan) stays
    exactly as recorded (trips entered before it are fixed); after it, trains are simulated using
    their recorded (or interpolated) running and dwell times as the unimpeded times, so recorded
    slack is kept; trains enter DG at their recorded times. Labelled "HYPOTHETICAL on a real
    recorded day".
70. **Knowledge on a replay**: detection and re-planning at clock `at` see the movement up to `at`,
    then the (repaired) timetable with each train's current delay carried forward; before DG the
    last recorded upstream delay is ASSUMED known. Strategy delays on a replay are minutes added to
    that expected movement, not delays against the timetable. Conflicts resting on an interpolated
    or ESTIMATED time are shown as uncertain, not as alerts. The SIMULATED-trained ML models are
    not applied to real data.
71. **Correction found while building Step 3**: train 20627 ("Ms Ncj Vb Express") is a Vande
    Bharat and is now typed PREMIUM (it was SUPERFAST). Step 2 was re-run with the same
    pre-registered design: main XGBoost MAE 4.18 vs carry 4.94 (difference -0.76, 95% CI
    [-1.53, -0.04]; train-clustered [-1.61, +0.18]); before the fix -0.74 [-1.50, -0.02] and
    [-1.60, +0.18]. The conclusion is unchanged.

## Phase 7: explainable recommendations (template rules)

72. **No LLM, no hand-typed numbers.** Every sentence is a template in
    `app/services/explainer/` filled only from values in the same API payload (strategy rows,
    the structured fields next to each sentence, the network the run used). `tests/test_explainer.py`
    checks that every number and HH:MM in every generated sentence appears in that payload.
73. **ML drivers explain the model's score, not a cause.** Each top SHAP driver becomes
    "Model risk raised by: ..." / "Model risk lowered by: ..." from a feature-to-text table
    (one template per model feature; the feature VALUE is put in words, the SHAP number never is).
    Driver sentences never say "because". The Reason line comes from the rule-based detector (a
    real interval clash) and may say "because". On REAL replay days the ML models are off and
    the model note says so; no drivers are shown.
74. **Reason** = the conflict the plan answers: CRITICAL before WARNING, then the soonest.
75. **Why not the others?** One line per other row (baselines included) from its own metrics:
    weighted delay and the difference to the recommended one; on a tie, the action count or the
    fixed tie order HOLD, REROUTE, RESEQUENCE, COMBINED (the order the recommendation uses);
    no plan found -> the CP-SAT status; strategies not offered -> the reason.
76. **Constraints respected** is listed only when the replay of the recommended plan has 0
    violations of `find_violations` (headway, capacity, minimum running time, closures, no early
    departure; plus loops on the REAL corridor). Otherwise the card says how many it breaks.
77. **Assumptions this depends on** lists the values read from the network, each with its item
    number here: SIMULATED - headway per section (1), priority weights (24), minimum running
    time (3); REAL - headway CALIBRATED (64), loops (65), priorities (66), minimum running time
    (50), knowledge from the forecast (70).
78. **Confidence**: the word "optimal" appears only when CP-SAT returned OPTIMAL ("optimal for
    that strategy's model", item 26); any other status reads "a valid plan, not proven to be
    the best within the solver's time limit". On REAL replay days it adds the headway-4
    sensitivity result: same recommendation (and ranking) or what differs.
