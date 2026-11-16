"""Plain-word text for the ML model's top SHAP drivers (Phase 7).

Drivers explain the MODEL'S SCORE, not physical causes: every sentence reads
"Model risk raised by: ..." / "Model risk lowered by: ...", never "because". The physical
reason for a clash comes only from the rule-based detector (see recommendation.py).

Each template turns the feature's VALUE (the number the model saw, carried in the API payload
next to the text) into words. SHAP magnitudes (log-odds) are never put in a sentence.
"""
from __future__ import annotations

from typing import Callable

from app.services.datagen.generator import FEATURES, NO_PRECEDING_GAP


def _n(v) -> int:
    return int(round(float(v)))


def _plural(n: int, one: str, many: str) -> str:
    return one if abs(n) == 1 else many


def _delay(subject: str, v) -> str:
    n = _n(v)
    if n > 0:
        return f"{subject} is already {n} min late"
    if n < 0:
        return f"{subject} is {abs(n)} min early"
    return f"{subject} is on time"


def _gap(v) -> str:
    n = _n(v)
    if n >= NO_PRECEDING_GAP:
        return "no train is ahead of it on this section"
    if n < 0:
        return f"it is planned to enter {abs(n)} min before the section clears"
    if n == 0:
        return "it is planned to enter just as the section clears"
    return f"it is planned to enter {n} min after the section clears"


def _ahead(v) -> str:
    n = _n(v)
    if n == 0:
        return "no other train enters this section within the half hour before it"
    return f"{n} other {_plural(n, 'train enters', 'trains enter')} this section within the half hour before it"


TEMPLATES: dict[str, Callable] = {
    "train_type": lambda v: f"it is a {str(v).lower()} train",
    "priority": lambda v: f"its priority is {_n(v)} (a lower number is a higher priority)",
    "current_delay_min": lambda v: _delay("the train", v),
    "time_to_section_min": lambda v: f"it is planned to reach the section in {_n(v)} min",
    "section_id": lambda v: f"the section is {v}",
    "section_tracks": lambda v: f"the section has {_n(v)} {_plural(_n(v), 'track', 'tracks')}",
    "headway_gap_min": _gap,
    "preceding_train_type": lambda v: ("no train is ahead of it on this section" if str(v) == "NONE"
                                       else f"the train ahead is a {str(v).lower()} train"),
    "preceding_train_priority": lambda v: ("no train is ahead of it on this section" if _n(v) == 0
                                           else f"the train ahead has priority {_n(v)}"),
    "preceding_train_delay_min": lambda v: _delay("the train ahead", v),
    "section_occupied_at_planned_entry": lambda v: ("the section is occupied at its planned entry" if _n(v)
                                                    else "the section is free at its planned entry"),
    "trains_ahead_within_30min": _ahead,
    "disruption_type": lambda v: f"the known disruption is a {str(v).lower().replace('_', ' ')}",
    "disruption_duration_min": lambda v: f"the known disruption lasts {_n(v)} min",
    "hour_of_day": lambda v: f"its planned entry is in hour {_n(v)} of the day",
    "rule_flags_conflict": lambda v: ("the rule-based detector also flags it" if _n(v)
                                      else "the rule-based detector does not flag it"),
}

missing = set(FEATURES) - set(TEMPLATES)
assert not missing, f"features without a driver template: {missing}"

HEADING = {"raises": "Model risk raised by", "lowers": "Model risk lowered by"}


def driver_text(feature: str, value) -> str:
    """Plain words for one feature value, e.g. headway_gap_min=-10 ->
    'it is planned to enter 10 min before the section clears'."""
    if value is None:
        return f"{feature} (no value)"
    return TEMPLATES[feature](value)


def describe(driver: dict) -> dict:
    """Adds `text` (the phrase) and `sentence` ('Model risk raised by: <phrase>.') to a driver."""
    text = driver_text(driver["feature"], driver.get("value"))
    return {**driver, "text": text, "sentence": f"{HEADING[driver['direction']]}: {text}."}


def describe_all(drivers: list[dict]) -> list[dict]:
    return [describe(d) for d in drivers]
