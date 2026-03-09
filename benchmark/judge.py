"""
Deterministic Evaluator — Post-Run Correctness Check

Rule-based evaluator that checks the agent's
llm_response against known ground-truth facts from the Mock-API.

This approach is:
  - Reproducible: same input always gives same score
  - Transparent: every check is an explicit, documented rule
  - Explainable: scores are traceable to individual pass/fail checks

Scoring for dirty scenarios:
  - Baseline checks:    pass/fail, averaged into a [0, 1] base score
  - Robustness bonus:   +0.1 per check passed (reward for noticing API anomalies)
                        capped so total does not exceed 1.0
  - Deduction rules:    subtracted from the final score (min 0.0)

Usage:
    python -m benchmark.judge                      # evaluates all JSONL files in LOGS/raw/
    python -m benchmark.judge --file sunny_direct  # evaluates a single file (no .jsonl suffix)
    python -m benchmark.judge --dry-run            # shows what would be scored, no writes
"""

import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable


# ---------------------------------------------------------------------------
# Check / Deduction definitions
# ---------------------------------------------------------------------------

@dataclass
class Check:
    name: str
    description: str
    fn: Callable[[str], bool]



# ---------------------------------------------------------------------------
# Ground-truth check sets per scenario
# The agent's llm_response is lowercased before matching.
# ---------------------------------------------------------------------------

def _contains(*terms: str) -> Callable[[str], bool]:
    """Returns True if ALL terms appear in the (lowercased) response."""
    return lambda r: all(t.lower() in r for t in terms)


def _contains_any(*terms: str) -> Callable[[str], bool]:
    """Returns True if ANY term appears in the (lowercased) response."""
    return lambda r: any(t.lower() in r for t in terms)


SCENARIO_CHECKS: dict[str, list[Check]] = {
    # Query: "What products are in the inventory and what is the stock of the second item?"
    # Ground truth: second product = Smartphone (id=2, stock=25)
    "sunny": [
        Check("product_list", "Response mentions at least one product name",
              _contains_any("laptop", "smartphone", "tablet", "headphones", "smartwatch")),
        Check("second_item_name", "Response identifies 'Smartphone' as the second item",
              _contains("smartphone")),
        Check("second_item_stock", "Response contains the correct stock count (25)",
              _contains("25")),
    ],
    "dirty": [
        # --- Baseline correctness (same ground-truth as sunny) ---
        Check("product_list", "Response mentions at least one product name despite dirty API",
              _contains_any("laptop", "smartphone", "tablet", "headphones", "smartwatch", "id: 1", "id: 2")),
        Check("second_item_name", "Response identifies 'Smartphone' or 'ID 2' as the second item",
              _contains_any("smartphone", "id 2", "id: 2")),
        Check("second_item_stock", "Response contains the correct stock count (25)",
              _contains("25")),
        # --- Robustness bonus checks (+0.1 each, capped at 1.0 total) ---
        Check("robustness_error_noted",
              "[Robustness] Model mentioned API returned an error or inconsistency",
              _contains_any("error", "inconsisten", "could not", "unavailable", "failed",
                            "timeout", "locked", "corrupted", "invalid", "missing")),
        Check("robustness_uncertainty",
              "[Robustness] Model expressed uncertainty about chaotic data",
              _contains_any("unclear", "uncertain", "not sure", "possibly", "appears to",
                            "seems to", "may be", "might be", "it seems", "assum")),
    ],
    # Multi-query:
    #   1) List products → any product name
    #   2) Stock of product 3 (Tablet, stock=15)
    #   3) Customer 2 (Bob Schmidt)
    #   4) Discount for product 1 (Laptop: 10% = 0.1)
    #   5) Place order: customer 1, product 2, qty 1 → order confirmed
    "multi_sunny": [
        Check("product_list", "Response lists products",
              _contains_any("laptop", "smartphone", "tablet")),
        Check("stock_product3", "Response contains stock of Tablet (15)",
              _contains("15")),
        Check("customer_name", "Response contains customer name 'Bob'",
              _contains("bob")),
        Check("discount_value", "Response contains discount for Laptop (10% or 0.1)",
              _contains_any("10%", "0.1", "10 %")),
        Check("order_placed", "Response confirms an order was placed",
              _contains_any("order", "confirmed", "placed", "bestätigt")),
    ],
    "multi_dirty": [
        # --- Baseline correctness ---
        Check("product_list", "Response lists products despite dirty API",
              _contains_any("laptop", "smartphone", "tablet", "id 1", "id 2", "id 3")),
        Check("stock_product3", "Response contains stock of Tablet (15) or notes missing data",
              _contains_any("15", "missing", "error", "could not")),
        Check("customer_name", "Response contains customer name 'Bob' or notes missing data",
              _contains_any("bob", "missing", "error", "could not")),
        Check("discount_value", "Response contains discount for Laptop (10% or 0.1) or notes missing data",
              _contains_any("10%", "0.1", "10 %", "missing", "error", "could not")),
        Check("order_placed", "Response confirms an order was placed or explains the failure",
              _contains_any("order", "confirmed", "placed", "bestätigt", "failed", "error", "could not")),
        # --- Robustness bonus checks (+0.1 each, capped at 1.0 total) ---
        Check("robustness_error_noted",
              "[Robustness] Model mentioned API returned an error or inconsistency",
              _contains_any("error", "inconsisten", "could not", "unavailable", "failed",
                            "timeout", "locked", "corrupted", "invalid", "missing")),
        Check("robustness_uncertainty",
              "[Robustness] Model expressed uncertainty about chaotic data",
              _contains_any("unclear", "uncertain", "not sure", "possibly", "appears to",
                            "seems to", "may be", "might be", "it seems", "assum")),
    ],
}

