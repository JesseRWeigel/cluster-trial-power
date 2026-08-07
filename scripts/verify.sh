#!/usr/bin/env bash
# Verify the cluster trial power calculator. The exit code IS the result.
#
# Nothing here prints success for a step it did not run. A missing dependency is a
# FAILURE with the install command named, never a skip, because a skipped check and a
# passing check look identical in a log a week later.
#
# The run must not modify the tree it verifies. Every tracked file is digested before
# and after, and any change, along with any new untracked file, is a named failure. A
# verify that edits the repository can pass on a later run for reasons an earlier run
# created, which is indistinguishable from working.
#
#   bash scripts/verify.sh              full run
#   CTP_FAST=1 bash scripts/verify.sh   skip the sabotage stage, which is the slow one
#
# CTP_FAST still exits nonzero at the end. It is for iterating, not for reporting.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WORK="$(mktemp -d)"
LOGS="$WORK/logs"
mkdir -p "$LOGS"
trap 'rm -rf "$WORK"' EXIT

FAILURES=0
STAGES=0

step() {
  local name="$1"; shift
  STAGES=$((STAGES + 1))
  printf '\n=== %s ===\n' "$name"
  if "$@"; then
    printf '[ok] %s\n' "$name"
  else
    printf '[FAIL] %s\n' "$name"
    FAILURES=$((FAILURES + 1))
  fi
}

require() {
  local binary="$1" install="$2"
  if ! command -v "$binary" >/dev/null 2>&1; then
    printf '\n=== dependency: %s ===\n' "$binary"
    printf 'MISSING. Install it with: %s\n' "$install"
    printf 'This is a failure rather than a skip. Without %s the run cannot check %s.\n' \
      "$binary" "$3"
    FAILURES=$((FAILURES + 1))
    STAGES=$((STAGES + 1))
    return 1
  fi
  return 0
}

digest_tree() {
  git ls-files -z | xargs -0 sha256sum | sort
}

# --------------------------------------------------------------------------

printf 'cluster-trial-power verify\n'
printf 'python: %s\n' "$(python3 --version 2>&1)"
printf 'node:   %s\n' "$(node --version 2>&1 || echo MISSING)"
printf 'R:      %s\n' "$(command -v R || echo 'absent, see README on what validation this run does and does not establish')"

BEFORE="$WORK/before.sha"
digest_tree > "$BEFORE"
TRACKED=$(wc -l < "$BEFORE")
printf 'tracked files digested: %s\n' "$TRACKED"
if [ "$TRACKED" -lt 15 ]; then
  printf 'FAIL: only %s tracked files. Commit before verifying; a scan of an empty index passes without opening anything.\n' "$TRACKED"
  exit 1
fi

have_node=0
have_chrome=0
require node "sudo apt-get install nodejs" "the browser page or the javascript port" && have_node=1
if [ -x "${CHROME_PATH:-/usr/bin/google-chrome}" ] || command -v chromium >/dev/null 2>&1; then
  have_chrome=1
else
  printf '\n=== dependency: chrome ===\n'
  printf 'MISSING. Install it with: sudo apt-get install google-chrome-stable, or set CHROME_PATH.\n'
  printf 'This is a failure rather than a skip. The unit suite imports the engine directly\n'
  printf 'and never loads the page, so without a browser nothing here would notice a page\n'
  printf 'whose inline script fails to parse.\n'
  FAILURES=$((FAILURES + 1))
  STAGES=$((STAGES + 1))
fi

# 1. unit tests -------------------------------------------------------------
unit_tests() {
  python3 -m unittest discover -s tests -v 2>&1 | tee "$LOGS/unit.log" | tail -4
  return "${PIPESTATUS[0]}"
}
step "unit tests" unit_tests

# 2. published reference values and negative controls -----------------------
reference() {
  python3 scripts/check_reference.py 2>&1 | tee "$LOGS/reference.log" | tail -6
  return "${PIPESTATUS[0]}"
}
step "reference values against published sources, with negative controls" reference

