"""Phase 10 evaluation core: scenarios, methods, replays and per-scenario metrics.

Scenarios come from the Phase 2 generator logic (`sample_run`) with a NEW seed, on the
full-day timetable (12 trains), 1-3 disruptions each plus 0-5 min starting delays.

Knowledge is time-aware (same rule as the API):
* starting delays: known from the start (as in the Phase 2 generator);
* STOPPAGE / DELAY: known at their start time;
* TRACK_UNAVAILABLE (planned maintenance): posted 30 min before it starts, or at 06:00
  if that is later than the start minus 30 (docs/ASSUMPTIONS.md).

Methods, all on the SAME scenarios:
* NO_REPLANNING      first come, first served at the signals
* PRIORITY_DISPATCH  the waiting train with the highest priority enters first
* SINGLE_SHOT        COMBINED (CP-SAT) once, when the first disruption becomes known
* DYNAMIC            COMBINED again every time a new event becomes known, on top of the
                     current plan (started trips fixed, 120-min rolling horizon)
* DYNAMIC_ML         DYNAMIC + ML risk buffers (+1 min headway on trips the conflict model
                     flags at its recall >= 0.80 threshold): the with/without-ML ablation

A RailOpt method adopts the solver's plan whenever the solve returns one (OPTIMAL or
FEASIBLE); otherwise the plan in force is kept. Every metric comes from a simulator replay
of the final plan with ALL events, never from the solver. Settings:
* deterministic  one replay, rng=None
* robustness     the same fixed plans replayed under the Phase 2 random variability,
                 REPLAYS seeded replays per scenario (identical seeds for every method)

Everything here is SIMULATED. RailOpt advises a human controller; it controls nothing.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from app.services.datagen.generator import TIMETABLE, RunSample, sample_run
from app.services.network import RailNetwork, load_network, parse_time
from app.services.optimizer import config
from app.services.optimizer.solver import solve
from app.services.optimizer.strategies import risk_buffers_from_predictor
from app.services.simulator import Disruption, SimResult, find_violations, simulate

SIMULATED_NOTE = "SIMULATED - sample corridor, synthetic disruptions, not real railway data"
METHODS = ["NO_REPLANNING", "PRIORITY_DISPATCH", "SINGLE_SHOT", "DYNAMIC", "DYNAMIC_ML"]
RAILOPT = ["SINGLE_SHOT", "DYNAMIC", "DYNAMIC_ML"]
SETTINGS = ["deterministic", "robustness"]
METRICS = ["avg_delay_min", "total_delay_min", "weighted_delay", "max_delay_min",
           "throughput_trains_per_hour", "trains_waited", "total_wait_min"]
REPLAYS = 5
TRAINING_SEED, TRAINING_RUNS = 42, 3000          # Phase 2/4 training data (CLAUDE.md)
DAY_START = parse_time("06:00")
CLOSURE_NOTICE_MIN = 30


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------
def make_scenarios(n: int, seed: int, net: RailNetwork | None = None, prefix: str = "V") -> list[RunSample]:
    """Same sampling as the Phase 2 generator (`iter_runs`): one child rng per scenario."""
    net = net or load_network(timetable=TIMETABLE)
    master = random.Random(seed)
    return [sample_run(net, f"{prefix}{i:04d}", random.Random(master.getrandbits(64))) for i in range(1, n + 1)]


def fingerprint(s: RunSample) -> tuple:
    """Identity of a scenario's content (ids excluded)."""
    return (tuple((d.train_id, d.location, d.start, d.duration) for d in s.starting_delays),
            tuple((d.event_type, d.train_id, d.location, d.start, d.duration) for d in s.disruptions))


def training_fingerprints(net: RailNetwork | None = None) -> set[tuple]:
    """The 3000 training scenarios (seed 42), rebuilt with the generator's own rng sequence."""
    return {fingerprint(s) for s in make_scenarios(TRAINING_RUNS, TRAINING_SEED, net, prefix="R")}


def known_from(d: Disruption) -> int:
    if d.event_id.startswith("SD_"):
        return -1                                          # starting delays: known from the start
    if d.event_type == "TRACK_UNAVAILABLE":
        return max(DAY_START, d.start - CLOSURE_NOTICE_MIN)
    return d.start


def known_at(s: RunSample, t: int) -> list[Disruption]:
    return [d for d in s.all_events if known_from(d) <= t]


def decision_points(s: RunSample) -> list[int]:
    return sorted({known_from(d) for d in s.disruptions})


# ---------------------------------------------------------------------------
# methods -> plans
# ---------------------------------------------------------------------------
@dataclass
class Plan:
    method: str
    dispatch: str = "fcfs"
    holds: dict = field(default_factory=dict)
    overrides: dict = field(default_factory=dict)
    solves: list[dict] = field(default_factory=list)       # one per solver call
    guarantee: dict | None = None                          # SINGLE_SHOT only


def weighted(net: RailNetwork, sim: SimResult) -> int:
    return sum(config.PRIORITY_WEIGHTS[net.trains[t].train_type] * sim.final_delay(t) for t in net.schedules)