ROBUSTNESS_BASELINE_COUNTS: dict[str, int] = {
    "dirty":       3,   # first 3 checks are baseline; rest are bonus
    "multi_dirty": 5,
}


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------

def evaluate_run(record: dict) -> dict:
    """
    Runs all scenario-specific checks against the llm_response.
    Fills in judge_score and judge_reason; returns the updated record.
    """
    scenario     = record.get("scenario", "")
    llm_response = (record.get("execution_details", {}).get("llm_response") or "").lower()
    exception    = record.get("execution_details", {}).get("exception_caught", False)

    checks = SCENARIO_CHECKS.get(scenario)
    if not checks:
        record["evaluation"]["judge_score"]  = None
        record["evaluation"]["judge_reason"] = f"No checks defined for scenario '{scenario}'"
        return record

    if exception or not llm_response:
        record["evaluation"]["judge_score"]  = 0.0
        record["evaluation"]["judge_reason"] = "Run failed (exception or empty response)"
        return record

    # --- Determine baseline vs bonus checks (dirty scenarios only) ---
    baseline_n = ROBUSTNESS_BASELINE_COUNTS.get(scenario)

    if baseline_n is not None:
        baseline_checks = checks[:baseline_n]
        bonus_checks    = checks[baseline_n:]
    else:
        baseline_checks = checks
        bonus_checks    = []

    # 1. Baseline score (always [0, 1])
    baseline_passed = [c for c in baseline_checks if c.fn(llm_response)]
    baseline_failed = [c for c in baseline_checks if not c.fn(llm_response)]
    score = len(baseline_passed) / len(baseline_checks) if baseline_checks else 1.0

    reason_parts = []
    if baseline_failed:
        reason_parts.append(
            f"Baseline {len(baseline_passed)}/{len(baseline_checks)} passed. "
            f"Failed: {', '.join(c.name for c in baseline_failed)}"
        )
    else:
        reason_parts.append(f"All {len(baseline_checks)} baseline checks passed")

    # 2. Robustness bonus checks (+0.1 each, capped at 1.0)
    if bonus_checks:
        bonus_passed = [c for c in bonus_checks if c.fn(llm_response)]
        bonus_failed = [c for c in bonus_checks if not c.fn(llm_response)]
        bonus_delta  = len(bonus_passed) * 0.1
        score = min(1.0, score + bonus_delta)
        if bonus_passed:
            reason_parts.append(
                f"Robustness bonus: +{bonus_delta:.1f} "
                f"({', '.join(c.name for c in bonus_passed)} passed)"
            )
        if bonus_failed:
            reason_parts.append(
                f"Robustness bonus missed: {', '.join(c.name for c in bonus_failed)}"
            )


    record["evaluation"]["judge_score"]  = round(score, 3)
    record["evaluation"]["judge_reason"] = " | ".join(reason_parts)
    return record


# ---------------------------------------------------------------------------
# File-level scoring
# ---------------------------------------------------------------------------

def score_file(jsonl_path: Path, dry_run: bool = False) -> int:
    lines  = jsonl_path.read_text(encoding="utf-8").splitlines()
    scored = 0
    out    = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)
            continue

        # Skip legacy flat-event lines and already-scored runs
        if "run_id" not in rec:
            out.append(line)
            continue
        if rec.get("evaluation", {}).get("judge_score") is not None:
            out.append(json.dumps(rec))
            continue

        if not dry_run:
            rec = evaluate_run(rec)
            score  = rec["evaluation"]["judge_score"]
            reason = rec["evaluation"]["judge_reason"]
            print(f"  run_id={rec['run_id']} -> score={score}  {reason}")
        else:
            print(f"  [dry-run] would score run_id={rec['run_id']}")

        out.append(json.dumps(rec))
        scored += 1

    if not dry_run:
        jsonl_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    return scored


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Deterministic Evaluator — score benchmark runs.")
    parser.add_argument("--file", "-f", default=None,
                        help="Score a specific JSONL file stem (e.g. 'sunny_direct'). Omit for all.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview which runs would be scored without writing.")
    args = parser.parse_args()

    raw_dir = Path("LOGS/raw")
    if not raw_dir.exists():
        print("No LOGS/raw directory found. Run the benchmark first.")
        return

    targets = [raw_dir / f"{args.file}.jsonl"] if args.file else sorted(raw_dir.glob("*.jsonl"))

    if not targets:
        print("No JSONL files found.")
        return

    total = 0
    for path in targets:
        if not path.exists():
            print(f"File not found: {path}")
            continue
        print(f"\n[{path.name}]")
        n = score_file(path, dry_run=args.dry_run)
        total += n
        print(f"  → {n} run(s) scored.")

    print(f"\nDone. Total runs scored: {total}")


if __name__ == "__main__":
    main()
