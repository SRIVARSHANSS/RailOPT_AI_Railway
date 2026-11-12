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
      planned trip. With variability the train may not be there at that
      minute; the simulator then ignores it (counted in the dataset card).
    - DELAY: random train, at one of its stations, at its planned departure.
    - TRACK_UNAVAILABLE: random main section, start uniform in 06:00-14:00,
      but never on a section from a stoppage's start until 30 min after it
      ends. The model has no rule for a closure that begins while a stopped
      train is stranded inside.
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
