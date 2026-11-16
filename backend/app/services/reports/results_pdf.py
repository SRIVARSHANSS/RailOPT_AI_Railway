"""Evaluation report and model report (PDF) from the stored result files.

Both refuse to export unless the files pass the same freshness checks as the Analytics and
Model Insights pages (app/services/results.py): `status == "ok"`. The model report also checks
that each committed card is exactly what its JSON renders to (cards are generated, never edited
by hand) and, for the real-data card, that the REAL extract still has the hashes the run used.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.services import results

from . import charts
from .pdf import (CONCLUSION_BG, CONCLUSION_EDGE, LabelMark, PageBreak, Spacer, boxed, build, figure,
                  frame_width, markdown, p, styles, table)

BACKEND = Path(__file__).resolve().parents[3]
REAL_REPORTS = BACKEND / "ml" / "reports" / "real"
REAL_DIR = BACKEND / "data" / "real" / "dg_mdu"

PHASE10 = ["NO_REPLANNING", "PRIORITY_DISPATCH", "SINGLE_SHOT", "DYNAMIC", "DYNAMIC_ML"]
BASELINES = {"NO_REPLANNING", "PRIORITY_DISPATCH"}
METHOD_LABEL = {  # words only (same names as the Analytics page)
    "NO_REPLANNING": "No re-planning (FCFS)", "PRIORITY_DISPATCH": "Priority dispatch",
    "SINGLE_SHOT": "RailOpt single-shot", "DYNAMIC": "RailOpt dynamic", "DYNAMIC_ML": "Dynamic + ML, 1-min buffers",
    "DYNAMIC_ML_B2": "A: 2-min buffers", "DYNAMIC_ML_B3": "A: 3-min buffers",
    "DYNAMIC_ML_PROP": "B: round(3p)-min buffers", "DYNAMIC_ML_TRIGGER": "C: ML-triggered re-planning",
}
METRICS = [("weighted_delay", "Weighted delay", 1), ("avg_delay_min", "Avg delay (min/train)", 2),
           ("total_delay_min", "Total delay (min)", 1), ("max_delay_min", "Max delay (min)", 1),
           ("total_wait_min", "Wait (min)", 1), ("trains_waited", "Trains that waited", 2),
           ("throughput_trains_per_hour", "Throughput (trains/h)", 2)]


class Outdated(Exception):
    """The stored results do not match the files they were computed from."""

    def __init__(self, what: str, status: str, reasons: list[str], command: str):
        self.status, self.reasons, self.command = status, reasons, command
        super().__init__(f"{what} {status} - rerun `{command}` from backend/: " + "; ".join(reasons))


def _f(x, d=1) -> str:
    return f"{x:.{d}f}"


def _ci(c, d=1) -> str:
    return f"[{_f(c[0], d)}, {_f(c[1], d)}]"


def _signed(x, d=1) -> str:
    return ("+" if x > 0 else "") + _f(x, d)


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------
def evaluation_pdf(view: dict, user=None, now: datetime | None = None) -> bytes:
    if view["status"] != "ok":
        raise Outdated("evaluation", view["status"], view["reasons"], view["command"])
    s, st, W = view["summary"], styles(), frame_width(wide=True)
    now = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    sc = s["scenarios"]
    story = [p("Evaluation report", "title", st), p(s["label"], "small", st), Spacer(1, 4),
             table([["Field", "Value"],
                    ["Scenarios", f"{s['config']['scenarios']} (seed {s['config']['seed']}, timetable {s['config']['timetable']})"],
                    ["Disruptions", f"{sc['disruptions_total']} ({', '.join(f'{k} {v}' for k, v in sc['types'].items())})"],
                    ["Overlap with training data", f"{sc['overlap_with_training']} (training seed {sc['training_seed']}, "
                                                   f"{sc['training_runs']} runs)"],
                    ["Robustness replays / bootstrap", f"{s['config']['replays']} replays per scenario, "
                                                       f"{s['config']['bootstrap']} bootstrap resamples"],
                    ["Constraint violations", f"{s['violations']} in {s['replays_checked']} replays checked"],
                    ["Source", f"eval/reports/eval_summary.json, hash-checked (results CSV and model files): {view['status']}"],
                    ["Command", view["command"]],
                    ["Generated", f"{now} UTC by {getattr(user, 'email', '')}"]], [W * 0.25, W * 0.75], st=st)]
    for setting in ("deterministic", "robustness"):
        ss = s["settings"][setting]
        story += [p(f"Methods - {setting}", "h1", st)]
        rows = [["Method"] + [lab for _, lab, _ in METRICS] + ["vs no re-planning (weighted): W / T / L, mean diff [CI]"]]
        for m in PHASE10:
            row = [METHOD_LABEL[m]]
            for k, _, dg in METRICS:
                d = ss["methods"][m][k]
                row.append(f"{_f(d['mean'], dg)} {_ci(d['mean_ci'], dg)}\nmedian {_f(d['median'], dg)}")
            pv = ss["paired_vs_no_replanning"].get(m, {}).get("weighted_delay")
            row.append(f"{pv['wins']} / {pv['ties']} / {pv['losses']} · {_signed(pv['mean_diff'])} "
                       f"{_ci(pv['mean_diff_ci'])} ({'significant' if pv['significant'] else 'not significant'})"
                       if pv else "reference")
            rows.append(row)
        story.append(table(rows, [W * 0.13] + [W * 0.095] * len(METRICS) + [W * 0.205], st=st))
    story.append(p(f"Mean [95% bootstrap CI, {s['config']['bootstrap']} resamples] per scenario. Paired: diff = method "
                   "- no re-planning per scenario; significant only when the CI of the mean difference excludes 0.",
                   "small", st))
    story += [PageBreak(), p("Charts", "h1", st),
              p("Mean weighted delay per scenario with 95% bootstrap CI (baselines grey)", "h2", st),
              figure(charts.eval_bars(s, PHASE10, METHOD_LABEL, BASELINES), W * 0.92),
              p("Weighted delay saved vs no re-planning per scenario (box: quartiles and median, whiskers: Tukey, "
                "dot: mean)", "h2", st),
              figure(charts.eval_reduction(view["distribution"], PHASE10[1:], METHOD_LABEL), W * 0.92)]
    concl = view.get("conclusion")
    variants = list(s["settings"]["deterministic"].get("variants_vs_dynamic", {}))
    story += [PageBreak(), p("ML integration variants (Phase 10b)", "h1", st)]
    if concl:
        story.append(boxed([p(concl["text"], "h2", st)], CONCLUSION_BG, CONCLUSION_EDGE, W))
        story.append(Spacer(1, 4))
    rows = [["Variant (vs RailOpt dynamic, no ML)", "deterministic: weighted delay diff [95% CI]", "W / T / L",
             "robustness: weighted delay diff [95% CI]", "W / T / L"]]
    rows.append([f"{METHOD_LABEL['DYNAMIC']} (reference)"] +
                [x for setting in ("deterministic", "robustness")
                 for x in (f"mean {_f(s['settings'][setting]['methods']['DYNAMIC']['weighted_delay']['mean'])} "
                           f"{_ci(s['settings'][setting]['methods']['DYNAMIC']['weighted_delay']['mean_ci'])}", "")])
    for m in variants:
        pre = " (pre-registered)" if concl and m in concl.get("preregistered", []) else ""
        cells = [METHOD_LABEL.get(m, m) + pre]
        for setting in ("deterministic", "robustness"):
            pv = s["settings"][setting]["variants_vs_dynamic"][m]["weighted_delay"]
            verdict = ("better" if pv["mean_diff"] < 0 else "worse") if pv["significant"] else "not significant"
            cells += [f"{_signed(pv['mean_diff'], 2)} {_ci(pv['mean_diff_ci'], 2)} ({verdict})",
                      f"{pv['wins']} / {pv['ties']} / {pv['losses']}"]
        rows.append(cells)
    story.append(table(rows, [W * 0.26, W * 0.24, W * 0.13, W * 0.24, W * 0.13], st=st))
    story.append(p("Diff = variant minus dynamic per scenario; negative = less delay. Significant only when the 95% "
                   "bootstrap CI excludes 0.", "small", st))
    tot = view.get("solver_totals") or {}
    if tot:
        ph = tot["phase10"]
        story.append(p(f"Solver: {ph['optimal']} / {ph['solves']} OPTIMAL solves (Phase 10 methods), mean "
                       f"{_f(ph['solve_s_mean'] * 1000, 0)} ms, max {_f(ph['solve_s_max'] * 1000, 0)} ms; Phase 10b "
                       f"variants {tot['variants_10b']['optimal']} / {tot['variants_10b']['solves']} OPTIMAL.", "body", st))
    story += [Spacer(1, 6), boxed([p("Limits", "h2", st)] + [p("• " + x, "body", st) for x in results.limits(s)], width=W)]
    label = "SIMULATED"
    return build(story, title="RailOpt AI - evaluation report", label=label, wide=True,
                 meta=f"eval_summary.json · {view['command']} · generated {now}")


# ---------------------------------------------------------------------------
# model report (synthetic card + real-data card)
# ---------------------------------------------------------------------------
def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cards_status(reports: Path | None = None, real_reports: Path | None = None,
                 real_dir: Path | None = None) -> dict:
    """Freshness of both cards: model_view (hashes of dataset and models) for the synthetic one;
    for both, the committed card must equal what its JSON renders to; the real card's inputs
    must still have the hashes recorded in metrics_real.json."""
    reports = reports or results.ML_REPORTS
    real_reports = real_reports or REAL_REPORTS
    real_dir = real_dir or REAL_DIR
    view = results.model_view()
    reasons = list(view["reasons"]) if view["status"] != "ok" else []
    status = view["status"]
    out = {"synthetic": None, "real": None}
    try:
        from ml.train import render_model_card
        metrics = json.loads((reports / "metrics.json").read_text(encoding="utf-8"))
        card = (reports / "model_card.md").read_text(encoding="utf-8")
        if card.strip() != render_model_card(metrics).strip():
            reasons.append("model_card.md differs from what metrics.json renders to")
        out["synthetic"] = card
    except FileNotFoundError as exc:
        reasons.append(f"missing {Path(exc.filename).name}")
        status = "missing"
    try:
        from ml.real_delay import render
        real = json.loads((real_reports / "metrics_real.json").read_text(encoding="utf-8"))
        card = (real_reports / "model_card_real.md").read_text(encoding="utf-8")
        if card.strip() != render(real).strip():
            reasons.append("model_card_real.md differs from what metrics_real.json renders to")
        for name, h in real.get("inputs", {}).items():
            if not (real_dir / name).exists() or _sha(real_dir / name) != h:
                reasons.append(f"REAL extract {name} changed since the real-data run (python -m ml.real_delay)")
        out["real"] = card
    except FileNotFoundError as exc:
        reasons.append(f"missing {Path(exc.filename).name}")
        status = "missing"
    if reasons and status == "ok":
        status = "outdated"
    return {"status": status, "reasons": reasons, "command": f"{view['command']} / python -m ml.real_delay",
            "cards": out}


def model_pdf(status: dict, user=None, now: datetime | None = None) -> bytes:
    if status["status"] != "ok":
        raise Outdated("model report", status["status"], status["reasons"], status["command"])
    st, W = styles(), frame_width()
    now = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    story = [p("Model report", "title", st),
             p("Part 1: synthetic model card (SIMULATED training data). Part 2: real-data model card (REAL recorded "
               "running times). Both cards are reproduced as generated from their JSON; nothing is edited.", "small", st),
             p(f"Generated {now} UTC by {getattr(user, 'email', '')}; freshness check: ok.", "small", st),
             Spacer(1, 6)]
    story += markdown(status["cards"]["synthetic"], st, W)
    story += [PageBreak(), LabelMark("REAL")]
    story += markdown(status["cards"]["real"], st, W)
    return build(story, title="RailOpt AI - model report", label="SIMULATED",
                 meta=f"ml/reports/model_card.md + ml/reports/real/model_card_real.md · generated {now}")
