#!/usr/bin/env python3
"""Compare the calculator against reference/reference_values.json, then prove the
tolerances are tight enough to reject a wrong answer.

Two halves, and the second is the one that earns the first its keep.

AGREEMENT: every row is evaluated and compared at a relative tolerance derived from
the precision of its source, never chosen by hand. A row whose function is unknown, or
whose evaluation raises, is a failure rather than a skip.

NEGATIVE CONTROLS: a tolerance wide enough to accept everything proves nothing. So for
each of the errors this calculator exists to prevent, the wrong value is computed with
the real code under wrong assumptions and compared against the same reference row at
the same tolerance. Every one of them must be REJECTED. A negative control that slips
through is reported as a failure of this script, not waved past.

Exit code is the result.
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import distributions as dist  # noqa: E402
import power as P  # noqa: E402

REFERENCE = os.path.join(ROOT, "reference", "reference_values.json")

DEFAULT_TOL = {
    "exact_arithmetic": 1e-12,
    "structural_identity": 0.0,
    "pinned_regression": 1e-12,
    "published_table": 1e-12,
    "published_package_output": 1e-12,
}


# --------------------------------------------------------------------------
# adapters, so the reference file can name a calculation rather than a call
# --------------------------------------------------------------------------


def n_two_sample_nearest(**kw) -> float:
    """Cohen's Table 2.4.1 rounds to nearest. The calculator itself reports the ceiling."""
    return float(round(P.n_two_sample(**kw)))


def deff_shorthand(m, icc, cv) -> float:
    return P.deff_shorthand_ratio(m, icc, cv)["deff_shorthand"]


def clusters_crt_field(field, **kw) -> float:
    return float(getattr(P.clusters_crt(**kw), field))


FUNCTIONS = {
    "norm_ppf": dist.norm_ppf,
    "norm_cdf": dist.norm_cdf,
    "t_ppf": dist.t_ppf,
    "t_cdf": dist.t_cdf,
    "nct_cdf": dist.nct_cdf,
    "design_effect": P.design_effect,
    "deff_shorthand": deff_shorthand,
    "cohen_h": P.cohen_h,
    "proportion_smd": P.proportion_smd,
    "n_two_sample": P.n_two_sample,
    "n_two_sample_nearest": n_two_sample_nearest,
    "power_two_sample": P.power_two_sample,
    "power_crt": P.power_crt,
    "clusters_crt_field": clusters_crt_field,
}


def tolerance_for(row: dict) -> float:
    """Relative tolerance, derived from the source's own precision wherever possible."""
    if "tol_rel" in row:
        return float(row["tol_rel"])
    expected = abs(float(row["expected"]))
    if "decimals" in row:
        # half a unit in the last printed decimal place, as a relative quantity
        half_ulp = 0.5 * 10.0 ** (-int(row["decimals"]))
        return half_ulp / expected if expected else 0.0
    if "sig_figs" in row:
        if expected == 0.0:
            return 0.0
        exponent = math.floor(math.log10(expected))
        half_ulp = 0.5 * 10.0 ** (exponent - (int(row["sig_figs"]) - 1))
        return half_ulp / expected
    return DEFAULT_TOL[row["provenance"]]


def evaluate(row: dict) -> float:
    fn = FUNCTIONS.get(row["fn"])
    if fn is None:
        raise KeyError(
            f"reference row {row['id']} names function {row['fn']!r}, which this script "
            f"does not know. Known: {sorted(FUNCTIONS)}"
        )
    return float(fn(**row["kwargs"]))


def relative_error(got: float, expected: float) -> float:
    if expected == 0.0:
        return abs(got)
    return abs(got - expected) / abs(expected)


def check_agreement(rows: list) -> tuple:
    failures = []
    print(f"{'id':44s} {'expected':>16s} {'computed':>18s} {'rel err':>10s} {'tol':>10s}  result")
    print("-" * 112)
    for row in rows:
        tol = tolerance_for(row)
        try:
            got = evaluate(row)
        except Exception as exc:  # a row that cannot be evaluated is a failure
            failures.append((row["id"], f"evaluation raised: {exc}"))
            print(f"{row['id']:44s} {'':>16s} {'RAISED':>18s} {'':>10s} {'':>10s}  FAIL {exc}")
            continue
        expected = float(row["expected"])
        rel = relative_error(got, expected)
        ok = (got == expected) if tol == 0.0 else (rel <= tol)
        if not ok:
            failures.append((row["id"], f"expected {expected!r}, got {got!r}, rel {rel:.3e} > tol {tol:.3e}"))
        print(f"{row['id']:44s} {expected:16.10g} {got:18.12g} {rel:10.2e} {tol:10.2e}  "
              f"{'ok' if ok else 'FAIL'}")
    return failures


# --------------------------------------------------------------------------
# negative controls
# --------------------------------------------------------------------------

