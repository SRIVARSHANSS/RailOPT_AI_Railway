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
