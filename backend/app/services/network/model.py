"""Railway network model: stations, sections, trains and timetable.

Loads the CSV files in backend/data into plain dataclasses and a NetworkX
MultiDiGraph (several parallel sections can join the same two stations,
for example the main line S_BC and the alternate line S_BC_ALT).

Times are stored as integer minutes after midnight ("10:03" -> 603).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def parse_time(value: str | None) -> int | None:
    """'HH:MM' -> minutes after midnight. Empty -> None."""
    if value is None or value.strip() == "":
        return None
    hours, minutes = value.strip().split(":")
    return int(hours) * 60 + int(minutes)


def format_time(minutes: int | None) -> str:
    """Minutes after midnight -> 'HH:MM'."""
    if minutes is None:
        return "--:--"
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True)
class Station:
    code: str
    name: str
    km_from_start: float
    platforms: int
    is_junction: bool


@dataclass(frozen=True)
class Section:
    section_id: str
    from_station: str
    to_station: str
    length_km: float
    tracks: int            # how many trains may occupy the section at once
    min_run_min: int       # fastest possible running time
    min_headway_min: int   # gap after one train clears before the next may enter
    status: str            # open | standby | closed

    @property
    def is_primary(self) -> bool:
        return self.status == "open"


@dataclass(frozen=True)
class Train:
    train_id: str
    train_no: str
    name: str
    train_type: str        # EXPRESS | PASSENGER | FREIGHT
    priority: int          # 1 = highest
    runs_on: str


@dataclass(frozen=True)
class StopTime:
    station: str
    seq: int
    sched_arr: int | None  # None at origin
    sched_dep: int | None  # None at destination


@dataclass
class RailNetwork:
    stations: dict[str, Station]
    sections: dict[str, Section]
    trains: dict[str, Train]
    schedules: dict[str, list[StopTime]]
    graph: nx.MultiDiGraph = field(repr=False)

    def sections_between(self, a: str, b: str) -> list[Section]:
        """All sections from station a to station b (primary first)."""
        found = [s for s in self.sections.values() if s.from_station == a and s.to_station == b]
        return sorted(found, key=lambda s: (not s.is_primary, s.min_run_min))

    def primary_section(self, a: str, b: str) -> Section:
        options = [s for s in self.sections_between(a, b) if s.status != "closed"]
        if not options:
            raise ValueError(f"No usable section from {a} to {b}")
        return options[0]

    def route_sections(self, train_id: str) -> list[Section]:
        """Sections a train uses by default, in order, following its timetable."""
        stops = self.schedules[train_id]
        return [self.primary_section(stops[i].station, stops[i + 1].station) for i in range(len(stops) - 1)]

    def shortest_route(self, a: str, b: str) -> list[str]:
        """Station sequence of the shortest route by length (km)."""
        return nx.shortest_path(self.graph, a, b, weight="length_km")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# timetable name -> (trains file, schedule file). Stations and sections are shared.
TIMETABLES = {
    "reference": ("trains.csv", "schedule.csv"),                    # T101/T202/T303 scenario
    "full_day": ("trains_full_day.csv", "schedule_full_day.csv"),   # 12 trains, 06:00-14:00
}


def load_network(data_dir: str | Path = DEFAULT_DATA_DIR, timetable: str = "reference") -> RailNetwork:
    data_dir = Path(data_dir)
    if timetable not in TIMETABLES:
        raise ValueError(f"Unknown timetable {timetable!r}; choose from {sorted(TIMETABLES)}")
    trains_file, schedule_file = TIMETABLES[timetable]

    stations = {
        r["station_code"]: Station(
            code=r["station_code"],
            name=r["station_name"],
            km_from_start=float(r["km_from_start"]),
            platforms=int(r["platforms"]),
            is_junction=r["is_junction"].strip().lower() == "yes",
        )
        for r in _read_csv(data_dir / "stations.csv")
    }

    sections = {
        r["section_id"]: Section(
            section_id=r["section_id"],
            from_station=r["from_station"],
            to_station=r["to_station"],
            length_km=float(r["length_km"]),
            tracks=int(r["tracks"]),
            min_run_min=int(r["min_run_min"]),
            min_headway_min=int(r["min_headway_min"]),
            status=r["status"].strip().lower(),
        )
        for r in _read_csv(data_dir / "sections.csv")
    }

    trains = {
        r["train_id"]: Train(
            train_id=r["train_id"],
            train_no=r["train_no"],
            name=r["train_name"],
            train_type=r["train_type"].strip().upper(),
            priority=int(r["priority"]),
            runs_on=r["runs_on"],
        )
        for r in _read_csv(data_dir / trains_file)
    }

    schedules: dict[str, list[StopTime]] = {}
    for r in _read_csv(data_dir / schedule_file):
        schedules.setdefault(r["train_id"], []).append(
            StopTime(
                station=r["station_code"],
                seq=int(r["stop_seq"]),
                sched_arr=parse_time(r["sched_arr"]),
                sched_dep=parse_time(r["sched_dep"]),
            )
        )
    for stops in schedules.values():
        stops.sort(key=lambda s: s.seq)

    _validate(stations, sections, trains, schedules)

    graph = nx.MultiDiGraph()
    for st in stations.values():
        graph.add_node(st.code, name=st.name, platforms=st.platforms, km=st.km_from_start)
    for sec in sections.values():
        graph.add_edge(
            sec.from_station,
            sec.to_station,
            key=sec.section_id,
            length_km=sec.length_km,
            tracks=sec.tracks,
            min_run_min=sec.min_run_min,
            min_headway_min=sec.min_headway_min,
            status=sec.status,
        )

    return RailNetwork(stations, sections, trains, schedules, graph)


def _validate(stations, sections, trains, schedules) -> None:
    """Fail early on data mistakes instead of producing a wrong simulation."""
    for sec in sections.values():
        for code in (sec.from_station, sec.to_station):
            if code not in stations:
                raise ValueError(f"Section {sec.section_id} uses unknown station {code}")
        if sec.tracks < 1 or sec.min_run_min < 1 or sec.min_headway_min < 0:
            raise ValueError(f"Section {sec.section_id} has invalid capacity or times")
    for train_id, stops in schedules.items():
        if train_id not in trains:
            raise ValueError(f"Schedule for unknown train {train_id}")
        if len(stops) < 2:
            raise ValueError(f"Train {train_id} needs at least two stops")
        if stops[0].sched_dep is None or stops[-1].sched_arr is None:
            raise ValueError(f"Train {train_id} needs an origin departure and a destination arrival")
        for prev, nxt in zip(stops, stops[1:]):
            if prev.station not in stations or nxt.station not in stations:
                raise ValueError(f"Train {train_id} calls at an unknown station")
            if nxt.sched_arr is None or prev.sched_dep is None:
                raise ValueError(f"Train {train_id} is missing a time between {prev.station} and {nxt.station}")
            if nxt.sched_arr < prev.sched_dep:
                raise ValueError(f"Train {train_id} arrives at {nxt.station} before leaving {prev.station}")
