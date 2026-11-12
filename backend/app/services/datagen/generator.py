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
STOPPAGE_CLEAR_MARGIN_MIN = 30  # no closure on a section until 30 min after a stoppage there ends

FEATURES = [
    "train_type", "priority", "current_delay_min", "time_to_section_min",
    "section_id", "section_tracks", "headway_gap_min",
    "preceding_train_type", "preceding_train_priority", "preceding_train_delay_min",
    "section_occupied_at_planned_entry", "trains_ahead_within_30min",
    "disruption_type", "disruption_duration_min", "hour_of_day", "rule_flags_conflict",
]
LABELS = ["label_conflict", "label_wait_min", "label_delay_min"]
COLUMNS = ["run_id", *FEATURES, *LABELS]

GENERATOR_RANGES = {
    "timetable": TIMETABLE,
    "service_day": ["06:00", "14:00"],
    "disruption_types": list(DISRUPTION_TYPES),
    "disruptions_per_run": list(DISRUPTIONS_PER_RUN),
    "disruption_duration_min": list(DISRUPTION_DURATION_MIN),
    "starting_delay_min": list(STARTING_DELAY_MIN),
    "no_preceding_train_gap_value": NO_PRECEDING_GAP,
    "closure_clear_of_stoppage_margin_min": STOPPAGE_CLEAR_MARGIN_MIN,
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
            drawn.append((start, kind, train_id, trip.section_id, duration))
        elif kind == "DELAY":
            train_id = rng.choice(trains)
            trip = rng.choice([t for t in base.trips if t.train_id == train_id])
            station = net.sections[trip.section_id].from_station
            drawn.append((trip.entry, kind, train_id, station, duration))
        else:
            drawn.append((None, kind, None, rng.choice(open_sections), duration))

    # Closures are drawn last so they can avoid a section while a stopped train
    # may still be inside it: the model has no rule for a closure that starts
    # with a stranded train in the section (see docs/ASSUMPTIONS.md).
    stoppages = [(loc, start, start + dur + STOPPAGE_CLEAR_MARGIN_MIN)
                 for start, kind, _t, loc, dur in drawn if kind == "STOPPAGE"]
    for k, (start, kind, train, loc, dur) in enumerate(drawn):
        if kind != "TRACK_UNAVAILABLE":
            continue
        for _ in range(50):
            start = rng.randint(*SERVICE_DAY)
            if not any(s_loc == loc and start < s_end and start + dur > s_start
                       for s_loc, s_start, s_end in stoppages):
                break
        else:
            raise RuntimeError(f"{run_id}: no closure slot on {loc} clear of stoppages")
        drawn[k] = (start, kind, train, loc, dur)

    drawn.sort(key=lambda d: d[0])
    disruptions = [Disruption(f"E{i}", kind, train, loc, start, dur)
                   for i, (start, kind, train, loc, dur) in enumerate(drawn, start=1)]
    return RunSample(run_id, starting, disruptions)


def simulate_run(net: RailNetwork, sample: RunSample, rng: random.Random) -> SimResult:
    """The 'actual' outcome: all disruptions, random variability, no re-planning."""
    return simulate(net, sample.all_events, rng=rng)


# ---------------------------------------------------------------------------
# rows for one run
# ---------------------------------------------------------------------------
def build_rows(net: RailNetwork, sample: RunSample, result: SimResult) -> list[dict]:
    state_time = sample.state_time
    plan = project_plan(net, state_time, sample.known_events)
    flagged = {(c.later, c.section_id) for c in detect_conflicts(net, plan)}
    first = sample.disruptions[0]

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
            actual = result.occupancy(trip.train_id, sid)
            rows.append({
                "run_id": sample.run_id,
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
                "label_conflict": int(actual.wait > 0),
                "label_wait_min": actual.wait,
                "label_delay_min": result.final_delay(trip.train_id),
            })
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
