"""Compare re-planning strategies and baselines for the T101 scenario.

Usage (from the backend folder):
    python -m app.services.optimizer.run_demo

Every number comes from replaying each plan through the simulator.
All results are SIMULATED on the sample corridor A-B-C-D.
"""
from __future__ import annotations

from app.services.network import format_time, load_network
from app.services.network.model import DEFAULT_DATA_DIR
from app.services.optimizer import SIMULATED_LABEL, compare
from app.services.optimizer.config import PRIORITY_WEIGHTS, REROUTE_PENALTY
from app.services.simulator import load_events


def print_table(title: str, net, results, show_trains: list[str]) -> None:
    print(f"\n=== {title} ===")
    head = (f"{'Strategy':<18}{'CP-SAT status':<15}{'Solve s':>8}{'Weighted':>10}{'Total':>7}"
            + "".join(f"{t:>6}" for t in show_trains) + f"{'Trains/h':>10}{'Violations':>12}")
    print(head)
    print("-" * len(head))
    for r in results:
        solve_s = f"{r.solve_seconds:.3f}" if r.solve_seconds is not None else "-"
        if r.replay is None:
            print(f"{r.name:<18}{r.status:<15}{solve_s:>8}   no plan: {r.message}")
            continue
        print(f"{r.name:<18}{r.status:<15}{solve_s:>8}{r.weighted_delay:>10}{r.total_delay:>7}"
              + "".join(f"{r.delays[t]:>6}" for t in show_trains)
              + f"{r.throughput:>10}{len(r.violations):>12}")
    print("\nActions (from each replay):")
    for r in results:
        if r.kind == "strategy" and r.replay is not None:
            print(f"  {r.name}: " + ("; ".join(r.actions) if r.actions else "none"))
            if r.mismatches:
                print(f"    solver/replay mismatches: {r.mismatches}")
            if r.status != "OPTIMAL":
                print(f"    note: {r.message}")


def main() -> None:
    events = load_events(DEFAULT_DATA_DIR / "events_t101.csv")
    state_time = events[0].start
    print(f"State time {format_time(state_time)}. Weights {PRIORITY_WEIGHTS}, reroute penalty {REROUTE_PENALTY}.")
    print("Delay columns = arrival delay at destination (min). Weighted = sum(weight x delay).")
    print("CP-SAT status OPTIMAL = proven optimal for that strategy's model; FEASIBLE = not proven.")

    ref = load_network()
    print_table("T101 stops in B-C at 10:03 for 15 min (reference, 3 trains)",
                ref, compare(ref, state_time, events), ["T101", "T202", "T303"])

    full = load_network(timetable="full_day")
    print_table("Same event on the full-day timetable (12 trains)",
                full, compare(full, state_time, events), ["T101", "T202", "T303", "T103", "T403", "T502"])

    print(f"\n({SIMULATED_LABEL}. Advice for a human controller; nothing here controls trains or signals.)")


if __name__ == "__main__":
    main()
