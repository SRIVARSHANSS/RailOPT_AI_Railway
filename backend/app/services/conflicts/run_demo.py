"""Print predicted conflicts for the T101 scenario.

Usage (from the backend folder):
    python -m app.services.conflicts.run_demo

All numbers are SIMULATED on the sample corridor A-B-C-D.
"""
from __future__ import annotations

from app.services.conflicts import SIMULATED_LABEL, detect_conflicts, estimate_cascade, project_plan
from app.services.network import format_time, load_network, parse_time
from app.services.network.model import DEFAULT_DATA_DIR
from app.services.simulator import load_events


def main() -> None:
    net = load_network()
    events = load_events(DEFAULT_DATA_DIR / "events_t101.csv")
    state_time = parse_time("10:03")

    plan = project_plan(net, state_time, events)
    print(f"\n=== Planned occupancy at {format_time(state_time)} (no train waits for another) ===")
    print(f"{'Train':<6}{'Section':<10}{'Entry':>7}{'Exit':>7}{'Stop':>6}")
    for t in plan.trips:
        print(f"{t.train_id:<6}{t.section_id:<10}{format_time(t.entry):>7}{format_time(t.exit):>7}{t.stopped_min:>6}")
    for line in plan.applied_events:
        print("  applied:", line)

    conflicts = detect_conflicts(net, plan)
    print(f"\n=== Predicted conflicts ({len(conflicts)}) ===")
    print(f"{'ID':<4}{'Section':<9}{'Earlier':<8}{'Later':<7}{'Type':<9}{'Planned':>8}{'Needs':>7}"
          f"{'Short':>7}{'In (min)':>10}  Severity")
    for c in conflicts:
        print(f"{c.conflict_id:<4}{c.section_id:<9}{c.earlier or '-':<8}{c.later:<7}{c.conflict_type:<9}"
              f"{format_time(c.window_start):>8}{format_time(c.window_end):>7}{c.minutes_short:>7}"
              f"{c.time_to_conflict:>10}  {c.severity}")

    for c in conflicts:
        report = estimate_cascade(net, events, c)
        print(f"\n=== Knock-on for {c.conflict_id} if nothing is re-planned (source: {report.source_train}) ===")
        print(f"{'Train':<6}{'Wait before ' + c.section_id:>18}{'Delay at destination':>23}")
        for i in report.impacts:
            marker = "  (source)" if i.train_id == report.source_train else ""
            print(f"{i.train_id:<6}{i.wait_at_section_min:>18}{i.final_delay_min:>23}{marker}")
        print(f"Total delay: {report.total_delay_min} min")

    print(f"\n({SIMULATED_LABEL}.)")


if __name__ == "__main__":
    main()
