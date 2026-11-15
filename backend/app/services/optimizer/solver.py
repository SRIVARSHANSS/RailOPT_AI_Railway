"""CP-SAT re-planning model (Phase 5).

Given the network, the state time and the events known then, decide for
every trip in the rolling horizon when it enters its section (and, where
allowed, which of the parallel sections it uses), so that the priority-
weighted arrival delay is as small as possible.

* History comes from the no-re-planning simulation of the known events:
  every trip entered at or before state time is fixed (this includes trains
  inside a section at state time, with any known stoppage).
* A trip is a decision if `project_plan` has it starting within
  HORIZON_MIN of state time. Later trips are not modelled; in the replay
  they run first come, first served.
* Each decision trip is an interval [entry, exit + headway (+ risk buffer)).
  1-track sections: NoOverlap. Multi-track sections: Cumulative with
  capacity = tracks. Trip [entry, exit) must not overlap a closure.
* entry >= previous exit + timetabled dwell, >= scheduled departure, and
  >= the end of a known DELAY at that station (the simulator's rules).

The solver's answer is only a proposal: `strategies.py` replays it through
the simulator and every reported metric comes from that replay.
All results are SIMULATED.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from app.services.conflicts import project_plan
from app.services.network import RailNetwork
from app.services.optimizer import config
from app.services.simulator import Disruption, SimResult, simulate
from app.services.simulator.engine import _running_time, next_departure

STATUS_NAMES = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}


@dataclass(frozen=True)
class StrategySpec:
    name: str
    fixed_order: bool      # keep timetable order on every section
    allow_reroute: bool    # may use a parallel section (S_BC_ALT)
    description: str


STRATEGIES = [
    StrategySpec("HOLD", True, False, "keep timetable order, hold trains, no reroute"),
    StrategySpec("REROUTE", True, True, "reroute allowed, order otherwise fixed"),
    StrategySpec("RESEQUENCE", False, False, "free order on every section, no reroute"),
    StrategySpec("COMBINED", False, True, "free order + reroute"),
]
STRATEGY_BY_NAME = {s.name: s for s in STRATEGIES}


@dataclass
class PlannedTrip:
    train_id: str
    stop_index: int
    section_id: str
    entry: int
    exit: int
    rerouted: bool


@dataclass
class SolveResult:
    strategy: str
    status: str                       # OPTIMAL | FEASIBLE | INFEASIBLE | MODEL_INVALID | UNKNOWN
    solve_seconds: float
    objective: int | None = None
    trips: list[PlannedTrip] = field(default_factory=list)       # decided by the solver
    fixed: list[PlannedTrip] = field(default_factory=list)       # already started at state time
    message: str = ""

    @property
    def has_solution(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")

    @property
    def holds(self) -> dict[tuple[str, str], int]:
        """Controller plan for the replay: started trips at their recorded entry, plus the decisions."""
        return {(t.train_id, t.section_id): t.entry for t in self.fixed + self.trips}

    @property
    def route_overrides(self) -> dict[tuple[str, str], str]:
        """Reroutes already under way (from an accepted plan) plus new ones."""
        return {(t.train_id, self._from_station[t.section_id]): t.section_id
                for t in self.fixed + self.trips if t.rerouted}

    _from_station: dict[str, str] = field(default_factory=dict, repr=False)


def solve(net: RailNetwork, state_time: int, known_events: list[Disruption] | None,
          strategy: str | StrategySpec,
          risk_buffers: dict[tuple[str, str], int] | None = None,
          horizon_min: int = config.HORIZON_MIN,
          time_limit_s: float = config.TIME_LIMIT_S,
          base_holds: dict[tuple[str, str], int] | None = None,
          base_overrides: dict[tuple[str, str], str] | None = None) -> SolveResult:
    """base_holds / base_overrides: the plan currently accepted. History (every trip
    started at state time, e.g. a reroute in progress) is simulated WITH it and fixed;
    only future trips are decided again."""
    spec = STRATEGY_BY_NAME[strategy] if isinstance(strategy, str) else strategy
    known = list(known_events or [])
    risk_buffers = dict(risk_buffers or {})
    started = time.perf_counter()

    history: SimResult = simulate(net, known, route_overrides=base_overrides, holds=base_holds)
    fixed: list[PlannedTrip] = []
    plan = project_plan(net, state_time, known)
    lo, hi = state_time, state_time + config.PLANNING_WINDOW_MIN
    closures = [d for d in known if d.event_type == "TRACK_UNAVAILABLE"]

    m = cp_model.CpModel()
    by_section: dict[str, list[tuple]] = {}      # section -> [(interval incl. headway, sched_key, entry, presence)]
    objective_terms = []
    decision: list[dict] = []                    # one per decision trip

    for train_id, stops in net.schedules.items():
        train = net.trains[train_id]
        occs = {o.section_id: o for o in history.occupancies if o.train_id == train_id}
        prev_exit = None          # int (fixed) or IntVar (decision)
        last_trip = None
        for i in range(len(stops) - 1):
            here, nxt = stops[i], stops[i + 1]
            primary = net.primary_section(here.station, nxt.station)
            actual = next((occs[s.section_id] for s in net.sections_between(here.station, nxt.station)
                           if s.section_id in occs), None)
            if actual is not None and actual.entry <= state_time:
                # history: fixed trip, still blocks its track until exit + headway
                sec = net.sections[actual.section_id]
                end = actual.exit + sec.min_headway_min
                if end > state_time:
                    iv = m.NewIntervalVar(actual.entry, end - actual.entry, end, f"fixed_{train_id}_{i}")
                    by_section.setdefault(sec.section_id, []).append((iv, None, actual.entry, None))
                fixed.append(PlannedTrip(train_id, i, sec.section_id, actual.entry, actual.exit,
                                         sec.section_id != primary.section_id))
                prev_exit = actual.exit
                continue
            if plan.trip(train_id, primary.section_id).entry > state_time + horizon_min:
                break                                           # beyond the rolling horizon

            options = [s for s in net.sections_between(here.station, nxt.station) if s.status != "closed"]
            if not spec.allow_reroute:
                options = [primary]
            entry = m.NewIntVar(lo, hi, f"entry_{train_id}_{i}")
            exit_ = m.NewIntVar(lo, hi, f"exit_{train_id}_{i}")

            # ready rules: scheduled departure, dwell after the previous trip, known DELAY
            m.Add(entry >= here.sched_dep)
            for d in known:
                if d.event_type == "DELAY" and d.train_id == train_id and d.location == here.station:
                    m.Add(entry >= d.start + d.duration)
            if prev_exit is not None:
                if isinstance(prev_exit, int):
                    m.Add(entry >= next_departure(here, prev_exit))
                else:
                    dwell = (here.sched_dep - here.sched_arr) if here.sched_arr is not None else 0
                    m.Add(entry >= prev_exit + dwell)

            presences = {}
            for sec in options:
                run = _running_time(net, sec, here, nxt)
                p = m.NewBoolVar(f"use_{train_id}_{i}_{sec.section_id}")
                if len(options) == 1:
                    m.Add(p == 1)
                presences[sec.section_id] = p
                block = sec.min_headway_min + risk_buffers.get((train_id, sec.section_id), 0)
                end = m.NewIntVar(lo, hi + run + block, f"end_{train_id}_{i}_{sec.section_id}")
                iv = m.NewOptionalIntervalVar(entry, run + block, end, p, f"iv_{train_id}_{i}_{sec.section_id}")
                m.Add(exit_ == entry + run).OnlyEnforceIf(p)
                sched_key = (here.sched_dep, train.priority, train_id)
                by_section.setdefault(sec.section_id, []).append((iv, sched_key, entry, p))
                for c in closures:
                    if c.location == sec.section_id:
                        trip_iv = m.NewOptionalFixedSizeIntervalVar(entry, run, p, f"trip_{train_id}_{i}_{sec.section_id}")
                        closed = m.NewIntervalVar(c.start, c.duration, c.end, f"closed_{c.event_id}_{train_id}_{i}")
                        m.AddNoOverlap([trip_iv, closed])
                if sec.section_id != primary.section_id and len(options) > 1:
                    objective_terms.append(config.REROUTE_PENALTY * p)
            if len(options) > 1:
                m.AddExactlyOne(list(presences.values()))
            decision.append({"train_id": train_id, "i": i, "entry": entry, "exit": exit_,
                             "presences": presences, "primary": primary.section_id})
            prev_exit = exit_
            last_trip = (i, exit_)

        if last_trip is not None:
            i, exit_ = last_trip
            late = m.NewIntVar(0, config.PLANNING_WINDOW_MIN * 2, f"late_{train_id}")
            m.AddMaxEquality(late, [0, exit_ - stops[i + 1].sched_arr])
            objective_terms.append(config.PRIORITY_WEIGHTS[train.train_type] * late)

    # capacity
    for sid, items in by_section.items():
        sec = net.sections[sid]
        intervals = [it[0] for it in items]
        if sec.tracks == 1:
            m.AddNoOverlap(intervals)
        else:
            m.AddCumulative(intervals, [1] * len(intervals), sec.tracks)
        if spec.fixed_order:
            ordered = sorted((it for it in items if it[1] is not None), key=lambda it: it[1])
            for a in range(len(ordered)):
                for b in range(a + 1, len(ordered)):
                    _, _, ea, pa = ordered[a]
                    _, _, eb, pb = ordered[b]
                    m.Add(eb >= ea).OnlyEnforceIf([pa, pb])

    m.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = config.NUM_WORKERS
    solver.parameters.random_seed = config.RANDOM_SEED
    code = solver.Solve(m)
    status = STATUS_NAMES.get(code, str(code))
    result = SolveResult(spec.name, status, round(time.perf_counter() - started, 3), fixed=fixed,
                         _from_station={s.section_id: s.from_station for s in net.sections.values()})

    if status not in ("OPTIMAL", "FEASIBLE"):
        result.message = {
            "INFEASIBLE": "No schedule satisfies the constraints within the planning window "
                          f"({config.PLANNING_WINDOW_MIN} min after state time) for this strategy.",
            "UNKNOWN": f"No solution found within the {time_limit_s} s time limit.",
            "MODEL_INVALID": "The model is invalid (please report this as a bug).",
        }.get(status, status)
        return result

    result.objective = int(solver.ObjectiveValue())
    if status == "FEASIBLE":
        result.message = (f"Time limit of {time_limit_s} s reached: the schedule is feasible "
                          "but not proven optimal.")
    for d in decision:
        chosen = next(sid for sid, p in d["presences"].items() if solver.Value(p))
        result.trips.append(PlannedTrip(d["train_id"], d["i"], chosen, solver.Value(d["entry"]),
                                        solver.Value(d["exit"]), chosen != d["primary"]))
    result.trips.sort(key=lambda t: (t.entry, t.section_id))
    return result