def _solve(net, t, known, buffers, holds, overrides) -> tuple[dict, object]:
    started = time.perf_counter()
    sol = solve(net, t, known, "COMBINED", risk_buffers=buffers,
                base_holds=holds or None, base_overrides=overrides or None)
    info = {"at": t, "status": sol.status, "seconds": time.perf_counter() - started,
            "solver_seconds": sol.solve_seconds, "known": len(known), "buffers": len(buffers or {}),
            "adopted": sol.has_solution}
    return info, sol


def plan_for(net: RailNetwork, s: RunSample, method: str, predictor=None) -> Plan:
    if method == "NO_REPLANNING":
        return Plan(method)
    if method == "PRIORITY_DISPATCH":
        return Plan(method, dispatch="priority")
    points = decision_points(s)
    plan = Plan(method)
    if method == "SINGLE_SHOT":
        points = points[:1]
    for t in points:
        known = known_at(s, t)
        buffers = risk_buffers_from_predictor(net, t, known, predictor) if method == "DYNAMIC_ML" else None
        info, sol = _solve(net, t, known, buffers, plan.holds, plan.overrides)
        plan.solves.append(info)
        if sol.has_solution:
            plan.holds, plan.overrides = sol.holds, sol.route_overrides
    if method == "SINGLE_SHOT":
        plan.guarantee = single_shot_check(net, s, plan, points[0])
    return plan


def single_shot_check(net: RailNetwork, s: RunSample, plan: Plan, t: int) -> dict:
    """The by-construction claim: on the events known when it solved, an OPTIMAL single-shot
    plan is never worse (weighted delay) than no re-planning."""
    known = known_at(s, t)
    ss = weighted(net, simulate(net, known, route_overrides=plan.overrides or None, holds=plan.holds or None))
    fcfs = weighted(net, simulate(net, known))
    return {"status": plan.solves[0]["status"], "at": t, "weighted_known": ss, "fcfs_weighted_known": fcfs,
            "worse_on_known": ss > fcfs}


# ---------------------------------------------------------------------------
# replays and metrics
# ---------------------------------------------------------------------------
def replay(net: RailNetwork, s: RunSample, plan: Plan, rng: random.Random | None = None) -> SimResult:
    return simulate(net, s.all_events, route_overrides=plan.overrides or None, holds=plan.holds or None,
                    rng=rng, dispatch=plan.dispatch)


def metrics(net: RailNetwork, sim: SimResult) -> dict:
    delays = [sim.final_delay(t) for t in sorted(net.schedules)]
    return {
        "avg_delay_min": sum(delays) / len(delays),
        "total_delay_min": sum(delays),
        "weighted_delay": weighted(net, sim),
        "max_delay_min": max(delays),
        "throughput_trains_per_hour": sim.metrics()["throughput_trains_per_hour"],
        "trains_waited": len({o.train_id for o in sim.occupancies if o.wait > 0}),
        "total_wait_min": sum(o.wait for o in sim.occupancies),
    }


def replay_seed(seed: int, scenario_index: int, r: int) -> int:
    """Common random numbers: the same seeds for every method of a scenario."""
    return random.Random(f"{seed}/{scenario_index}/{r}").getrandbits(64)


def evaluate_scenario(net: RailNetwork, s: RunSample, index: int, seed: int, predictor=None,
                      methods: list[str] = METHODS, replays: int = REPLAYS) -> tuple[list[dict], list[Plan]]:
    """Rows (one per method x setting) for one scenario. Asserts zero violations in every replay."""
    rows, plans = [], []
    base = {"scenario_id": s.run_id, "scenario_index": index, "n_disruptions": len(s.disruptions),
            "disruption_types": "+".join(d.event_type for d in s.disruptions), "label": "SIMULATED"}
    for method in methods:
        plan = plan_for(net, s, method, predictor)
        plans.append(plan)
        solve_cols = {"n_solves": len(plan.solves),
                      "solve_s_total": round(sum(x["seconds"] for x in plan.solves), 4),
                      "n_optimal": sum(x["status"] == "OPTIMAL" for x in plan.solves),
                      "n_feasible": sum(x["status"] == "FEASIBLE" for x in plan.solves),
                      "n_buffers": sum(x["buffers"] for x in plan.solves)}

        det = replay(net, s, plan)
        problems = find_violations(net, det, s.all_events)
        assert not problems, (s.run_id, method, "deterministic", problems)
        rows.append({**base, "method": method, "setting": "deterministic", "replays": 1,
                     **metrics(net, det), **solve_cols})

        acc = {k: 0.0 for k in METRICS}
        for r in range(replays):
            sim = replay(net, s, plan, random.Random(replay_seed(seed, index, r)))
            problems = find_violations(net, sim, s.all_events)
            assert not problems, (s.run_id, method, f"replay {r}", problems)
            for k, v in metrics(net, sim).items():
                acc[k] += v / replays
        rows.append({**base, "method": method, "setting": "robustness", "replays": replays, **acc, **solve_cols})
    return rows, plans
