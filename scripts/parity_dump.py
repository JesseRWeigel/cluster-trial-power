#!/usr/bin/env python3
"""Dump a grid of Python engine results for the JavaScript port to reproduce.

Written to a path given on the command line, never into the repository, because a
verify run must not modify the tree it verifies.
"""

from __future__ import annotations

import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import distributions as dist  # noqa: E402
import power as P  # noqa: E402


def cases() -> list:
    out = []

    for p in (0.001, 0.025, 0.05, 0.5, 0.9, 0.95, 0.975, 0.99, 0.999):
        out.append({"fn": "normPpf", "args": [p], "expected": dist.norm_ppf(p)})
    for x in (-4.0, -1.96, -0.5, 0.0, 0.5, 1.96, 4.0, 8.0):
        out.append({"fn": "normCdf", "args": [x], "expected": dist.norm_cdf(x)})

    for df in (1, 2, 4, 10, 46, 200, 5000):
        for p in (0.9, 0.95, 0.975, 0.99):
            out.append({"fn": "tPpf", "args": [p, df], "expected": dist.t_ppf(p, df)})
        for t in (-3.0, -0.7, 0.0, 0.7, 2.0, 6.0):
            out.append({"fn": "tCdf", "args": [t, df], "expected": dist.t_cdf(t, df)})

    for df, ncp, t in itertools.product((3, 10, 46, 200, 1000), (0.0, 1.0, 2.9, 6.0, 11.0),
                                        (-2.0, 0.0, 1.96, 2.5, 5.0)):
        out.append({"fn": "nctCdf", "args": [t, df, ncp],
                    "expected": dist.nct_cdf(t, df, ncp)})

    for m, icc, cv in itertools.product((1, 10, 30, 250), (0.0, 0.01, 0.05, 0.3),
                                        (0.0, 0.4, 1.2)):
        out.append({"fn": "designEffect", "args": [m, icc, cv],
                    "expected": P.design_effect(m, icc, cv)})

    for p1, p2 in ((0.75, 0.5), (0.6, 0.4), (0.1, 0.05)):
        out.append({"fn": "cohenH", "args": [p1, p2], "expected": P.cohen_h(p1, p2)})
        out.append({"fn": "proportionSmd", "args": [p1, p2],
                    "expected": P.proportion_smd(p1, p2)})

    for d, n, sides, method in itertools.product((0.2, 0.5, 0.9), (8, 30, 64, 400),
                                                 (1, 2), ("t", "normal")):
        out.append({"fn": "powerTwoSample", "args": [d, n, 0.05, sides, method],
                    "expected": P.power_two_sample(d, n, 0.05, sides, method)})

    for d, power, sides, method in itertools.product((0.2, 0.5, 0.8), (0.8, 0.9),
                                                     (1, 2), ("t", "normal")):
        out.append({"fn": "nTwoSample", "args": [d, power, 0.05, sides, method],
                    "expected": P.n_two_sample(d, power, 0.05, sides, method)})

    for d, m, icc, k, cv, rule in itertools.product(
        (0.2, 0.35, 0.6), (5, 25, 60), (0.0, 0.02, 0.1), (3, 12, 40), (0.0, 0.7),
        ("cluster_t", "normal", "individual_t"),
    ):
        out.append({"fn": "powerCrt", "args": [d, m, icc, k, cv, 0.05, 2, rule],
                    "expected": P.power_crt(d, m, icc, k, cv, 0.05, 2, rule)})

    for d, m, icc, cv, rule in itertools.product(
        (0.2, 0.4), (10, 40), (0.0, 0.03, 0.15), (0.0, 0.6), ("cluster_t", "normal"),
    ):
        res = P.clusters_crt(d, m, icc, cv, 0.8, 0.05, 2, rule)
        out.append({"fn": "clustersCrtField",
                    "args": ["clusters_per_arm", d, m, icc, cv, 0.8, 0.05, 2, rule],
                    "expected": float(res.clusters_per_arm)})
        out.append({"fn": "clustersCrtField",
                    "args": ["achieved_power", d, m, icc, cv, 0.8, 0.05, 2, rule],
                    "expected": float(res.achieved_power)})
        out.append({"fn": "clustersCrtField",
                    "args": ["individuals_total", d, m, icc, cv, 0.8, 0.05, 2, rule],
                    "expected": float(res.individuals_total)})

    curve = P.power_curve_clusters(0.3, 25, 0.04, 0.5, k_min=2, k_max=30)
    for point in curve:
        out.append({"fn": "powerCurvePoint", "args": [0.3, 25, 0.04, 0.5, point["k_per_arm"]],
                    "expected": point["power"]})

    oc = P.operating_characteristic(20, 25, 0.05, 0.0, points=21)
    for point in oc:
        out.append({"fn": "ocPoint", "args": [20, 25, 0.05, 0.0, point["effect"]],
                    "expected": point["power"]})

    return out


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: parity_dump.py <output.json>", file=sys.stderr)
        return 2
    payload = {"generated_by": "scripts/parity_dump.py", "cases": cases()}
    with open(sys.argv[1], "w") as fh:
        json.dump(payload, fh, indent=1)
    print(f"wrote {len(payload['cases'])} parity cases to {sys.argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
