#!/usr/bin/env python3
"""Scan every tracked file for credentials and personal paths.

Four things this does that a naive scanner does not, each because the naive version
has failed in this workspace before.

1. POSITIVE CONTROL. A file containing a credential-shaped string is written into a
   temporary directory and scanned first. If the scanner does not find it, the
   scanner is broken and the run aborts. A scanner that reads nothing reports the
   same clean result as a scanner that read everything.

2. PATTERNS ASSEMBLED FROM FRAGMENTS. This file is itself tracked and therefore
   scanned. A pattern written out whole would match its own definition and report a
   permanent false positive, and the usual fix, excluding the scanner from its own
   scan, disarms the check exactly where it is tested. So each pattern is built by
   joining pieces at run time and no complete pattern exists on disk.

3. NUL BYTES ARE A FAILURE, NOT A SKIP. git and grep classify a file containing a NUL
   as binary and skip it, so one NUL byte makes a whole file invisible to a scan.
   Proven in this workspace by committing a real token into such a file and watching
   the scan report clean. Here the files are read as bytes and a NUL in a text file
   fails the run with the fix named: write it as the two character escape instead.

4. AN EMPTY FILE LIST IS A FAILURE. Before the first commit `git ls-files` returns
   nothing and a scan of nothing passes without opening a file.

Case sensitivity is deliberate where the real format is fixed. AWS key ids are
uppercase by definition, and a case insensitive match for them fires on ordinary
base64, which is how an embedded PNG once became a credential alert.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MIN_TRACKED_FILES = 12

# Text extensions. Anything else is read as bytes and only checked for a token, not
# for a NUL.
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".json", ".md", ".html", ".css", ".sh", ".yml",
                 ".yaml", ".txt", ".gitignore", ""}


def patterns() -> list:
    """Build the credential patterns from fragments so this file does not match them."""
    hex40 = "[0-9a-f]{" + "40" + "}"
    b64ish = "[A-Za-z0-9_\\-]{" + "35," + "}"
    joined = [
        ("aws access key id", "A" + "KIA" + "[0-9A-Z]{16}", 0),
        ("github token", "gh" + "[pousr]" + "_" + "[A-Za-z0-9]{36,}", 0),
        ("openai style key", "sk" + "-" + "[A-Za-z0-9]{20,}", 0),
        ("openrouter key", "sk" + "-or-" + "v1-" + "[A-Za-z0-9]{20,}", 0),
        ("google api key", "AI" + "za" + "Sy" + b64ish, 0),
        ("slack token", "xo" + "x" + "[abprs]" + "-" + "[A-Za-z0-9-]{10,}", 0),
        ("private key header", "-----" + "BEGIN " + "[A-Z ]*" + "PRIVATE KEY" + "-----", 0),
        ("bearer token literal", "[Bb]" + "earer" + r"\s+" + "[A-Za-z0-9._\\-]{25,}", 0),
        ("hex secret assignment",
         "(secret|token|password|passwd|api_?key)" + r"\s*[=:]\s*" + "['\"]?" + hex40, re.I),
        ("home directory path", "/" + "home" + "/" + "[a-z][a-z0-9_-]{2,}" + "/", 0),
        ("private ipv4", r"\b" + "192" + r"\.168\." + r"\d{1,3}\.\d{1,3}\b", 0),
    ]
    return [(name, re.compile(pattern, flags)) for name, pattern, flags in joined]


# The scan runs over source, so an example that is obviously a placeholder must not
# fire. Each allowance names the exact literal, never a whole file or a whole rule.
ALLOWED_LITERALS = {
    "/home/user/",
    "/home/runner/",
}


def tracked_files() -> list:
    proc = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"git ls-files failed: {proc.stderr}")
    return [line for line in proc.stdout.splitlines() if line]


def scan_bytes(name: str, blob: bytes, rules: list, is_text: bool) -> list:
    hits = []
    if is_text and b"\0" in blob:
        hits.append((name, 0, "NUL byte",
                     "this file contains a literal NUL, which makes git and grep treat "
                     "it as binary and skip it in every later scan. Write it as the two "
                     "character escape \\0 instead; identical semantics, and the file "
                     "stays text."))
        return hits
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        for rule_name, rule in rules:
            for match in rule.finditer(line):
                if match.group(0) in ALLOWED_LITERALS:
                    continue
                hits.append((name, lineno, rule_name, match.group(0)[:60]))
    return hits


def positive_control(rules: list) -> None:
    """Plant credential-shaped strings where the scanner will read them."""
    planted = {
        "aws access key id": "A" + "KIA" + "QRSTUVWXYZ012345",
        "github token": "gh" + "p" + "_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
        "openai style key": "sk" + "-" + "abcdefghijklmnopqrstuvwxyz012345",
        "home directory path": "/" + "home" + "/" + "someone" + "/notes.txt",
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "planted.txt")
        with open(path, "w") as fh:
            for label, value in planted.items():
                fh.write(f"{label}: {value}\n")
        with open(path, "rb") as fh:
            hits = scan_bytes("positive-control", fh.read(), rules, True)
        found = {hit[2] for hit in hits}
        missing = sorted(set(planted) - found)
        if missing:
            raise SystemExit(
                "POSITIVE CONTROL FAILED: the scanner did not find planted "
                f"{missing}. Every clean result from this scanner is meaningless "
                "until that is fixed."
            )
        print(f"positive control: {len(found)} of {len(planted)} planted secrets found "
              f"({', '.join(sorted(found))})")

    # And a negative control on the control: ordinary text must not fire.
    benign = b"the design effect is 1 + (m - 1) * icc, and 24 clusters per arm suffice\n"
    if scan_bytes("benign", benign, rules, True):
        raise SystemExit("the scanner fires on ordinary prose, which makes it useless")
    print("negative control: ordinary prose does not match any pattern")


def main() -> int:
    rules = patterns()
    positive_control(rules)

    files = tracked_files()
    if len(files) < MIN_TRACKED_FILES:
        raise SystemExit(
            f"only {len(files)} tracked files. A scan of an empty index passes without "
            f"opening anything, so fewer than {MIN_TRACKED_FILES} is treated as a "
            "failure. Commit before scanning."
        )

    hits = []
    scanned_bytes = 0
    for name in files:
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as fh:
            blob = fh.read()
        scanned_bytes += len(blob)
        suffix = os.path.splitext(name)[1]
        hits.extend(scan_bytes(name, blob, rules, suffix in TEXT_SUFFIXES))

    print(f"scanned {len(files)} tracked files, {scanned_bytes} bytes, "
          f"{len(rules)} patterns")
    if hits:
        print(f"PRIVACY SCAN FAILED: {len(hits)} findings")
        for name, lineno, rule_name, detail in hits:
            print(f"  - {name}:{lineno} {rule_name}: {detail}")
        return 1
    print("privacy scan PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