# 3. python / javascript parity ---------------------------------------------
parity() {
  python3 scripts/parity_dump.py "$WORK/parity.json" > /dev/null || return 1
  node scripts/parity_check.mjs "$WORK/parity.json" 2>&1 | tee "$LOGS/parity.log" | tail -5
  return "${PIPESTATUS[0]}"
}
if [ "$have_node" = 1 ]; then
  step "python and javascript engines agree" parity
fi

# 4. independent recomputation by simulation --------------------------------
independent() {
  python3 scripts/check_independent.py --replications "${CTP_REPLICATIONS:-20000}" 2>&1 \
    | tee "$LOGS/independent.log" | tail -16
  return "${PIPESTATUS[0]}"
}
step "independent monte carlo recomputation" independent

# 5. the published page is generated, not hand edited -----------------------
page_is_current() {
  python3 scripts/build_page.py "$WORK/index.html" > /dev/null || return 1
  if diff -u docs/index.html "$WORK/index.html" > "$LOGS/page.diff"; then
    printf 'docs/index.html matches what scripts/build_page.py produces\n'
    return 0
  fi
  printf 'docs/index.html has drifted from its generator. Diff:\n'
  head -40 "$LOGS/page.diff"
  return 1
}
step "published page rebuilds identically" page_is_current

# 6. the page in a real browser ---------------------------------------------
browser() {
  python3 scripts/browser_expectations.py "$WORK/expected.json" || return 1
  timeout 300 node scripts/browser_check.mjs "$WORK/expected.json" 2>&1 \
    | tee "$LOGS/browser.log" | tail -8
  return "${PIPESTATUS[0]}"
}
if [ "$have_node" = 1 ] && [ "$have_chrome" = 1 ]; then
  step "real headless chrome, desktop and 390px" browser
fi

# 7. privacy ----------------------------------------------------------------
privacy() {
  python3 scripts/privacy_scan.py 2>&1 | tee "$LOGS/privacy.log" | tail -4
  return "${PIPESTATUS[0]}"
}
step "privacy scan with a positive control" privacy

# 8. sabotage ---------------------------------------------------------------
sabotage() {
  python3 scripts/sabotage.py 2>&1 | tee "$LOGS/sabotage.log" | tail -6
  return "${PIPESTATUS[0]}"
}
if [ "${CTP_FAST:-0}" = "1" ]; then
  printf '\n=== sabotage ===\n'
  printf 'SKIPPED because CTP_FAST=1. This run therefore cannot pass.\n'
  FAILURES=$((FAILURES + 1))
  STAGES=$((STAGES + 1))
else
  step "sabotage under the three gate rule, null control first" sabotage
fi

# 9. the README is true ------------------------------------------------------
readme() {
  python3 scripts/check_readme.py "$LOGS" 2>&1 | tee "$LOGS/readme.log" | tail -20
  return "${PIPESTATUS[0]}"
}
step "README states the truth, including the counts" readme

# 10. the run changed nothing ------------------------------------------------
printf '\n=== tree unchanged by this run ===\n'
AFTER="$WORK/after.sha"
digest_tree > "$AFTER"
STAGES=$((STAGES + 1))
if diff -u "$BEFORE" "$AFTER" > "$WORK/tree.diff"; then
  UNTRACKED="$(git status --porcelain --untracked-files=all | grep '^??' || true)"
  if [ -n "$UNTRACKED" ]; then
    printf '[FAIL] the run left new untracked files behind:\n%s\n' "$UNTRACKED"
    FAILURES=$((FAILURES + 1))
  else
    printf '[ok] all %s tracked files have the same digest, and no new files appeared\n' "$TRACKED"
  fi
else
  printf '[FAIL] the run modified the tree it was verifying:\n'
  head -20 "$WORK/tree.diff"
  FAILURES=$((FAILURES + 1))
fi

# --------------------------------------------------------------------------
printf '\n========================================\n'
if [ "$FAILURES" -eq 0 ]; then
  printf 'VERIFY PASSED: %s stages, 0 failures\n' "$STAGES"
  exit 0
fi
printf 'VERIFY FAILED: %s of %s stages\n' "$FAILURES" "$STAGES"
exit 1
