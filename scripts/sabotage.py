#!/usr/bin/env python3
"""Break the calculator on purpose and require the checks to notice.

A verify that passes on a broken implementation is the default failure mode, so the
only way to know the checks are worth anything is to break the code and watch them
go red. Each attack is scored under the three-gate rule:

  gate 1  APPLIES            the patch changed the file. A patch that silently
                             matched nothing is a no-op with a confident write-up
                             attached, and it will make you weaken a check that was
                             already correct.
  gate 2  CHANGES THE OUTPUT  the measured fingerprint moved. If it did not, the
                             attack did not reach any code path the measurement
                             exercises, and gate 3 would be meaningless.
  gate 3  IS CAUGHT           the checks exit nonzero.

Guard sabotages invert gate 2. Code that is dormant when the input is valid, such as
an argument validator, cannot change the output when you disable it. For those the
requirement is stricter and opposite: the fingerprint must be UNCHANGED and the unit
suite must still fail. A guard sabotage that does change the output was never a
guard, and is reported as misclassified rather than counted.

THE NULL CONTROL RUNS FIRST. An unmodified copy of the tree is fingerprinted and must
match the baseline exactly. If it does not, the measurement is a function of where
the code lives rather than of the code, gate 2 would pass for free for every attack,
and the whole run is void. That is not hypothetical: it invalidated eleven sabotages
in this fleet on 2026-08-06. Nothing measured here contains an absolute path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Designs the fingerprint is taken over. Chosen to exercise every switch an attack
# below could flip: clustering, unequal sizes, one sided, few clusters, ICC of zero.
FINGERPRINT_DESIGNS = [
    ["--effect", "0.2", "--cluster-size", "30", "--icc", "0.05"],
    ["--effect", "0.2", "--cluster-size", "30", "--icc", "0.05", "--cv", "0.65"],
    ["--effect", "0.5", "--cluster-size", "12", "--icc", "0.1", "--sides", "1"],
    ["--effect", "0.35", "--cluster-size", "20", "--icc", "0.0"],
    ["--effect", "0.8", "--cluster-size", "15", "--icc", "0.1", "--df-rule", "normal"],
    ["--effect-kind", "proportion_difference", "--p1", "0.55", "--p2", "0.45",
     "--cluster-size", "40", "--icc", "0.02", "--cv", "0.4"],
]

# A slice of the JavaScript engine, so an attack on the port alone still moves the
# fingerprint. Printed as bare numbers: no paths, nothing directory dependent.
JS_PROBE = """
const e = await import("./src/power.js");
const out = [
  e.designEffect(30, 0.05, 0),
  e.designEffect(30, 0.05, 0.65),
  e.powerCrt(0.2, 30, 0.05, 34, 0),
  e.powerCrt(0.5, 12, 0.1, 8, 0, 0.05, 1),
  e.clustersCrt({ effect: 0.2, m: 30, icc: 0.05 }).clusters_per_arm,
];
console.log(out.map((x) => Number(x).toPrecision(15)).join(","));
"""

DETECTORS = [
    ("unit tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
    ("reference table", [sys.executable, "scripts/check_reference.py"]),
    ("python/javascript parity", None),  # needs a temp file, built in run_detectors
]


def run(cmd, cwd, timeout=900):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def tracked_files() -> list:
    proc = run(["git", "ls-files"], ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"git ls-files failed: {proc.stderr}")
    return [line for line in proc.stdout.splitlines() if line]


def copy_tree(dest: str) -> None:
    for name in tracked_files():
        source = os.path.join(ROOT, name)
        if not os.path.isfile(source):
            continue
        target = os.path.join(dest, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)


def fingerprint(tree: str) -> tuple:
    """Hash what the calculator says, with no reference to where it lives.

    Every command is run with cwd set to the copied tree and uses relative paths, and
    the JSON that comes back holds only numbers and setting names. So two identical
    trees in different directories must hash identically, which is what the null
    control checks.
    """
    parts = []
    for design in FINGERPRINT_DESIGNS:
        proc = run([sys.executable, "src/cli.py"] + design, tree)
        if proc.returncode != 0:
            parts.append(f"ERROR {proc.returncode}: {proc.stderr.strip().splitlines()[-1:]}")
            continue
        payload = json.loads(proc.stdout)
        payload.pop("notes", None)  # prose, and it quotes the numbers already
        parts.append(json.dumps(payload, sort_keys=True))
    proc = run(["node", "--input-type=module", "-e", JS_PROBE], tree)
    parts.append(proc.stdout.strip() if proc.returncode == 0 else f"JS ERROR {proc.returncode}")
    blob = "\n".join(parts)
    if tree in blob or ROOT in blob:
        raise SystemExit(
            "the fingerprint contains its own working directory, so it measures where "
            "the code lives rather than what it does. Gate 2 would pass for free."
        )
    return hashlib.sha256(blob.encode()).hexdigest()[:16], blob


def run_detectors(tree: str) -> list:
    """Run the checks that ought to catch a sabotage. Returns the ones that failed."""
    caught = []
    with tempfile.TemporaryDirectory() as tmp:
        cases = os.path.join(tmp, "cases.json")
        for name, cmd in DETECTORS:
            if cmd is None:
                dump = run([sys.executable, "scripts/parity_dump.py", cases], tree)
                if dump.returncode != 0:
                    caught.append(name)
                    continue
                proc = run(["node", "scripts/parity_check.mjs", cases], tree)
            else:
                proc = run(cmd, tree)
            if proc.returncode != 0:
                caught.append(name)
    return caught


# --------------------------------------------------------------------------
# the attacks
# --------------------------------------------------------------------------

# (name, kind, file, find, replace, description)
# kind is "attack" for code that is active on correct input, "guard" for code that is
# dormant until the input is wrong.
SABOTAGES = [
    ("design effect off by one", "attack", "src/power.py",
     "return 1.0 + ((1.0 + cv * cv) * m - 1.0) * icc",
     "return 1.0 + ((1.0 + cv * cv) * m) * icc",
     "the classic slip: 1 + m*rho instead of 1 + (m-1)*rho"),

    ("design effect dropped entirely", "attack", "src/power.py",
     "    return 1.0 + ((1.0 + cv * cv) * m - 1.0) * icc",
     "    return 1.0",
     "what a calculator that ignores clustering computes"),

    ("CV inflation ignored", "attack", "src/power.py",
     "return 1.0 + ((1.0 + cv * cv) * m - 1.0) * icc",
     "return 1.0 + (m - 1.0) * icc",
     "unequal cluster sizes silently treated as equal"),

    ("CV shorthand instead of the exact factor", "attack", "src/power.py",
     "    return 1.0 + ((1.0 + cv * cv) * m - 1.0) * icc",
     "    return (1.0 + (m - 1.0) * icc) * (1.0 + cv * cv)",
     "the (1 + CV^2) approximation used as if it were exact"),

    ("one sided switch has no effect", "attack", "src/power.py",
     "    return alpha / sides",
     "    return alpha / 2.0",
     "sides is accepted, validated, and then ignored"),

    ("t correction removed from the cluster path", "attack", "src/power.py",
     '    df = 2.0 * k_per_arm - 2.0 if df_rule == "cluster_t" else 2.0 * k_per_arm * m - 2.0',
     '    df = 2.0 * k_per_arm * m - 2.0',
     "degrees of freedom counted in people rather than clusters"),

    ("t correction weakened by two degrees of freedom", "attack", "src/power.py",
     '    df = 2.0 * k_per_arm - 2.0 if df_rule == "cluster_t" else 2.0 * k_per_arm * m - 2.0',
     '    df = 2.0 * k_per_arm if df_rule == "cluster_t" else 2.0 * k_per_arm * m - 2.0',
     "2k instead of 2k-2, a plausible off by one in the df"),

    ("noncentrality loses the two arm factor", "attack", "src/power.py",
     "    ncp = abs(effect) * math.sqrt(n_eff / 2.0)",
     "    ncp = abs(effect) * math.sqrt(n_eff)",
     "the sqrt(n/2) of a two sample comparison written as sqrt(n)"),

    ("effective sample size not divided by the design effect", "attack", "src/power.py",
     "    return k_per_arm * m / design_effect(m, icc, cv, deff_model)",
     "    return k_per_arm * m",
     "the design effect is computed and reported, then not used"),

    ("required clusters allowed to fall short", "attack", "src/power.py",
     "    while k <= max_clusters_per_arm and power_at(k) < power:",
     "    while k <= max_clusters_per_arm and power_at(k) < power * 0.97:",
     "accepting 97 percent of the target power, which looks like rounding"),

    ("Cohen's h drops the square root", "attack", "src/power.py",
     "    return 2.0 * math.asin(math.sqrt(p1)) - 2.0 * math.asin(math.sqrt(p2))",
     "    return 2.0 * math.asin(p1) - 2.0 * math.asin(p2)",
     "the arcsine transform applied to the proportion rather than its root"),

    ("proportion SMD standardised by the wrong variance", "attack", "src/power.py",
     "    pbar = 0.5 * (p1 + p2)",
     "    pbar = p1",
     "using the treated proportion instead of the average"),

    ("javascript port drifts from the engine", "attack", "src/power.js",
     "  return 1 + ((1 + cv * cv) * m - 1) * icc;",
     "  return 1 + (m - 1) * icc;",
     "the page loses the CV inflation while the python engine keeps it"),

    ("noncentral t series never hands off to the quadrature", "attack", "src/distributions.py",
     "    if method == \"auto\" and abs(ncp) > 12.0:",
     "    if method == \"auto\" and abs(ncp) > 1e9:",
     "AS 243 pushed into the range where it loses its digits"),

    ("ICC range check removed", "guard", "src/power.py",
     "    if not (0.0 <= icc <= 1.0):",
     "    if False:",
     "an ICC of 2 or -1 would be accepted and produce a confident wrong answer"),

    ("effect size validation removed", "guard", "src/power.py",
     "    if effect == 0.0:",
     "    if False:",
     "a zero effect would run the solver to its bracket limit instead of failing"),
]


def apply_patch(tree: str, relative: str, find: str, replace: str) -> int:
    path = os.path.join(tree, relative)
    with open(path) as fh:
        before = fh.read()
    count = before.count(find)
    if count == 0:
        return 0
    with open(path, "w") as fh:
        fh.write(before.replace(find, replace))
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default=None, help="substring of a sabotage name")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as workspace:
        baseline_tree = os.path.join(workspace, "baseline")
        os.makedirs(baseline_tree)
        copy_tree(baseline_tree)
        baseline, baseline_blob = fingerprint(baseline_tree)
        print(f"baseline fingerprint {baseline}")

        null_tree = os.path.join(workspace, "null-control")
        os.makedirs(null_tree)
        copy_tree(null_tree)
        null, null_blob = fingerprint(null_tree)
        print(f"null control fingerprint {null}")
        if null != baseline:
            print()
            print("NULL CONTROL FAILED. An unmodified copy of the tree fingerprints "
                  "differently from the baseline, so the measurement depends on where "
                  "the code lives rather than on the code. Every sabotage below would "
                  "pass gate 2 for free and the run would prove nothing. Aborting.")
            for a, b in zip(baseline_blob.splitlines(), null_blob.splitlines()):
                if a != b:
                    print(f"  baseline: {a[:120]}")
                    print(f"  null    : {b[:120]}")
            return 1
        print("null control passed: an unchanged copy fingerprints identically, so a "
              "changed fingerprint below can only come from the sabotage")

        baseline_failures = run_detectors(baseline_tree)
        if baseline_failures:
            print(f"the unmodified tree already fails {baseline_failures}. Fix that "
                  "first; a sabotage run against a red baseline means nothing.")
            return 1
        print("baseline detectors all pass")
        print()

        results = []
        for name, kind, relative, find, replace, description in SABOTAGES:
            if args.only and args.only not in name:
                continue
            tree = os.path.join(workspace, "s-" + str(len(results)))
            os.makedirs(tree)
            copy_tree(tree)
            applied = apply_patch(tree, relative, find, replace)
            gate1 = applied > 0
            if not gate1:
                results.append({
                    "name": name, "kind": kind, "verdict": "NO-OP",
                    "note": f"the patch text was not found in {relative}, so this "
                            "attack never applied",
                })
                print(f"[{'NO-OP':^9}] {name}")
                print(f"            the patch text was not found in {relative}")
                continue

            current, _ = fingerprint(tree)
            changed = current != baseline
            caught = run_detectors(tree)
            gate3 = len(caught) > 0

            if kind == "guard":
                # Inverted gate 2: dormant code cannot move the output.
                if changed:
                    verdict, note = ("MISCLASS", "this changed the output, so it was "
                                     "never a guard; rerun it as a plain attack")
                elif gate3:
                    verdict, note = ("PROVEN", "output unchanged as a guard should be, "
                                     "and " + ", ".join(caught) + " still fail")
                else:
                    verdict, note = ("MISSED", "nothing failed, so this guard is not "
                                     "actually tested by anything")
            else:
                if not changed:
                    verdict, note = ("NO-OP", "the output did not move, so the attack "
                                     "never reached the measured code path")
                elif gate3:
                    verdict, note = ("PROVEN", "caught by " + ", ".join(caught))
                else:
                    verdict, note = ("MISSED", "THE OUTPUT CHANGED AND NOTHING FAILED, "
                                     "which is a hole in the checks")

            results.append({"name": name, "kind": kind, "verdict": verdict, "note": note})
            print(f"[{verdict:^9}] {name}  ({kind}, {applied} site{'s' if applied > 1 else ''} "
                  f"in {relative})")
            print(f"            {description}")
            print(f"            fingerprint {'moved' if changed else 'unchanged'}; {note}")

    print()
    counts = {}
    for result in results:
        counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1
    print(f"{len(results)} sabotages: "
          + ", ".join(f"{count} {verdict.lower()}" for verdict, count in sorted(counts.items())))

    # Only PROVEN counts. A missed sabotage is a gap in the checks, a no-op is a
    # sabotage that never happened, and a misclassified guard was mislabelled. All
    # three make the score a fiction, so all three fail the run.
    unproven = [r for r in results if r["verdict"] != "PROVEN"]
    if unproven:
        print(f"SABOTAGE RUN FAILED: {len(unproven)} of {len(results)} not proven")
        for result in unproven:
            print(f"  - [{result['verdict']}] {result['name']}: {result['note']}")
        return 1
    print(f"sabotage run PASSED: all {len(results)} applied, moved the measured output "
          "in the direction their kind requires, and were caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
