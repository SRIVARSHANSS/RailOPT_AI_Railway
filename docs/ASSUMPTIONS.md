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
    does not wait before the flagged trip (same stations, either line).
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
