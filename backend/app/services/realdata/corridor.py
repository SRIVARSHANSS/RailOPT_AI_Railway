"""Corridor definition for DG -> MDU (one track per direction, "twin single line").

Station chainages (km from Chennai Egmore) for ABI..MDU are from the Southern Railway Madurai
division system map 2024 as supplied by the project owner. DG's chainage could not be read from
the map (the official URLs returned 404 on 2026-11-15), so it is DERIVED: ABI chainage minus the
DG-ABI distance in the dataset's own route file (see docs/DATA_SOURCES.md, ASSUMPTIONS.md 47-48).
Headways, minimum running times and platform counts are not public: ASSUMED (ASSUMPTIONS.md 49-51).
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

# ASSUMED (not public): platforms usable by DG -> MDU trains, minimum headway, maximum speed.
ASSUMED_PLATFORMS: dict[str, int] = {"DG": 5, "MDU": 7, "ABI": 2, "KQN": 2, "VDP": 2,
                                     "SDN": 2, "SER": 2, "KON": 2}
ASSUMED_HEADWAY_MIN = 5
ASSUMED_MAX_SPEED_KMH = 110.0


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
            "min_headway_min": ASSUMED_HEADWAY_MIN, "status": "open",
        })
    return rows


def train_type(train_no: int, name: str) -> str:
    """Category from the IR numbering convention (12/20/22xxx = superfast) and the name."""
    n = str(train_no)
    if len(n) < 5:
        return "SPECIAL"                       # 0xxxx specials lose their leading zero in the dataset
    if "vande" in name.lower() or "tejas" in name.lower():
        return "PREMIUM"
    if n[:2] in {"12", "20", "22"}:
        return "SUPERFAST"
    return "EXPRESS"


PRIORITY = {"PREMIUM": 1, "SUPERFAST": 1, "EXPRESS": 1, "SPECIAL": 1}   # ASSUMED, ASSUMPTIONS.md 52
