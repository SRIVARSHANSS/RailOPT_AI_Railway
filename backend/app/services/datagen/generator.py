"""Synthetic training-data generator (Phase 2).

Each run is one SIMULATED day on the full-day timetable (12 trains):

1. Every train gets a random starting delay of 0-5 min (a DELAY at its
   origin). These are treated as known to the controller.
2. 1-3 random disruptions (STOPPAGE, DELAY or TRACK_UNAVAILABLE), each
   5-30 min long.
3. State time = the first disruption's start. Only what is known at that
   moment (the timetable, the starting delays and the disruptions that have
   started) goes into `project_plan` / `detect_conflicts`, which produce the
   features. Later disruptions are NOT visible to the features.
4. The labels come from the simulator run WITH random running-time and
   dwell variability and ALL disruptions, with no re-planning.

One row per (run, train, upcoming section) that the plan has the train
entering after state time. `run_id` is kept on every row so Phase 4 can
split by run, never by random rows.

All data produced here is SIMULATED. No real railway data is used.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import pandas as pd

from app.services.conflicts import detect_conflicts, project_plan
from app.services.network import RailNetwork, load_network, parse_time
from app.services.simulator import DEFAULT_VARIABILITY, Disruption, SimResult, simulate

SIMULATED_NOTE = "SIMULATED data - sample corridor, synthetic disruptions, not real railway records"

TIMETABLE = "full_day"
SERVICE_DAY = (parse_time("06:00"), parse_time("14:00"))
DISRUPTION_TYPES = ("STOPPAGE", "DELAY", "TRACK_UNAVAILABLE")
DISRUPTIONS_PER_RUN = (1, 3)
DISRUPTION_DURATION_MIN = (5, 30)
STARTING_DELAY_MIN = (0, 5)
NO_PRECEDING_GAP = 999          # headway_gap_min when no train is ahead on the section

FEATURES = [
    "train_type", "priority", "current_delay_min", "time_to_section_min",
    "section_id", "section_tracks", "headway_gap_min",
    "preceding_train_type", "preceding_train_priority", "preceding_train_delay_min",
    "section_occupied_at_planned_entry", "trains_ahead_within_30min",
    "disruption_type", "disruption_duration_min", "hour_of_day", "rule_flags_conflict",
]
BASELINES = ["baseline_projected_delay_min"]   # comparison only, never a model feature
LABELS = ["label_conflict", "label_wait_min", "label_delay_min"]
COLUMNS = ["run_id", *FEATURES, *BASELINES, *LABELS]

GENERATOR_RANGES = {
    "timetable": TIMETABLE,
    "service_day": ["06:00", "14:00"],
    "disruption_types": list(DISRUPTION_TYPES),
    "disruptions_per_run": list(DISRUPTIONS_PER_RUN),
    "disruption_duration_min": list(DISRUPTION_DURATION_MIN),
    "starting_delay_min": list(STARTING_DELAY_MIN),
    "no_preceding_train_gap_value": NO_PRECEDING_GAP,
    "closure_rule": "never on a section that has a stoppage in the same run",
    "stoppage_rule": "if variability moves the train, applied at actual entry + planned offset",
}


@dataclass
class RunSample:
    run_id: str
    starting_delays: list[Disruption]   # known to the controller
    disruptions: list[Disruption]       # sorted by start; the first one sets state time

    @property
    def state_time(self) -> int:
        return self.disruptions[0].start

    @property
    def known_events(self) -> list[Disruption]:
        return self.starting_delays + [d for d in self.disruptions if d.start <= self.state_time]

    @property
    def all_events(self) -> list[Disruption]:
        return self.starting_delays + self.disruptions


# ---------------------------------------------------------------------------
# sampling one run
# ---------------------------------------------------------------------------
def sample_run(net: RailNetwork, run_id: str, rng: random.Random) -> RunSample:
    starting = []
    for train_id in sorted(net.schedules):
        d = rng.randint(*STARTING_DELAY_MIN)
        if d > 0:
            origin = net.schedules[train_id][0]
            starting.append(Disruption(f"SD_{train_id}", "DELAY", train_id, origin.station, origin.sched_dep, d))

    # planned times with the starting delays, used to place stoppages and delays
    base = project_plan(net, 0, starting)
    open_sections = sorted(s.section_id for s in net.sections.values() if s.status == "open")
    trains = sorted(net.schedules)

    drawn = []
    for _ in range(rng.randint(*DISRUPTIONS_PER_RUN)):
        kind = rng.choice(DISRUPTION_TYPES)
        duration = rng.randint(*DISRUPTION_DURATION_MIN)
        if kind == "STOPPAGE":
            train_id = rng.choice(trains)
            trip = rng.choice([t for t in base.trips if t.train_id == train_id])
            start = rng.randint(trip.entry + 1, max(trip.entry + 1, trip.exit - 1))
            drawn.append((start, kind, train_id, trip.section_id, duration, start - trip.entry))
        elif kind == "DELAY":
            train_id = rng.choice(trains)
            trip = rng.choice([t for t in base.trips if t.train_id == train_id])
            station = net.sections[trip.section_id].from_station
            drawn.append((trip.entry, kind, train_id, station, duration, None))
        else:
            drawn.append((None, kind, None, None, duration, None))     # placed below

    # Closures are placed last, never on a section that has a stoppage in the same
    # run: the model has no rule for a closure that starts while a stopped train
    # is stranded inside, and variability can move a stoppage by any amount
    # (see docs/ASSUMPTIONS.md). At most 2 stoppages + 1 closure per run and 3
    # open sections, so a free section always exists.
    stopped_sections = {loc for _s, kind, _t, loc, _d, _o in drawn if kind == "STOPPAGE"}
    closable = [sid for sid in open_sections if sid not in stopped_sections]
    for k, (_start, kind, train, _loc, dur, offset) in enumerate(drawn):
        if kind == "TRACK_UNAVAILABLE":
            drawn[k] = (rng.randint(*SERVICE_DAY), kind, train, rng.choice(closable), dur, offset)

    drawn.sort(key=lambda d: d[0])
    # offset_min: how far into its planned trip a stoppage starts, so the simulator
    # can re-place it if random variability moves the train
    disruptions = [Disruption(f"E{i}", kind, train, loc, start, dur, offset_min=offset)
                   for i, (start, kind, train, loc, dur, offset) in enumerate(drawn, start=1)]
    return RunSample(run_id, starting, disruptions)


def simulate_run(net: RailNetwork, sample: RunSample, rng: random.Random) -> SimResult:
    """The 'actual' outcome: all disruptions, random variability, no re-planning."""
    return simulate(net, sample.all_events, rng=rng)


# ---------------------------------------------------------------------------
# features (known at state time) and rows for one run
# ---------------------------------------------------------------------------
def plan_features(net: RailNetwork, state_time: int, known_events: list[Disruption],
                  first: Disruption, route_overrides: dict | None = None,
                  holds: dict | None = None) -> list[dict]:
    """Feature rows for every (train, section) the plan has the train entering
    after `state_time`, using only what is known then. Usable on a live
    scenario: no simulation outcome is needed.

    Each row also carries `train_id` (for lookups; not a model feature) and
    the non-ML baseline `baseline_projected_delay_min`: the deterministic
    simulator (rng=None) run on the known events, i.e. what the rules plus
    the simulator predict without ML. It is a comparison column only, never
    a model feature.

    route_overrides / holds (optional, default none = the training setting): build the
    features on the projection of an accepted plan (used by the Phase 10b trigger variant).
    """
    plan = project_plan(net, state_time, known_events, route_overrides, holds)
    flagged = {(c.later, c.section_id) for c in detect_conflicts(net, plan)}
    projection = simulate(net, known_events, route_overrides=route_overrides, holds=holds)   # rng=None

    # planned delay of each trip = planned entry - timetabled departure from that section's start
    delay_at: dict[tuple[str, str], int] = {}
    for train_id, stops in net.schedules.items():
        trips = sorted((t for t in plan.trips if t.train_id == train_id), key=lambda t: t.entry)
        for stop, trip in zip(stops, trips):
            delay_at[(train_id, trip.section_id)] = trip.entry - stop.sched_dep

    by_section: dict[str, list] = {}
    for t in plan.trips:
        by_section.setdefault(t.section_id, []).append(t)

    rows = []
    for sid, trips in by_section.items():
        sec = net.sections[sid]
        trips.sort(key=lambda t: (t.entry, net.trains[t.train_id].priority, t.train_id))
        for k, trip in enumerate(trips):
            if trip.entry <= state_time:
                continue                       # already entered: not a prediction any more
            train = net.trains[trip.train_id]
            prev = trips[k - 1] if k > 0 else None
            prev_train = net.trains[prev.train_id] if prev else None
            rows.append({
                "train_id": trip.train_id,
                "train_type": train.train_type,
                "priority": train.priority,
                "current_delay_min": delay_at[(trip.train_id, sid)],
                "time_to_section_min": trip.entry - state_time,
                "section_id": sid,
                "section_tracks": sec.tracks,
                "headway_gap_min": trip.entry - prev.exit if prev else NO_PRECEDING_GAP,
                "preceding_train_type": prev_train.train_type if prev else "NONE",
                "preceding_train_priority": prev_train.priority if prev else 0,
                "preceding_train_delay_min": delay_at[(prev.train_id, sid)] if prev else 0,
                "section_occupied_at_planned_entry": int(any(
                    o is not trip and o.entry <= trip.entry < o.exit for o in trips)),
                "trains_ahead_within_30min": sum(1 for o in trips[:k] if o.entry >= trip.entry - 30),
                "disruption_type": first.event_type,
                "disruption_duration_min": first.duration,
                "hour_of_day": trip.entry // 60,
                "rule_flags_conflict": int((trip.train_id, sid) in flagged),
                "baseline_projected_delay_min": projection.final_delay(trip.train_id),
            })
    return rows


def build_rows(net: RailNetwork, sample: RunSample, result: SimResult) -> list[dict]:
    """Feature rows for one run plus labels from the randomised outcome."""
    rows = plan_features(net, sample.state_time, sample.known_events, sample.disruptions[0])
    for row in rows:
        actual = result.occupancy(row["train_id"], row["section_id"])
        row["run_id"] = sample.run_id
        row["label_conflict"] = int(actual.wait > 0)
        row["label_wait_min"] = actual.wait
        row["label_delay_min"] = result.final_delay(row["train_id"])
    return rows


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def iter_runs(n_runs: int, seed: int, net: RailNetwork | None = None):
    """Yield (sample, result) per run. Same seed -> identical sequence."""
    net = net or load_network(timetable=TIMETABLE)
    master = random.Random(seed)
    for i in range(1, n_runs + 1):
        rng = random.Random(master.getrandbits(64))
        sample = sample_run(net, f"R{i:05d}", rng)
        yield sample, simulate_run(net, sample, rng)


def generate(n_runs: int, seed: int) -> pd.DataFrame:
    """Generate the SIMULATED training table. Same seed -> identical DataFrame."""
    net = load_network(timetable=TIMETABLE)
    rows: list[dict] = []
    ignored = 0
    for sample, result in iter_runs(n_runs, seed, net):
        rows.extend(build_rows(net, sample, result))
        ignored += sum(1 for line in result.ignored_events if "was not inside" in line)
    df = pd.DataFrame(rows, columns=COLUMNS)
    df.attrs["ignored_stoppages"] = ignored     # stoppages that missed the train after variability
    df.attrs["note"] = SIMULATED_NOTE
    return df


def dataset_card(df: pd.DataFrame, n_runs: int, seed: int) -> dict:
    """Facts about a generated table, all computed from the data itself."""
    flags, labels = df["rule_flags_conflict"], df["label_conflict"]
    return {
        "note": SIMULATED_NOTE,
        "seed": seed,
        "runs": n_runs,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "conflict_rate": round(float(labels.mean()), 4),
        "rule_flag_rate": round(float(flags.mean()), 4),
        "rule_vs_label": {
            "disagreement_rate": round(float((flags != labels).mean()), 4),
            "both_conflict": int(((flags == 1) & (labels == 1)).sum()),
            "rule_only": int(((flags == 1) & (labels == 0)).sum()),
            "label_only": int(((flags == 0) & (labels == 1)).sum()),
            "neither": int(((flags == 0) & (labels == 0)).sum()),
        },
        "label_wait_min": _stats(df["label_wait_min"]),
        "label_wait_min_when_conflict": _stats(df.loc[labels == 1, "label_wait_min"]),
        "label_delay_min_per_row": _stats(df["label_delay_min"]),
        "ignored_stoppages": int(df.attrs.get("ignored_stoppages", 0)),
        "variability": DEFAULT_VARIABILITY.as_dict(),
        "generator": GENERATOR_RANGES,
        "split_rule": "split by run_id only, never by random rows",
    }


def _stats(s: pd.Series) -> dict:
    if s.empty:
        return {"mean": 0.0, "max": 0, "min": 0}
    return {"mean": round(float(s.mean()), 2), "max": int(s.max()), "min": int(s.min())}
