"""Static charts for the PDF reports (matplotlib, print / light surface).

Each chart is drawn only from an API payload (timeline rows, the evaluation summary and its
distribution); nothing is recomputed or typed in. Colours: the validated categorical palette of
the dataviz reference (slots in a fixed order, never cycled), hairline grid, one y-axis.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
CRITICAL = "#d03b3b"
BASELINE_GREY = "#a9a79f"


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=7.5)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _fig(w, h):
    plt.rcParams["font.family"] = font_manager.FontProperties(family="DejaVu Sans").get_name()
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("white")
    _style(ax)
    return fig, ax


def _hhmm(m, _pos=None) -> str:
    m = int(round(m))
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------------------------------------------------------------------
# time-distance chart (scenario report)
# ---------------------------------------------------------------------------
def timeline_chart(tl: dict, trains: dict[str, dict], at_min: int | None = None):
    """tl = the /api/timeline payload; trains = {train_id: {train_type, priority}} from /api/state.
    Planned = thin dashed grey; actual = solid, coloured by train type (priority order);
    standing still = thick segment; closures = hatched blocks; the clock = a vertical rule."""
    fig, ax = _fig(10.5, 5.6)
    types = sorted({v["train_type"] for v in trains.values()},
                   key=lambda t: min(v["priority"] for v in trains.values() if v["train_type"] == t))
    colour = {t: SERIES[i] for i, t in enumerate(types[:len(SERIES)])}
    for r in tl["planned"]:
        ax.plot([r["entry_min"], r["exit_min"]], [r["from_km"], r["to_km"]], color=BASELINE_GREY,
                linewidth=0.8, linestyle=(0, (3, 2)), zorder=1)
    ends: dict[str, tuple[float, float]] = {}
    starts: dict[str, tuple[float, float]] = {}
    for r in tl["actual"]:
        typ = trains.get(r["train_id"], {}).get("train_type")
        c = colour.get(typ, INK2)
        ax.plot([r["entry_min"], r["exit_min"]], [r["from_km"], r["to_km"]], color=c, linewidth=1.6,
                solid_capstyle="round", zorder=3, linestyle="-" if not r.get("alternate") else (0, (1, 1)))
        span = r["exit_min"] - r["entry_min"]
        for s in r.get("stops", []):
            if span > 0:
                f0 = (s["start_min"] - r["entry_min"]) / span
                f1 = (s["end_min"] - r["entry_min"]) / span
                km = lambda f: r["from_km"] + f * (r["to_km"] - r["from_km"])  # noqa: E731
                ax.plot([s["start_min"], s["end_min"]], [km(f0), km(f1)], color=CRITICAL, linewidth=3.2,
                        solid_capstyle="round", zorder=4)
        if r["train_id"] not in starts or r["entry_min"] < starts[r["train_id"]][0]:
            starts[r["train_id"]] = (r["entry_min"], r["from_km"])
        if r["train_id"] not in ends or r["exit_min"] > ends[r["train_id"]][0]:
            ends[r["train_id"]] = (r["exit_min"], r["to_km"])
    for b in tl.get("closures", []):
        ax.fill_between([b["start_min"], b["end_min"]], b["from_km"], b["to_km"], facecolor="none",
                        edgecolor=CRITICAL, hatch="////", linewidth=0.6, zorder=2)
    if len(starts) <= 16:                               # direct labels only while they stay legible
        for tid, (x, y) in starts.items():
            ax.annotate(tid, (x, y), xytext=(-2, 3), textcoords="offset points", fontsize=6.5, color=INK2,
                        ha="right", zorder=5)
    if at_min is not None:
        ax.axvline(at_min, color=INK, linewidth=0.8, zorder=5)
        ax.annotate(f"clock {_hhmm(at_min)}", (at_min, 1), xycoords=("data", "axes fraction"), xytext=(3, -10),
                    textcoords="offset points", fontsize=7, color=INK)
    stations = sorted(tl["stations"], key=lambda s: s["km"])
    ax.set_yticks([s["km"] for s in stations], [s["code"] for s in stations])
    ax.xaxis.set_major_formatter(_hhmm)
    xs = [r["entry_min"] for r in tl["actual"] + tl["planned"]] + [r["exit_min"] for r in tl["actual"] + tl["planned"]]
    if xs:
        ax.set_xlim(min(xs) - 5, max(xs) + 5)
    ax.set_xlabel("time", color=INK2, fontsize=8)
    ax.set_ylabel("distance (station)", color=INK2, fontsize=8)
    handles = [plt.Line2D([], [], color=colour[t], linewidth=1.6, label=f"{t} (actual)") for t in colour]
    handles += [plt.Line2D([], [], color=BASELINE_GREY, linewidth=0.8, linestyle=(0, (3, 2)), label="timetable"),
                plt.Line2D([], [], color=CRITICAL, linewidth=3.2, label="standing still")]
    if tl.get("closures"):
        handles.append(matplotlib.patches.Patch(facecolor="none", edgecolor=CRITICAL, hatch="////", label="closure"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=min(len(handles), 6),
              frameon=False, fontsize=7)
    return fig


# ---------------------------------------------------------------------------
# evaluation charts
# ---------------------------------------------------------------------------
def eval_bars(summary: dict, methods: list[str], labels: dict[str, str], baselines: set[str],
              metric: str = "weighted_delay"):
    """Mean weighted delay with 95% bootstrap CI whiskers per method, deterministic and robustness
    side by side (small multiples, one shared y-axis)."""
    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.6), sharey=True)
    fig.patch.set_facecolor("white")
    for ax, setting in zip(axes, ("deterministic", "robustness")):
        _style(ax)
        ax.grid(axis="x", visible=False)
        ms = summary["settings"][setting]["methods"]
        for i, m in enumerate(methods):
            d = ms[m][metric]
            c = BASELINE_GREY if m in baselines else SERIES[0]
            ax.bar(i, d["mean"], width=0.62, color=c, zorder=2)
            ax.errorbar(i, d["mean"], yerr=[[d["mean"] - d["mean_ci"][0]], [d["mean_ci"][1] - d["mean"]]],
                        color=INK, linewidth=0.9, capsize=3, zorder=3)
            ax.annotate(f"{d['mean']:.1f}", (i, d["mean_ci"][1]), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=7, color=INK)
        ax.set_xticks(range(len(methods)), [labels.get(m, m) for m in methods], rotation=18, ha="right", fontsize=7)
        ax.set_title(setting, fontsize=8.5, color=INK, loc="left")
    axes[0].set_ylabel("mean weighted delay per scenario", color=INK2, fontsize=8)
    fig.tight_layout()
    return fig


def eval_reduction(distribution: dict, methods: list[str], labels: dict[str, str]):
    """Per-scenario reduction in weighted delay vs no re-planning: box (q1-median-q3) and whiskers,
    as summarised by the API from eval_results.csv. Positive = less delay than no re-planning."""
    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.2), sharey=True)
    fig.patch.set_facecolor("white")
    for ax, setting in zip(axes, ("deterministic", "robustness")):
        _style(ax)
        ax.grid(axis="y", visible=False)
        ms = distribution[setting]["methods"]
        shown = [m for m in methods if m in ms]
        for i, m in enumerate(shown):
            d = ms[m]
            ax.plot([d["whisker_low"], d["whisker_high"]], [i, i], color=INK2, linewidth=0.9, zorder=2)
            ax.add_patch(matplotlib.patches.Rectangle((d["q1"], i - 0.26), d["q3"] - d["q1"], 0.52,
                                                      facecolor="#b7d3f6", edgecolor=SERIES[0], linewidth=0.9,
                                                      zorder=3))
            ax.plot([d["median"], d["median"]], [i - 0.26, i + 0.26], color=SERIES[0], linewidth=2, zorder=4)
            ax.plot([d["mean"]], [i], marker="o", markersize=4, color=INK, zorder=5)
        ax.axvline(0, color=AXIS, linewidth=1)
        ax.set_yticks(range(len(shown)), [labels.get(m, m) for m in shown], fontsize=7)
        ax.set_title(setting, fontsize=8.5, color=INK, loc="left")
        ax.set_xlabel("weighted delay saved vs no re-planning (per scenario)", color=INK2, fontsize=7.5)
    fig.tight_layout()
    return fig
