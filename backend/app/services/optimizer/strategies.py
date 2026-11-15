"""Strategies and baselines, compared on the SAME footing: a simulator replay.

Each CP-SAT solution becomes controller holds + route overrides and is
replayed through `simulate()` (rng=None). Every reported number (delays,
weighted delay, throughput, violations) comes from that replay, never from
the solver. Baselines are plain simulator runs:

* NO_REPLANNING      - first come, first served at the signals
* PRIORITY_DISPATCH  - when several trains wait, the highest priority enters first

All results are SIMULATED. The output is advice for a human controller.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.network import RailNetwork, format_time
from app.services.optimizer import config
from app.services.optimizer.solver import STRATEGIES, SolveResult, solve
from app.services.simulator import Disruption, SimResult, find_violations, simulate

SIMULATED_LABEL = "SIMULATED - sample corridor, not real railway data"


@dataclass
class StrategyResult:
    name: str
    kind: str                         # "baseline" | "strategy"
    status: str                       # BASELINE | OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN | MODEL_INVALID
    solve_seconds: float | None = None
    objective: int | None = None      # solver objective (weighted delay of modelled trips + reroute penalty)
    message: str = ""
    actions: list[str] = field(default_factory=list)
    holds: dict = field(default_factory=dict)
    route_overrides: dict = field(default_factory=dict)
    replay: SimResult | None = None
    delays: dict[str, int] = field(default_factory=dict)
    total_delay: int | None = None
    weighted_delay: int | None = None
    throughput: float | None = None
    violations: list[str] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)   # solver vs replay disagreements
    solve: SolveResult | None = None
    label: str = SIMULATED_LABEL

    @property
    def is_proven_optimal(self) -> bool:
        return self.status == "OPTIMAL"


def weighted_delay(net: RailNetwork, delays: dict[str, int]) -> int:
    return sum(config.PRIORITY_WEIGHTS[net.trains[t].train_type] * d for t, d in delays.items())


def _score(net, res: StrategyResult, replay: SimResult, known) -> StrategyResult:
    res.replay = replay
    res.delays = {t: replay.final_delay(t) for t in sorted(net.schedules)}
    res.total_delay = sum(res.delays.values())
    res.weighted_delay = weighted_delay(net, res.delays)
    res.throughput = replay.metrics()["throughput_trains_per_hour"]
    res.violations = find_violations(net, replay, known)
    return res


def run_baseline(net: RailNetwork, known: list[Disruption], dispatch: str,
                 base_holds: dict | None = None, base_overrides: dict | None = None) -> StrategyResult:
    """With an accepted plan, the baseline keeps that plan (no NEW re-planning)."""
    name = {"fcfs": "NO_REPLANNING", "priority": "PRIORITY_DISPATCH"}[dispatch]
    res = StrategyResult(name, "baseline", "BASELINE",
                         message="keeps the accepted plan, no new re-planning" if (base_holds or base_overrides) else "")
    replay = simulate(net, known, route_overrides=base_overrides, holds=base_holds, dispatch=dispatch)
    return _score(net, res, replay, known)


def run_strategy(net: RailNetwork, state_time: int, known: list[Disruption], strategy: str,
                 risk_buffers: dict | None = None, **solve_kwargs) -> StrategyResult:
    """solve_kwargs may carry base_holds / base_overrides (the accepted plan)."""
    sol = solve(net, state_time, known, strategy, risk_buffers=risk_buffers, **solve_kwargs)
    res = StrategyResult(strategy, "strategy", sol.status, sol.solve_seconds, sol.objective, sol.message,
                         solve=sol)
    if not sol.has_solution:
        return res
    res.holds, res.route_overrides = sol.holds, sol.route_overrides
    replay = simulate(net, known, route_overrides=res.route_overrides, holds=res.holds)
    _score(net, res, replay, known)

    for t in sol.trips:
        occ = replay.occupancy(t.train_id, t.section_id)
        if (occ.entry, occ.exit) != (t.entry, t.exit):
            res.mismatches.append(f"{t.train_id} {t.section_id}: solver {format_time(t.entry)}-"
                                  f"{format_time(t.exit)}, replay {format_time(occ.entry)}-{format_time(occ.exit)}")
    res.actions = describe_actions(net, sol, replay)
    return res


def describe_actions(net: RailNetwork, sol: SolveResult, replay: SimResult) -> list[str]:
    """Plain-language controller actions, from the replay (holds that really bite)."""
    actions = []
    for t in sol.trips:
        sec = net.sections[t.section_id]
        if t.rerouted:
            actions.append(f"reroute {t.train_id} {sec.from_station}->{sec.to_station} via {t.section_id}")
        occ = replay.occupancy(t.train_id, t.section_id)
        if occ.entry > occ.requested:
            actions.append(f"hold {t.train_id} at {sec.from_station} until {format_time(occ.entry)} "
                           f"(ready {format_time(occ.requested)}, +{occ.entry - occ.requested} min)")
    return actions


def compare(net: RailNetwork, state_time: int, known: list[Disruption],
            risk_buffers: dict | None = None, base_holds: dict | None = None,
            base_overrides: dict | None = None, **solve_kwargs) -> list[StrategyResult]:
    """Both baselines and all four strategies, each scored on its replay.

    With an accepted plan (base_*), trips already started stay as that plan made them;
    the baselines carry the plan on, the strategies re-plan the future."""
    solve_kwargs.update(base_holds=base_holds, base_overrides=base_overrides)
    results = [run_baseline(net, known, "fcfs", base_holds, base_overrides),
               run_baseline(net, known, "priority", base_holds, base_overrides)]
    results += [run_strategy(net, state_time, known, s.name, risk_buffers, **solve_kwargs) for s in STRATEGIES]
    return results


def risk_buffers_from_predictor(net: RailNetwork, state_time: int, known: list[Disruption],
                                predictor=None) -> dict[tuple[str, str], int]:
    """Optional ML input (off by default): +RISK_BUFFER_MIN headway on trips the
    conflict model flags at its recall >= 0.80 threshold."""
    from app.services.datagen import plan_features
    from app.services.predictor import get_predictor

    predictor = predictor or get_predictor()
    disruptions = [d for d in known if not d.event_id.startswith("SD_")]
    first = min(disruptions, key=lambda d: d.start) if disruptions else None
    if first is None:
        return {}
    buffers = {}
    for row in plan_features(net, state_time, known, first):
        if predictor.predict(row)["conflict_predicted"]:
            buffers[(row["train_id"], row["section_id"])] = config.RISK_BUFFER_MIN
    return buffers
