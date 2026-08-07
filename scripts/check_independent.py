#!/usr/bin/env python3
"""Recompute power by simulating the trial, sharing no algebra with the calculator.

The closed form says power is a tail probability of a noncentral t whose
noncentrality carries the design effect. Checking that against another closed form
would only confirm that two derivations of the same algebra agree. So this script
does not evaluate any formula from the package. It builds synthetic trials one
individual at a time, analyses each one, and counts how often the analysis rejects
the null. That count is the power, by definition, and it goes wrong for entirely
different reasons than the algebra would.

Independence is structural, and enforced rather than promised:

  * Nothing from src/ is imported. `assert_no_package_imports` walks this file's own
    syntax tree with the `ast` module and fails if any import names the package. A
    grep would be satisfied by a comment and would miss importlib.
  * The number this is compared against is obtained by running src/cli.py as a
    SUBPROCESS and reading its JSON, so the calculator's code never enters this
    process.
  * The critical values come from a printed t table rather than from any code here
    or there. Three decimals is enough: the power changes by about 5e-5 across half
    a unit in the last printed place, which is fifty times smaller than the Monte
    Carlo error at the sample sizes used.

The simulated model, stated so the comparison is interpretable. Individual j in
cluster i of arm a has outcome mu_a + b_i + e_ij with b_i ~ N(0, rho) and
e_ij ~ N(0, 1 - rho), so the total variance is 1 and the intracluster correlation is
rho by construction. The treatment effect mu_1 - mu_0 is the standardised effect d.

Two analyses, matching the two models the calculator offers:

  cluster_t  the standard cluster level analysis. Reduce each cluster to its mean,
             run a two sample t test on the 2k cluster means, reject when |t|
             exceeds the tabled critical value on 2k - 2 degrees of freedom. With
             equal clusters this is exactly what the calculator's cluster_t rule
             models, so agreement should be within Monte Carlo error.
  normal     the size weighted arm mean compared using the true variance, a z test.
             This is what the normal rule models, and it is the one that can be run
             with unequal cluster sizes without the analysis itself becoming an
             approximation.

Every result is reported with its Monte Carlo standard error, and the discrepancy is
reported in units of that error. A run passes when every scenario is within 4
standard errors, which for the eight scenarios here is a false alarm rate of about
0.02 percent if the calculator is right.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLI = os.path.join(ROOT, "src", "cli.py")

# Two sided 0.975 and one sided 0.95 critical values of Student's t, from the table
# reproduced in Fisher and Yates (1963) Table III and in every textbook appendix.
# Keyed by degrees of freedom. A degrees of freedom value that is not in this table
# is a failure rather than an interpolation.
T_TABLE_0975 = {
    10: 2.228, 14: 2.145, 18: 2.101, 22: 2.074, 26: 2.056, 30: 2.042,
    38: 2.024, 46: 2.013, 58: 2.002, 78: 1.991, 118: 1.980, 126: 1.979,
}
T_TABLE_0950 = {
    10: 1.812, 14: 1.761, 18: 1.734, 22: 1.717, 26: 1.706, 30: 1.697,
    38: 1.686, 46: 1.679, 58: 1.672, 78: 1.665, 118: 1.658, 126: 1.657,
}


def assert_no_package_imports(path: str) -> list:
    """Walk this file's syntax tree and prove it imports nothing from the package.

    Returns the list of modules imported, so the verify log records what it saw
    rather than only that the check passed.
    """
    with open(path) as fh:
        tree = ast.parse(fh.read(), filename=path)
    banned = {"power", "distributions", "src", "cli", "check_reference"}
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imported.append(base)
            imported.extend(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name in ("import_module", "__import__", "exec", "eval"):
                raise SystemExit(
                    f"{path} calls {name}, which can import the package under test "
                    "without appearing in the syntax tree as an import. Remove it."
                )
    for module in imported:
        head = module.split(".")[0]
        if head in banned:
            raise SystemExit(
                f"{path} imports {module!r}, which is the package under test. An "
                "independent check that calls the code it is checking is not "
                "independent."
            )
    return sorted(set(m for m in imported if m))


# --------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------


def cluster_sizes(k: int, m: float, cv: float, rng: random.Random) -> list:
    """k cluster sizes averaging m with coefficient of variation cv.

    Sizes are drawn from a gamma shaped distribution and rounded, then the realised
    mean and CV are returned to the caller so the comparison uses what was actually
    simulated rather than what was requested.
    """
    if cv == 0.0:
        return [int(round(m))] * k
    shape = 1.0 / (cv * cv)
    scale = m / shape
    sizes = []
    for _ in range(k):
        size = int(round(rng.gammavariate(shape, scale)))
        sizes.append(max(2, size))
    return sizes


def simulate_trial_cluster_means(k: int, sizes_a: list, sizes_b: list, effect: float,
                                 icc: float, rng: random.Random) -> tuple:
    """One trial. Returns the per-cluster means for each arm, and the sizes."""
    sd_between = math.sqrt(icc)
    sd_within = math.sqrt(1.0 - icc)
    means_a, means_b = [], []
    for sizes, means, mu in ((sizes_a, means_a, 0.0), (sizes_b, means_b, effect)):
        for size in sizes:
            b = rng.gauss(0.0, sd_between) if sd_between > 0 else 0.0
            total = 0.0
            for _ in range(size):
                total += mu + b + (rng.gauss(0.0, sd_within) if sd_within > 0 else 0.0)
            means.append(total / size)
    return means_a, means_b


def two_sample_t(a: list, b: list) -> float:
    """Pooled variance two sample t statistic, written out rather than imported."""
    na, nb = len(a), len(b)
    mean_a = sum(a) / na
    mean_b = sum(b) / nb
    ss = sum((x - mean_a) ** 2 for x in a) + sum((x - mean_b) ** 2 for x in b)
    pooled = ss / (na + nb - 2)
    if pooled <= 0.0:
        return 0.0
    return (mean_b - mean_a) / math.sqrt(pooled * (1.0 / na + 1.0 / nb))


def weighted_arm_mean(means: list, sizes: list) -> float:
    total = sum(sizes)
    return sum(mu * size for mu, size in zip(means, sizes)) / total


def true_variance_of_weighted_mean(sizes: list, icc: float) -> float:
    """Variance of the size weighted arm mean, from the simulated model directly.

    This is a property of the data generating process, not of the calculator. With
    y_ij = mu + b_i + e_ij, the weighted mean is sum(m_i ybar_i) / M, whose variance
    is (rho sum m_i^2 + (1 - rho) sum m_i) / M^2. Two lines of covariance algebra on
    the simulation's own definition, which is why it is allowed here.
    """
    total = float(sum(sizes))
    sum_sq = float(sum(size * size for size in sizes))
    return (icc * sum_sq + (1.0 - icc) * total) / (total * total)


def run_scenario(name: str, effect: float, m: float, icc: float, k: int, cv: float,
                 analysis: str, sides: int, alpha: float, replications: int,
                 seed: int) -> dict:
    if alpha != 0.05:
        raise SystemExit("the tabled critical values here cover alpha = 0.05 only")
    rng = random.Random(seed)
    df = 2 * k - 2
    table = T_TABLE_0975 if sides == 2 else T_TABLE_0950
    if analysis == "cluster_t":
        if df not in table:
            raise SystemExit(
                f"scenario {name} needs the t critical value at {df} degrees of freedom, "
                f"which is not in the tabled values {sorted(table)}. Add it from a "
                "printed table rather than computing it here."
            )
        crit = table[df]
    else:
        crit = 1.959964 if sides == 2 else 1.644854  # standard normal, tabled

    rejections = 0
    size_n, size_sum, size_sumsq = 0, 0.0, 0.0
    for rep in range(replications):
        sizes_a = cluster_sizes(k, m, cv, rng)
        sizes_b = cluster_sizes(k, m, cv, rng)
        for size in sizes_a + sizes_b:
            size_n += 1
            size_sum += size
            size_sumsq += size * size
        means_a, means_b = simulate_trial_cluster_means(k, sizes_a, sizes_b, effect, icc, rng)
        if analysis == "cluster_t":
            stat = two_sample_t(means_a, means_b)
        else:
            diff = weighted_arm_mean(means_b, sizes_b) - weighted_arm_mean(means_a, sizes_a)
            var = (true_variance_of_weighted_mean(sizes_a, icc)
                   + true_variance_of_weighted_mean(sizes_b, icc))
            stat = diff / math.sqrt(var)
        if sides == 2:
            if abs(stat) > crit:
                rejections += 1
        elif stat > crit:
            rejections += 1

    p = rejections / replications
    se = math.sqrt(max(p * (1.0 - p), 1e-12) / replications)
    realised_mean = size_sum / size_n
    variance = max(size_sumsq / size_n - realised_mean ** 2, 0.0)
    return {
        "name": name, "effect": effect, "m": m, "icc": icc, "k": k, "cv": cv,
        "analysis": analysis, "sides": sides, "replications": replications,
        "critical_value": crit, "simulated_power": p, "monte_carlo_se": se,
        "realised_mean_size": realised_mean,
        "realised_cv": math.sqrt(variance) / realised_mean,
    }


# --------------------------------------------------------------------------
# the calculator, as a subprocess
# --------------------------------------------------------------------------


def calculator_power(effect: float, m: float, icc: float, k: int, cv: float,
                     df_rule: str, sides: int) -> float:
    """Ask src/cli.py for the power of exactly this design, without importing it.

    The CLI solves for k rather than reporting power at a given k, so the design is
    pinned by asking for the power curve and reading the point at this k. Anything
    missing is an error, never a silently skipped comparison.
    """
    cmd = [
        sys.executable, CLI, "--effect", repr(effect), "--cluster-size", repr(m),
        "--icc", repr(icc), "--cv", repr(cv), "--sides", str(sides),
        "--df-rule", df_rule, "--curves", "--k-max", str(max(k, 2)),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"calculator subprocess failed: {' '.join(cmd)}\n{proc.stderr}")
    payload = json.loads(proc.stdout)
    for point in payload["power_curve"]:
        if point["k_per_arm"] == k:
            return float(point["power"])
    raise SystemExit(f"power curve from the calculator has no point at k = {k}")


SCENARIOS = [
    # name, effect, m, icc, k, cv, analysis, sides
    ("equal clusters, t analysis", 0.35, 20, 0.05, 12, 0.0, "cluster_t", 2),
    ("equal clusters, larger design", 0.25, 25, 0.05, 24, 0.0, "cluster_t", 2),
    ("few clusters, where the t correction bites", 0.8, 15, 0.10, 6, 0.0, "cluster_t", 2),
    ("one sided", 0.35, 20, 0.05, 12, 0.0, "cluster_t", 1),
    ("ICC zero, clustering irrelevant", 0.35, 20, 0.0, 12, 0.0, "cluster_t", 2),
    ("normal analysis, equal clusters", 0.3, 20, 0.05, 15, 0.0, "normal", 2),
    ("normal analysis, unequal clusters CV 0.6", 0.3, 20, 0.05, 15, 0.6, "normal", 2),
    ("null effect, must reject at alpha", 0.0, 20, 0.05, 12, 0.0, "cluster_t", 2),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replications", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=20260807)
    parser.add_argument("--sigma", type=float, default=4.0,
                        help="how many Monte Carlo standard errors of disagreement to allow")
    args = parser.parse_args()

    imported = assert_no_package_imports(os.path.abspath(__file__))
    print(f"import graph checked with ast: {', '.join(imported)}")
    # Relative, deliberately: this output gets pasted into the README, and an
    # absolute /home/<user>/... path there is both private and unportable.
    print("nothing from src/ is imported; the calculator is run as a subprocess "
          f"({os.path.relpath(CLI, ROOT)})")
    print()

    failures = []
    print(f"{'scenario':44s} {'simulated':>10s} {'+/- se':>9s} {'calculator':>11s} "
          f"{'diff':>10s} {'sigmas':>7s}  result")
    print("-" * 108)
    for i, (name, effect, m, icc, k, cv, analysis, sides) in enumerate(SCENARIOS):
        sim = run_scenario(name, effect, m, icc, k, cv, analysis, sides, 0.05,
                           args.replications, args.seed + 977 * i)
        if effect == 0.0:
            # The null case has no calculator call to make: a correct test rejects at
            # the nominal level whatever the design, and that is the claim being checked.
            expected = 0.05
            label = "alpha"
        else:
            df_rule = "cluster_t" if analysis == "cluster_t" else "normal"
            expected = calculator_power(effect, m, icc, k, cv, df_rule, sides)
            label = "calculator"
        diff = sim["simulated_power"] - expected
        sigmas = abs(diff) / sim["monte_carlo_se"]
        ok = sigmas <= args.sigma
        if not ok:
            failures.append(
                f"{name}: simulated {sim['simulated_power']:.4f} +/- {sim['monte_carlo_se']:.4f}, "
                f"{label} {expected:.4f}, {sigmas:.1f} standard errors apart"
            )
        print(f"{name:44s} {sim['simulated_power']:10.4f} {sim['monte_carlo_se']:9.4f} "
              f"{expected:11.4f} {diff:+10.4f} {sigmas:7.2f}  {'ok' if ok else 'FAIL'}")
        # The unequal size scenarios only mean anything if the sizes actually drawn
        # have the mean and CV the calculator was told about, so say what they were.
        drift = abs(sim["realised_cv"] - cv)
        note = ""
        if cv > 0 and drift > 0.05:
            note = "  <-- drifted from the requested CV, comparison is not clean"
            failures.append(
                f"{name}: simulated cluster sizes have CV {sim['realised_cv']:.3f}, "
                f"not the {cv} the calculator was given"
            )
        print(f"{'':44s} simulated cluster sizes: mean {sim['realised_mean_size']:.2f} "
              f"(asked {m}), CV {sim['realised_cv']:.3f} (asked {cv}){note}")

    print()
    print(f"{len(SCENARIOS)} scenarios, {args.replications} replications each, "
          f"seed {args.seed}, tolerance {args.sigma} Monte Carlo standard errors")
    print("Monte Carlo error is the honest limit here: at 20000 replications the "
          "standard error of a power near 0.8 is 0.0028, so this check can detect a "
          "systematic error of about 1 percent of power and no smaller.")
    if failures:
        print(f"INDEPENDENT CHECK FAILED: {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("independent check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
