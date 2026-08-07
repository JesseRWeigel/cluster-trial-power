#!/usr/bin/env python3
"""Compute, with the Python engine, what the page in the browser must show.

Written to a path given on the command line so a verify run leaves no new files in
the tree. Keeping the expected values here rather than inside browser_check.mjs is
what makes the browser stage a cross-language agreement test instead of a check that
the page agrees with itself.
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import power as P  # noqa: E402

# These are the page's own default input values. If the page defaults change, this
# must change with them, and the browser check fails loudly rather than quietly
# comparing the wrong design.
DEFAULTS = {"effect": 0.2, "m": 30.0, "icc": 0.05, "cv": 0.0, "power": 0.8,
            "alpha": 0.05, "sides": 2, "df_rule": "cluster_t"}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: browser_expectations.py <output.json>", file=sys.stderr)
        return 2
    base = P.clusters_crt(
        DEFAULTS["effect"], DEFAULTS["m"], DEFAULTS["icc"], DEFAULTS["cv"],
        DEFAULTS["power"], DEFAULTS["alpha"], DEFAULTS["sides"], DEFAULTS["df_rule"])
    cv_case = P.clusters_crt(
        DEFAULTS["effect"], DEFAULTS["m"], DEFAULTS["icc"], 0.65,
        DEFAULTS["power"], DEFAULTS["alpha"], DEFAULTS["sides"], DEFAULTS["df_rule"])
    icc_zero = P.clusters_crt(
        DEFAULTS["effect"], DEFAULTS["m"], 0.0, DEFAULTS["cv"],
        DEFAULTS["power"], DEFAULTS["alpha"], DEFAULTS["sides"], DEFAULTS["df_rule"])

    with open(os.path.join(ROOT, "reference", "reference_values.json")) as fh:
        reference_rows = len(json.load(fh)["values"])

    payload = {
        "defaults": DEFAULTS,
        "clusters_per_arm": base.clusters_per_arm,
        "clusters_total": base.clusters_total,
        "individuals_total": base.individuals_total,
        "achieved_power": base.achieved_power,
        "design_effect": base.design_effect,
        "degrees_of_freedom": int(base.degrees_of_freedom),
        "n_individually_randomised_total": base.n_individually_randomised_total,
        "alpha": DEFAULTS["alpha"],
        "cv065_design_effect": cv_case.design_effect,
        "cv065_clusters_per_arm": cv_case.clusters_per_arm,
        "icc_zero_clusters_per_arm": icc_zero.clusters_per_arm,
        "icc_zero_individuals_total": icc_zero.individuals_total,
        "proportion_smd": P.proportion_smd(0.55, 0.45),
        "n_individual_per_arm_ceil": math.ceil(base.n_individually_randomised_per_arm),
        "reference_rows": reference_rows,
    }
    with open(sys.argv[1], "w") as fh:
        json.dump(payload, fh, indent=1)
    # The file name is a temporary path and is deliberately not printed: this output
    # gets pasted into the README, where an absolute path is both noise and a leak.
    print(f"browser expectations from the python engine: "
          f"{payload['clusters_per_arm']} clusters per arm, "
          f"design effect {payload['design_effect']}, "
          f"{payload['reference_rows']} reference rows to render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