# Each entry: the reference row it attacks, a description of the wrong assumption, and
# a callable producing the value that wrong assumption gives. Every one must be
# rejected by the same tolerance that accepted the correct value.
NEGATIVE_CONTROLS = [
    (
        "deff-m30-icc005",
        "design effect written as 1 + m*rho instead of 1 + (m-1)*rho",
        lambda: 1.0 + 30 * 0.05,
    ),
    (
        "deff-m30-icc005",
        "design effect omitted entirely",
        lambda: 1.0,
    ),
    (
        "deff-m30-icc005-cv065",
        "unequal cluster sizes ignored, Kish design effect used with a CV of 0.65",
        lambda: P.design_effect(30, 0.05, 0.65, model="kish"),
    ),
    (
        "deff-m30-icc005-cv065",
        "the (1 + CV^2) shorthand used in place of the exact Eldridge inflation",
        lambda: deff_shorthand(30, 0.05, 0.65),
    ),
    (
        "pwr-t-d020-p080",
        "normal approximation used where pwr uses the noncentral t",
        lambda: P.n_two_sample(0.2, 0.80, 0.05, 2, "normal"),
    ),
    (
        "pwr-t-d050-p080",
        "one sided test used where the reference is two sided",
        lambda: P.n_two_sample(0.5, 0.80, 0.05, 1, "t"),
    ),
    (
        "cohen-t241-d020-p080",
        "normal approximation, rounded the same way as the table",
        lambda: float(round(P.n_two_sample(0.2, 0.80, 0.05, 2, "normal"))),
    ),
    (
        "crt-hand-d025-m25-icc005-t",
        "degrees of freedom taken from individuals (2km - 2) rather than clusters (2k - 2)",
        lambda: clusters_crt_field(
            "clusters_per_arm", effect=0.25, m=25, icc=0.05, power=0.80,
            alpha=0.05, sides=2, df_rule="individual_t"),
    ),
    (
        "crt-hand-d025-m25-icc005-t",
        "design effect omitted, so clustering is ignored completely",
        lambda: clusters_crt_field(
            "clusters_per_arm", effect=0.25, m=25, icc=0.0, power=0.80,
            alpha=0.05, sides=2, df_rule="cluster_t"),
    ),
    (
        "crt-power-d025-m25-icc005-k24",
        "normal approximation instead of the t correction at 24 clusters per arm",
        lambda: P.power_crt(0.25, 25, 0.05, 24, df_rule="normal"),
    ),
    (
        "crt-power-d035-m40-icc002-cv06-k7",
        "CV inflation dropped, equal cluster sizes assumed",
        lambda: P.power_crt(0.35, 40, 0.02, 7, cv=0.0, df_rule="cluster_t"),
    ),
    (
        "t-0975-df46",
        "t quantile taken at the wrong degrees of freedom, 44 instead of 46",
        lambda: dist.t_ppf(0.975, 44),
    ),
    (
        "smd-060-040",
        "Cohen's arcsine h used where the standardised proportion difference was meant",
        lambda: P.cohen_h(0.6, 0.4),
    ),
]


def check_negative_controls(rows_by_id: dict) -> list:
    failures = []
    print()
    print("negative controls: each must be REJECTED by the tolerance that accepted the correct value")
    print("-" * 112)
    for row_id, description, wrong in NEGATIVE_CONTROLS:
        row = rows_by_id[row_id]
        tol = tolerance_for(row)
        expected = float(row["expected"])
        try:
            value = float(wrong())
        except Exception as exc:
            failures.append((row_id, f"negative control raised: {exc}"))
            print(f"  {row_id:38s} RAISED {exc}")
            continue
        rel = relative_error(value, expected)
        rejected = (value != expected) if tol == 0.0 else (rel > tol)
        margin = rel / tol if tol > 0 else float("inf")
        if not rejected:
            failures.append((
                row_id,
                f"negative control NOT rejected: {description}; wrong value {value!r} sits "
                f"within tol {tol:.3e} of {expected!r}. The tolerance is too wide, or the "
                f"attack does not change the answer."
            ))
        print(f"  {row_id:38s} {value:16.10g} rel {rel:9.2e} = {margin:9.1f}x tol  "
              f"{'rejected' if rejected else 'ACCEPTED (bad)'}")
        print(f"      {description}")
    return failures


def main() -> int:
    with open(REFERENCE) as fh:
        data = json.load(fh)
    rows = data["values"]
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        print("duplicate reference ids", file=sys.stderr)
        return 1

    failures = check_agreement(rows)
    failures += check_negative_controls({r["id"]: r for r in rows})

    print()
    print(f"reference rows: {len(rows)}   negative controls: {len(NEGATIVE_CONTROLS)}")
    if failures:
        print(f"FAILED: {len(failures)}")
        for fid, msg in failures:
            print(f"  - {fid}: {msg}")
        return 1
    print("reference check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
