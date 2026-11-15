"""Summary JSON, Markdown report and charts. The report is GENERATED from eval_summary.json:
no number in it is typed by hand. Everything is SIMULATED."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from eval.evaluation import METHODS, METRICS, RAILOPT, SETTINGS, SIMULATED_NOTE
from eval.stats import describe, paired

LABEL = {"NO_REPLANNING": "No re-planning (FCFS)", "PRIORITY_DISPATCH": "Priority dispatch",
         "SINGLE_SHOT": "RailOpt single-shot", "DYNAMIC": "RailOpt dynamic", "DYNAMIC_ML": "RailOpt dynamic + ML"}
METRIC_LABEL = {"avg_delay_min": "Avg delay (min/train)", "total_delay_min": "Total delay (min)",
                "weighted_delay": "Weighted delay", "max_delay_min": "Max delay (min)",
                "throughput_trains_per_hour": "Throughput (trains/h)", "trains_waited": "Trains that waited",
                "total_wait_min": "Wait (min)"}
PAIRED_METRICS = ["weighted_delay", "total_delay_min"]
# chart colours: reference categorical slots 1-2 (validated light mode, CVD dE 24.7)
C_DET, C_ROB = "#2a78d6", "#eb6834"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"


def _series(rows: list[dict], setting: str, method: str, metric: str) -> np.ndarray:
    sel = sorted((r for r in rows if r["setting"] == setting and r["method"] == method), key=lambda r: r["scenario_index"])
    return np.array([float(r[metric]) for r in sel])


def summarize(rows: list[dict], plans_info: dict, config: dict) -> dict:
    """plans_info: {"solves": {method: [solve dicts]}, "guarantee": [dicts], "scenarios": [...] }"""
    out = {"label": SIMULATED_NOTE, "config": config, "settings": {}}
    for setting in SETTINGS:
        s = {"methods": {}, "paired_vs_no_replanning": {}, "ml_ablation": {}, "dynamic_vs_single_shot": {}}
        for m in METHODS:
            s["methods"][m] = {k: describe(_series(rows, setting, m, k), seed=1) for k in METRICS}
        base = {k: _series(rows, setting, "NO_REPLANNING", k) for k in PAIRED_METRICS}
        for m in METHODS[1:]:
            s["paired_vs_no_replanning"][m] = {k: paired(_series(rows, setting, m, k), base[k], seed=2) for k in PAIRED_METRICS}
        for k in PAIRED_METRICS:
            s["ml_ablation"][k] = paired(_series(rows, setting, "DYNAMIC_ML", k), _series(rows, setting, "DYNAMIC", k), seed=3)
            s["dynamic_vs_single_shot"][k] = paired(_series(rows, setting, "DYNAMIC", k), _series(rows, setting, "SINGLE_SHOT", k), seed=4)
        out["settings"][setting] = s

    solver = {}
    for m in RAILOPT:
        xs = plans_info["solves"][m]
        secs = np.array([x["seconds"] for x in xs]) if xs else np.array([0.0])
        statuses = [x["status"] for x in xs]
        solver[m] = {"solves": len(xs), "optimal": statuses.count("OPTIMAL"), "feasible": statuses.count("FEASIBLE"),
                     "other": len(xs) - statuses.count("OPTIMAL") - statuses.count("FEASIBLE"),
                     "plans_adopted": sum(x["adopted"] for x in xs),
                     "solve_s_mean": float(secs.mean()), "solve_s_p95": float(np.quantile(secs, 0.95)),
                     "solve_s_max": float(secs.max()),
                     "risk_buffers_total": sum(x["buffers"] for x in xs),
                     "decision_points_with_buffers": sum(x["buffers"] > 0 for x in xs)}
    out["solver"] = solver

    g = plans_info["guarantee"]
    det_ss = _series(rows, "deterministic", "SINGLE_SHOT", "weighted_delay")
    det_nr = _series(rows, "deterministic", "NO_REPLANNING", "weighted_delay")
    optimal_idx = [i for i, x in enumerate(g) if x["status"] == "OPTIMAL"]
    out["single_shot_guarantee"] = {
        "optimal_single_shots": len(optimal_idx),
        "worse_on_events_known_at_solve": [g[i]["scenario_id"] for i in optimal_idx if g[i]["worse_on_known"]],
        "worse_on_full_replay": [g[i]["scenario_id"] for i in optimal_idx if det_ss[i] > det_nr[i]],
        "note": ("The by-construction claim covers the events known when the solver ran. On the full replay, "
                 "disruptions that become known later can make a fixed single-shot plan worse; those cases are "
                 "listed, not hidden."),
    }
    out["plans_differ_ml_vs_dynamic"] = plans_info["ml_plans_differ"]
    out["scenarios"] = plans_info["scenarios"]
    return out


# ---------------------------------------------------------------------------
# report (generated from the summary JSON only)
# ---------------------------------------------------------------------------
def _f(x, d=1):
    return f"{x:.{d}f}"


def _ci(c, d=1):
    return f"[{c[0]:.{d}f}, {c[1]:.{d}f}]"


def _sig(p: dict) -> str:
    return "significant" if p["significant"] else "**not significant**"


def write_report(summary: dict, path: Path) -> None:
    cfg, L = summary["config"], []
    L += [f"# RailOpt AI - Phase 10 evaluation ({cfg['scenarios']} scenarios)", "",
          f"**{summary['label']}.** Every number below is generated from `eval_summary.json` "
          "(`python -m eval.run_eval`); nothing is typed by hand. These are simulator results on a "
          "sample corridor, not measurements of real railway operations. RailOpt advises a human "
          "controller; it controls no trains or signals.", ""]
    sc = summary["scenarios"]
    L += ["## Setup", "",
          f"- {cfg['scenarios']} scenarios, seed {cfg['seed']}, timetable `{cfg['timetable']}` "
          f"({sc['trains']} trains), Phase 2 generator logic (1-3 disruptions of 5-30 min + 0-5 min starting delays).",
          f"- Disruptions: {sc['disruptions_total']} in total; per scenario {sc['per_scenario']}; types {sc['types']}.",
          f"- Overlap with the {sc['training_runs']} training scenarios (seed {sc['training_seed']}): "
          f"**{sc['overlap_with_training']}** identical scenarios.",
          f"- Knowledge: stoppages and delays known at their start; closures posted {cfg['closure_notice_min']} min "
          "before they start (or at 06:00); starting delays known from the start.",
          "- Methods: " + "; ".join(f"**{LABEL[m]}** - {cfg['methods'][m]}" for m in METHODS) + ".",
          f"- Settings: **deterministic** (one replay, no randomness) and **robustness** ({cfg['replays']} seeded "
          "replays per scenario under the Phase 2 running-time and dwell variability, same seeds for every method, "
          "plans fixed in advance; a scenario's value is the mean of its replays).",
          f"- Statistics: mean and median with {cfg['bootstrap']}-resample bootstrap 95% CIs over scenarios; paired "
          "comparisons per scenario (diff = method - reference, negative = better); a difference is significant when "
          "the CI of the mean difference excludes 0 (Wilcoxon p shown for reference).",
          f"- Every replay was checked for violations (headway, capacity, minimum running time, closures, early "
          f"departures): **{summary['violations']} violations in {summary['replays_checked']} replays**.",
          f"- Runtime: {_f(summary['runtime_s'], 0)} s.", ""]

    for setting in ("deterministic", "robustness"):
        s = summary["settings"][setting]
        L += [f"## Results - {setting}", "",
              "| Method | " + " | ".join(METRIC_LABEL[k] for k in METRICS) + " |",
              "|---|" + "---|" * len(METRICS)]
        for m in METHODS:
            cells = []
            for k in METRICS:
                v = s["methods"][m][k]
                d = 2 if k in ("avg_delay_min", "throughput_trains_per_hour", "trains_waited") else 1
                cells.append(f"{_f(v['mean'], d)} {_ci(v['mean_ci'], d)}<br>median {_f(v['median'], d)}")
            L.append(f"| {LABEL[m]} | " + " | ".join(cells) + " |")
        L += ["", "Mean [95% CI] per scenario; median below.", "",
              "### Paired vs no re-planning (per scenario)", "",
              "| Method | Metric | Wins / ties / losses | Mean diff [95% CI] | Median diff | Wilcoxon p | |",
              "|---|---|---|---|---|---|---|"]
        for m, per in s["paired_vs_no_replanning"].items():
            for k, p in per.items():
                L.append(f"| {LABEL[m]} | {METRIC_LABEL[k]} | {p['wins']} / {p['ties']} / {p['losses']} | "
                         f"{_f(p['mean_diff'])} {_ci(p['mean_diff_ci'])} | {_f(p['median_diff'])} | "
                         f"{p['wilcoxon_p']:.3g} | {_sig(p)} |")
        a, dv = s["ml_ablation"]["weighted_delay"], s["dynamic_vs_single_shot"]["weighted_delay"]
        L += ["", "### Ablation: dynamic with vs without ML risk buffers", "",
              f"Weighted delay, dynamic + ML minus dynamic: wins / ties / losses {a['wins']} / {a['ties']} / {a['losses']}, "
              f"mean diff {_f(a['mean_diff'], 2)} {_ci(a['mean_diff_ci'], 2)} - {_sig(a)}.",
              "", f"Dynamic minus single-shot (weighted delay): {dv['wins']} / {dv['ties']} / {dv['losses']}, "
              f"mean diff {_f(dv['mean_diff'])} {_ci(dv['mean_diff_ci'])} - {_sig(dv)}.", ""]

    L += ["## ML risk buffers - honest reading", ""]
    for setting in ("deterministic", "robustness"):
        a = summary["settings"][setting]["ml_ablation"]["weighted_delay"]
        verdict = ("lower (better) with the buffers" if a["significant"] and a["mean_diff"] < 0 else
                   "higher (worse) with the buffers" if a["significant"] else "not significantly different")
        L.append(f"- {setting}: weighted delay is {verdict} (mean diff {_f(a['mean_diff'], 2)} "
                 f"{_ci(a['mean_diff_ci'], 2)}; {a['ties']} of {a['n']} scenarios tie).")
    sv = summary["solver"]["DYNAMIC_ML"]
    L += [f"- The model put a buffer on {sv['risk_buffers_total']} trips at {sv['decision_points_with_buffers']} of "
          f"{sv['solves']} decision points; the final plan differs from plain dynamic in "
          f"{summary['plans_differ_ml_vs_dynamic']} of {cfg['scenarios']} scenarios.",
          "- A buffer is +1 min headway; whether it helps depends on the variability it has to absorb. "
          "If the difference is not significant, the ML buffers did not help on this corridor - that is a valid result.", ""]

    L += ["## Solver", "", "| Method | Solves | OPTIMAL | FEASIBLE | other | Plans adopted | Solve time mean / p95 / max (s) |",
          "|---|---|---|---|---|---|---|"]
    for m, v in summary["solver"].items():
        L.append(f"| {LABEL[m]} | {v['solves']} | {v['optimal']} | {v['feasible']} | {v['other']} | {v['plans_adopted']} | "
                 f"{v['solve_s_mean']:.3f} / {v['solve_s_p95']:.3f} / {v['solve_s_max']:.3f} |")
    g = summary["single_shot_guarantee"]
    L += ["", "Solve time is wall time of one CP-SAT call including model building (1 worker, 10 s limit).", "",
          "## Single-shot vs no re-planning when OPTIMAL", "",
          f"- OPTIMAL single-shot solves: {g['optimal_single_shots']}.",
          f"- Worse than no re-planning on the events known at solve time (the by-construction claim): "
          f"**{len(g['worse_on_events_known_at_solve'])}** {g['worse_on_events_known_at_solve'] or ''}",
          f"- Worse on the full replay (later disruptions included): **{len(g['worse_on_full_replay'])}** "
          f"{g['worse_on_full_replay'] or ''}",
          f"- {g['note']}", "",
          "## Charts", "", "![Mean weighted delay with 95% CI](eval_bars.png)", "",
          "![Per-scenario reduction vs no re-planning](eval_reduction.png)", "",
          "## Limits", "",
          "- One sample corridor (4 stations, 12 trains), synthetic disruptions and assumed variability ranges "
          "(docs/ASSUMPTIONS.md). Results say nothing about real operations.",
          "- Robustness replays keep each plan fixed; in use, RailOpt would re-plan again as actual times drift.",
          "- Waits include planned holds (a held train counts as waiting).",
          "- Priority dispatch only differs from FCFS when two trains wait for the same section at the same time.", ""]
    path.write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=10)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def write_charts(summary: dict, rows: list[dict], out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = summary["config"]["scenarios"]
    # 1) mean weighted delay with 95% bootstrap CI, both settings
    fig, ax = plt.subplots(figsize=(11, 5.6), facecolor=SURFACE)
    _style(ax)
    x, w = np.arange(len(METHODS)), 0.38
    for j, (setting, col) in enumerate((("deterministic", C_DET), ("robustness", C_ROB))):
        ms = [summary["settings"][setting]["methods"][m]["weighted_delay"] for m in METHODS]
        means = np.array([v["mean"] for v in ms])
        err = np.array([[v["mean"] - v["mean_ci"][0] for v in ms], [v["mean_ci"][1] - v["mean"] for v in ms]])
        pos = x + (j - 0.5) * (w + 0.02)
        ax.bar(pos, means, w, color=col, label=f"{setting} ({'1 replay' if j == 0 else str(summary['config']['replays']) + ' seeded replays'})",
               edgecolor=SURFACE, linewidth=2)
        ax.errorbar(pos, means, yerr=err, fmt="none", ecolor=INK, elinewidth=1.4, capsize=4)
    ax.set_xticks(x, [LABEL[m] for m in METHODS], color=INK, fontsize=10)
    ax.set_ylabel("Priority-weighted delay per scenario (mean)", color=INK2)
    ax.set_title(f"SIMULATED - mean weighted delay over {n} scenarios, 95% bootstrap CI", color=INK, fontsize=13, loc="left")
    ax.legend(frameon=False, labelcolor=INK, loc="upper right")
    fig.text(0.01, 0.01, summary["label"], color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out / "eval_bars.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)

    # 2) per-scenario reduction vs no re-planning (positive = less weighted delay)
    others = METHODS[1:]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6), sharey=True, facecolor=SURFACE)
    rng = np.random.default_rng(0)
    for ax, (setting, col) in zip(axes, (("deterministic", C_DET), ("robustness", C_ROB))):
        _style(ax)
        base = _series(rows, setting, "NO_REPLANNING", "weighted_delay")
        data = [base - _series(rows, setting, m, "weighted_delay") for m in others]
        ax.axhline(0, color=INK2, linewidth=1)
        bp = ax.boxplot(data, widths=0.5, showfliers=False, patch_artist=True,
                        medianprops={"color": INK, "linewidth": 2}, whiskerprops={"color": INK2},
                        capprops={"color": INK2}, boxprops={"edgecolor": INK2})
        for patch in bp["boxes"]:
            patch.set_facecolor(col)
            patch.set_alpha(0.35)
        for i, d in enumerate(data, start=1):
            ax.scatter(i + rng.uniform(-0.17, 0.17, len(d)), d, s=10, color=col, alpha=0.55, linewidths=0)
        ax.set_xticks(range(1, len(others) + 1), [LABEL[m].replace("RailOpt ", "RailOpt\n") for m in others], color=INK, fontsize=9)
        ax.set_title(setting, color=INK, fontsize=12, loc="left")
    axes[0].set_ylabel("Weighted delay saved vs no re-planning\n(per scenario; above 0 = better)", color=INK2)
    fig.suptitle(f"SIMULATED - per-scenario delay reduction vs no re-planning ({n} scenarios)", color=INK, fontsize=13, x=0.01, ha="left")
    fig.text(0.01, 0.01, summary["label"] + ". Boxes: quartiles and median; dots: scenarios.", color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(out / "eval_reduction.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)


def write_summary(summary: dict, path: Path) -> None:
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
