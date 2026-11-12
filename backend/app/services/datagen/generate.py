"""CLI: generate the SIMULATED training table and its dataset card.

Usage (from the backend folder):
    python -m app.services.datagen.generate --runs 3000 --seed 42

Writes data/generated/training_rows.csv and data/generated/dataset_card.json
(the folder is gitignored).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.services.datagen.generator import SIMULATED_NOTE, dataset_card, generate
from app.services.network.model import DEFAULT_DATA_DIR


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate SIMULATED training rows.")
    parser.add_argument("--runs", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=DEFAULT_DATA_DIR / "generated")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    df = generate(args.runs, args.seed)
    elapsed = time.perf_counter() - started

    args.out.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out / "training_rows.csv", index=False)
    card = dataset_card(df, args.runs, args.seed)
    (args.out / "dataset_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")

    rv = card["rule_vs_label"]
    print(f"\n=== {SIMULATED_NOTE} ===")
    print(f"runs {args.runs}, seed {args.seed}, rows {card['rows']}, generated in {elapsed:.1f} s")
    print(f"conflict rate (label_conflict):      {card['conflict_rate']:.1%}")
    print(f"rule flag rate (rule_flags_conflict): {card['rule_flag_rate']:.1%}")
    print(f"rules disagree with labels:          {rv['disagreement_rate']:.1%} "
          f"(rule only {rv['rule_only']}, label only {rv['label_only']}, "
          f"both {rv['both_conflict']}, neither {rv['neither']})")
    w, d = card["label_wait_min_when_conflict"], card["label_delay_min_per_row"]
    print(f"wait when conflict (min):            mean {w['mean']}, max {w['max']}")
    print(f"delay at destination (min, per row): mean {d['mean']}, max {d['max']}")
    print(f"stoppages that missed their train after variability: {card['ignored_stoppages']}")
    print(f"wrote {args.out / 'training_rows.csv'} and dataset_card.json")


if __name__ == "__main__":
    main()
