#!/usr/bin/env python3
"""Check that the README says what actually happened.

Twelve verify scripts in this fleet pass without ever reading their README, which
means a project can report a wall of green while its README still says "TODO: replace
with a real description". So this stage reads it.

Three things:

1. NO SCAFFOLD MARKERS, ignoring fenced code blocks. The Status section holds the
   pasted transcript of the verify run, and that transcript contains the word TODO
   inside the phrase "no TODO left in it" and similar. A marker search that reads its
   own pasted output finds itself. Excluding the README from the check would disarm
   it exactly where it is tested, so instead the fenced blocks are stripped and the
   prose around them is searched.

2. THE STATUS SECTION EXISTS AND CARRIES REAL OUTPUT, specifically the verify
   script's own success line.

3. THE COUNTS ARE TRUE. A pasted "45 tests passed" goes stale the moment somebody
   adds a test. The README carries a table of counts, and each one is compared
   against what this run actually produced, read out of the logs the verify script
   just wrote. A count in the README with no corresponding log, or a log with no
   corresponding claim, is a failure in both directions.

  usage: check_readme.py <log directory written by verify.sh>
"""

from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")

SCAFFOLD_MARKERS = [
    "TODO",
    "FIXME",
    "NOT YET VERIFIED",
    "replace with a real description",
    "XXX",
    "lorem ipsum",
]

SUCCESS_LINE = "VERIFY PASSED"

# label in the README's counts table -> (log file, regex capturing the number)
COUNT_SOURCES = {
    "unit tests": ("unit.log", r"^Ran (\d+) tests"),
    "reference values": ("reference.log", r"^reference rows: (\d+)"),
    "negative controls": ("reference.log", r"negative controls: (\d+)"),
    "parity cases": ("parity.log", r"^parity cases: (\d+)"),
    "simulation scenarios": ("independent.log", r"^(\d+) scenarios,"),
    "sabotages": ("sabotage.log", r"^(\d+) sabotages:"),
    "browser assertions": ("browser.log", r"^\s*ok\s"),  # counted, not captured
}


def strip_fenced(text: str) -> str:
    out = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append(line)
    if fenced:
        raise SystemExit("README has an unterminated fenced code block")
    return "\n".join(out)


def parse_counts_table(text: str) -> dict:
    """Read the pipe table under the 'What the verify run checks' heading."""
    counts = {}
    for line in text.splitlines():
        match = re.match(r"^\|\s*([a-z ]+?)\s*\|\s*([\d,]+)\s*\|", line)
        if match and match.group(1) in COUNT_SOURCES:
            counts[match.group(1)] = int(match.group(2).replace(",", ""))
    return counts


def observed_counts(log_dir: str) -> dict:
    found = {}
    for label, (log_name, pattern) in COUNT_SOURCES.items():
        path = os.path.join(log_dir, log_name)
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            lines = fh.read().splitlines()
        if label == "browser assertions":
            found[label] = sum(1 for line in lines if re.match(pattern, line))
            continue
        for line in lines:
            match = re.search(pattern, line)
            if match:
                found[label] = int(match.group(1))
                break
    return found


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_readme.py <log directory>", file=sys.stderr)
        return 2
    log_dir = sys.argv[1]

    if not os.path.exists(README):
        print("FAIL: README.md does not exist")
        return 1
    with open(README) as fh:
        raw = fh.read()
    prose = strip_fenced(raw)

    failures = []

    for marker in SCAFFOLD_MARKERS:
        if marker.lower() in prose.lower():
            for lineno, line in enumerate(prose.splitlines(), start=1):
                if marker.lower() in line.lower():
                    failures.append(f"scaffold marker {marker!r} in the prose: {line.strip()[:80]}")
                    break
    print(f"scaffold markers outside fenced blocks: "
          f"{len([f for f in failures if 'scaffold marker' in f])}")

    if "## Status" not in raw:
        failures.append("README has no '## Status' section")
    else:
        status = raw.split("## Status", 1)[1]
        if SUCCESS_LINE not in status:
            failures.append(
                f"the Status section does not contain {SUCCESS_LINE!r}, so it does not "
                "hold the pasted output of a passing run"
            )
        else:
            print(f"Status section carries the verify success line {SUCCESS_LINE!r}")

    claimed = parse_counts_table(raw)
    observed = observed_counts(log_dir)
    print(f"counts claimed in the README: {claimed}")
    print(f"counts observed in this run:  {observed}")
    for label in COUNT_SOURCES:
        if label not in observed:
            failures.append(
                f"no log produced a count for {label!r}, so the README's claim about it "
                "cannot be checked. Run the full verify rather than a partial one."
            )
        elif label not in claimed:
            failures.append(f"the README's counts table does not mention {label!r}")
        elif claimed[label] != observed[label]:
            failures.append(
                f"the README claims {claimed[label]} {label} and this run produced "
                f"{observed[label]}"
            )

    for required in ("cluster", "design effect", "ICC", "clusterPower", "pwr"):
        if required.lower() not in prose.lower():
            failures.append(f"the README never mentions {required!r}")

    if failures:
        print(f"README CHECK FAILED: {len(failures)}")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("README check PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
