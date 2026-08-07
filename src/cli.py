#!/usr/bin/env python3
"""Command line front end. Prints JSON so other tools can consume it.

  python3 src/cli.py --effect 0.2 --cluster-size 30 --icc 0.05
  python3 src/cli.py --effect-kind proportion_difference --p1 0.55 --p2 0.45 --icc 0.02 \
      --cluster-size 40 --cv 0.6 --sides 1
  python3 src/cli.py --effect 0.3 --cluster-size 25 --icc 0.05 --curves
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import power as P  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Cluster randomised trial sample size")
    p.add_argument("--effect", type=float, default=None,
                   help="standardised effect size, required unless --p1 and --p2 are given")
    p.add_argument("--effect-kind", default="d", choices=list(P.EFFECT_KINDS),
                   help="d or smd for a standardised mean difference, cohen_h for the "
                        "arcsine transform of two proportions, proportion_difference for "
                        "the difference over the pooled standard deviation")
    p.add_argument("--p1", type=float, default=None)
    p.add_argument("--p2", type=float, default=None)
    p.add_argument("--cluster-size", type=float, required=True, dest="m",
                   help="average number of individuals per cluster")
    p.add_argument("--icc", type=float, required=True, help="intracluster correlation")
    p.add_argument("--cv", type=float, default=0.0,
                   help="coefficient of variation of cluster size, 0 for equal clusters")
    p.add_argument("--power", type=float, default=0.80)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--sides", type=int, default=2, choices=(1, 2))
    p.add_argument("--df-rule", default="cluster_t", choices=list(P.DF_RULES))
    p.add_argument("--deff-model", default="eldridge", choices=list(P.DEFF_MODELS))
    p.add_argument("--curves", action="store_true",
                   help="include the power curve and the operating characteristic")
    p.add_argument("--k-max", type=int, default=60)
    return p


def resolve_effect(args) -> float:
    if args.effect_kind in ("cohen_h", "proportion_difference"):
        if args.p1 is None or args.p2 is None:
            raise SystemExit(f"--effect-kind {args.effect_kind} needs --p1 and --p2")
        return P.standardised_effect(args.effect_kind, p1=args.p1, p2=args.p2)
    if args.effect is None:
        raise SystemExit("--effect is required for a standardised mean difference")
    return P.standardised_effect(args.effect_kind, value=args.effect)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    effect = resolve_effect(args)
    result = P.clusters_crt(
        effect=effect, m=args.m, icc=args.icc, cv=args.cv, power=args.power,
        alpha=args.alpha, sides=args.sides, df_rule=args.df_rule,
        deff_model=args.deff_model, effect_kind=args.effect_kind,
    )
    payload = result.to_dict()
    if args.p1 is not None and args.p2 is not None:
        payload["p1"] = args.p1
        payload["p2"] = args.p2
        payload["cohen_h"] = P.cohen_h(args.p1, args.p2)
        payload["proportion_smd"] = P.proportion_smd(args.p1, args.p2)
    if args.curves:
        payload["power_curve"] = P.power_curve_clusters(
            effect, args.m, args.icc, args.cv, args.alpha, args.sides,
            args.df_rule, args.deff_model, 2, args.k_max)
        payload["operating_characteristic"] = P.operating_characteristic(
            result.clusters_per_arm, args.m, args.icc, args.cv, args.alpha,
            args.sides, args.df_rule, args.deff_model,
            0.0, max(1.0, 2.0 * abs(effect)), 101)
    json.dump(payload, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
