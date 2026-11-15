"""Corridor definition for DG -> MDU (one track per direction, "twin single line").

Station chainages (km from Chennai Egmore) for ABI..MDU are from the Southern Railway Madurai
division system map 2024 as supplied by the project owner. DG's chainage could not be read from
the map (the official URLs returned 404 on 2026-11-15), so it is DERIVED: ABI chainage minus the
DG-ABI distance in the dataset's own route file (see docs/DATA_SOURCES.md, ASSUMPTIONS.md 47-48).
Minimum running times, platforms and loops are not public: ASSUMED (ASSUMPTIONS.md 49-50, 65);
the headway is CALIBRATED on the recorded days (ASSUMPTIONS.md 64).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

DATA_LABEL = "REAL"
CORRIDOR_ID = "dg_mdu"

# km from Chennai Egmore on the SR MDU division map 2024 (owner-supplied values).
MAP_CHAINAGE_KM: dict[str, float] = {
    "ABI": 444.02, "KQN": 454.85, "VDP": 465.92, "SDN": 473.66,
    "SER": 482.45, "KON": 491.20, "MDU": 494.95,
}

STATION_NAMES: dict[str, str] = {
    "DG": "Dindigul Jn", "ABI": "Ambaturai", "KQN": "Kodaikanal Road", "VDP": "Vadipatti",
    "SDN": "Sholavandan", "SER": "Samayanallur", "KON": "Koodal Nagar", "MDU": "Madurai Jn",
}
ORDER: list[str] = ["DG", "ABI", "KQN", "VDP", "SDN", "SER", "KON", "MDU"]
JUNCTIONS = {"DG", "MDU"}

# ASSUMED (not public): platforms usable by DG -> MDU trains and the maximum speed.
ASSUMED_PLATFORMS: dict[str, int] = {"DG": 5, "MDU": 7, "ABI": 2, "KQN": 2, "VDP": 2,
                                     "SDN": 2, "SER": 2, "KON": 2}
ASSUMED_MAX_SPEED_KMH = 110.0
# CALIBRATED on the recorded days (calibrate.py, ASSUMPTIONS.md 64): the largest headway that all 75
# fully recorded section pairs respect. 0 still means one train per block section (absolute block).
CALIBRATED_HEADWAY_MIN = 0
# ASSUMED loop lines per station (ASSUMPTIONS.md 65): a train can only be overtaken where a loop is free.
ASSUMED_LOOPS: dict[str, int] = {"DG": 4, "ABI": 1, "KQN": 2, "VDP": 1, "SDN": 2, "SER": 1, "KON": 0, "MDU": 4}


@dataclass(frozen=True)
class Chainage:
    km: float
    method: str          # MAP_2024 | DERIVED
    note: str = ""


def derive_dg_chainage(dg_abi_route_km: float) -> Chainage:
    """DG = ABI (map) - DG-ABI distance from the dataset route file. Labelled DERIVED."""
    km = round(MAP_CHAINAGE_KM["ABI"] - dg_abi_route_km, 2)
    return Chainage(km, "DERIVED",
                    f"ABI {MAP_CHAINAGE_KM['ABI']} (map 2024) - DG-ABI {dg_abi_route_km:g} km (dataset route file)")


def chainages(dg: Chainage) -> dict[str, Chainage]:
    out = {"DG": dg}
    out.update({s: Chainage(k, "MAP_2024") for s, k in MAP_CHAINAGE_KM.items()})
    return out


def km_from_dg(dg: Chainage) -> dict[str, float]:
    return {s: round(c.km - dg.km, 2) for s, c in chainages(dg).items()}


def sections(km: dict[str, float]) -> list[dict]:
    rows = []
    for a, b in zip(ORDER, ORDER[1:]):
        length = round(km[b] - km[a], 2)
        rows.append({
            "section_id": f"S_{a}_{b}", "from_station": a, "to_station": b, "length_km": length,
            "tracks": 1,
            "min_run_min": max(1, math.ceil(length / ASSUMED_MAX_SPEED_KMH * 60)),
            "min_headway_min": CALIBRATED_HEADWAY_MIN, "status": "open",
            "min_run_source": "ASSUMED", "headway_source": "CALIBRATED",
        })
    return rows


def train_type(train_no: int, name: str) -> str:
    """Category from the IR numbering convention (12/20/22xxx = superfast) and the name."""
    n = str(train_no)
    if len(n) < 5:
        return "SPECIAL"                       # 0xxxx specials lose their leading zero in the dataset
    words = name.lower().split()
    if "vande" in name.lower() or "vandebharat" in words or "vb" in words or "tejas" in words:
        return "PREMIUM"
    if n[:2] in {"12", "20", "22"}:
        return "SUPERFAST"
    return "EXPRESS"


# ASSUMED (no public priority order), ASSUMPTIONS.md 66: 1 = highest. Objective weight = 4 - priority.
PRIORITY = {"PREMIUM": 1, "SUPERFAST": 2, "EXPRESS": 3, "SPECIAL": 3}
