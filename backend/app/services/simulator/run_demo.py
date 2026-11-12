"""Run the T101 scenario and print a before/after timeline.

Usage (from the backend folder):
    python -m app.services.simulator.run_demo

All numbers are SIMULATED on the sample corridor A-B-C-D.
"""
from __future__ import annotations

from app.services.network import format_time, load_network
from app.services.network.model import DEFAULT_DATA_DIR
from app.services.simulator import find_violations, load_events, simulate


def print_run(title, net, result, disruptions=None) -> None:
    print(f"\n=== {title} ===")
    print(f"{'Train':<6}{'Section':<10}{'Ready':>7}{'Enter':>7}{'Exit':>7}{'Wait':>6}{'Stop':>6}")
    for o in result.occupancies:
        print(f"{o.train_id:<6}{o.section_id:<10}{format_time(o.requested):>7}{format_time(o.entry):>7}"
              f"{format_time(o.exit):>7}{o.wait:>6}{o.stopped_min:>6}")
    print("\nArrival delay at destination (min):",
          {t: result.final_delay(t) for t in sorted(net.schedules)})
    print("Metrics:", result.metrics())
    for line in result.applied_events:
        print("  applied:", line)
    for line in result.ignored_events:
        print("  ignored:", line)
    problems = find_violations(net, result, disruptions)
    print("Safety check:", "OK - no capacity, headway or closure violations" if not problems else problems)


def main() -> None:
    net = load_network()
    print_run("Normal day (no disruption)", net, simulate(net))
    events = load_events(DEFAULT_DATA_DIR / "events_t101.csv")
    print_run("T101 stops in B-C at 10:03 for 15 min (no re-planning)", net, simulate(net, events), events)
    print("\n(SIMULATED results on a sample corridor. Not real railway data.)")


if __name__ == "__main__":
    main()
