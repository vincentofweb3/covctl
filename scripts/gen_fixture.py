#!/usr/bin/env python3
"""Regenerate the contract-derived fixture used by `covctl selftest`.

The fixture is CovenantGuard's observable surface, extracted without importing
it: importing needs the GenVM SDK and a runner, so this reads the source bytes
instead. Every value is pinned to the source sha256, which lets `selftest`
detect drift instead of drifting silently.

    python scripts/gen_fixture.py --contract ../covenant/contracts/covenant_guard.py
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "contracts" / "covenant_guard.py"
DEFAULT_OUTPUT = REPO_ROOT / "fixtures" / "covenant_guard_constants.json"

TRACKED_CONSTANTS = ("HASH_VERSION", "MAX_COVENANT_LEN", "MAX_EXCERPT_LEN", "CONTROL_MARKERS")

FORMULA_MARKERS = (
    'payload = "|".join([HASH_VERSION, tag] + [str(f) for f in fields])',
    'hashlib.sha256(payload.encode("utf-8")).hexdigest()',
)

SAMPLE = (
    "Clause 1: Recurring monthly payments to an approved vendor are permitted "
    "up to 5000 USD equivalent.\n"
    "Clause 2: No single payment above 50000 may be released without multisig approval."
)


def digest(tag: str, fields: list, version: str) -> str:
    """The contract's `_digest`, written out literally on purpose."""
    payload = "|".join([version, tag] + [str(field) for field in fields])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stored_text(raw: str) -> str:
    """`_check_text` storage: `str(value).strip()`."""
    return str(raw).strip()


def stored_excerpt(covenant: str, excerpt: str, limit: int) -> str | None:
    """`_normalize`'s excerpt path: strip, truncate, then substring check."""
    text = str(covenant).strip()
    candidate = str(excerpt).strip()
    if not candidate:
        return None
    candidate = candidate[:limit]
    return candidate if candidate in text else None


def extract_constants(source: str) -> dict:
    tree = ast.parse(source)
    found: dict = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in TRACKED_CONSTANTS:
                found[target.id] = ast.literal_eval(node.value)
    missing = [name for name in TRACKED_CONSTANTS if name not in found]
    if missing:
        raise SystemExit(f"contract is missing constants: {', '.join(missing)}")
    return found


def commit_of(contract: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(contract.parent), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def build(contract: Path, commit: str | None) -> dict:
    raw = contract.read_bytes()
    source = raw.decode("utf-8")

    constants = extract_constants(source)
    for marker in FORMULA_MARKERS:
        if marker not in source:
            raise SystemExit(f"contract no longer contains the expected formula: {marker}")

    version = constants["HASH_VERSION"]
    excerpt_limit = constants["MAX_EXCERPT_LEN"]

    digest_vectors = [
        {
            "label": "example covenant",
            "tag": "covenant",
            "fields": [SAMPLE],
            "sha256": digest("covenant", [SAMPLE], version),
        },
        {
            "label": "empty field still hashes",
            "tag": "covenant",
            "fields": [""],
            "sha256": digest("covenant", [""], version),
        },
        {
            "label": "unicode is hashed as UTF-8",
            "tag": "covenant",
            "fields": ["Café — ünïcode ✓"],
            "sha256": digest("covenant", ["Café — ünïcode ✓"], version),
        },
        {
            "label": "CRLF inside the stored text is preserved",
            "tag": "covenant",
            "fields": ["Clause 1: one.\r\nClause 2: two."],
            "sha256": digest("covenant", ["Clause 1: one.\r\nClause 2: two."], version),
        },
        {
            "label": "operation tag is domain separated",
            "tag": "operation",
            "fields": ["allow"],
            "sha256": digest("operation", ["allow"], version),
        },
        {
            "label": "two fields are joined with a pipe",
            "tag": "verdict",
            "fields": ["allow", "Clause 1: one."],
            "sha256": digest("verdict", ["allow", "Clause 1: one."], version),
        },
    ]

    long_prefix = "x" * excerpt_limit
    normalization_vectors = [
        {"label": "trailing newline is stripped", "raw": SAMPLE + "\n", "stored": stored_text(SAMPLE + "\n")},
        {"label": "surrounding whitespace is stripped", "raw": "  " + SAMPLE + "  ", "stored": SAMPLE},
        {"label": "internal CRLF is not rewritten", "raw": "a\r\nb\r\n", "stored": "a\r\nb"},
        {"label": "blank input stores empty", "raw": " \n\t ", "stored": ""},
    ]

    excerpt_vectors = [
        {
            "label": "exact clause",
            "covenant": SAMPLE,
            "excerpt": "Recurring monthly payments to an approved vendor are permitted",
            "verifiable": True,
            "stored": stored_excerpt(
                SAMPLE, "Recurring monthly payments to an approved vendor are permitted", excerpt_limit
            ),
        },
        {
            "label": "case change is not verbatim",
            "covenant": SAMPLE,
            "excerpt": "Recurring monthly payments to an approved vendor are permitted".upper(),
            "verifiable": False,
            "stored": None,
        },
        {
            "label": "empty excerpt",
            "covenant": SAMPLE,
            "excerpt": "",
            "verifiable": False,
            "stored": None,
        },
        {
            "label": "whitespace-only excerpt",
            "covenant": SAMPLE,
            "excerpt": "   \n\t",
            "verifiable": False,
            "stored": None,
        },
        {
            "label": "surrounding whitespace is trimmed",
            "covenant": SAMPLE,
            "excerpt": "  Clause 2: No single payment above 50000 may be released without multisig approval.  ",
            "verifiable": True,
            "stored": "Clause 2: No single payment above 50000 may be released without multisig approval.",
        },
        {
            "label": "over-long excerpt keeps only its first 320 chars",
            "covenant": long_prefix + "TAIL",
            "excerpt": long_prefix + "TAIL",
            "verifiable": True,
            "stored": long_prefix,
        },
        {
            "label": "over-long excerpt whose prefix is absent fails",
            "covenant": "short covenant",
            "excerpt": long_prefix + "TAIL",
            "verifiable": False,
            "stored": None,
        },
        {
            "label": "CRLF covenant keeps its exact bytes",
            "covenant": "Clause 1: one.\r\nClause 2: two.",
            "excerpt": "Clause 2: two.",
            "verifiable": True,
            "stored": "Clause 2: two.",
        },
        {
            "label": "citation may span clauses",
            "covenant": SAMPLE,
            "excerpt": "permitted up to 5000 USD equivalent.",
            "verifiable": True,
            "stored": "permitted up to 5000 USD equivalent.",
        },
    ]

    return {
        "provenance": {
            "repository": "https://github.com/vincentofweb3/covenant",
            "path": "contracts/covenant_guard.py",
            "commit": commit or "unknown",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "generated_by": "scripts/gen_fixture.py",
        },
        "constants": constants,
        "normalization_vectors": normalization_vectors,
        "digest_vectors": digest_vectors,
        "excerpt_vectors": excerpt_vectors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--commit", default=None, help="override the git commit recorded as provenance")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.contract.is_file():
        parser.error(f"contract not found: {args.contract}")

    fixture = build(args.contract, args.commit or commit_of(args.contract))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({len(fixture['digest_vectors'])} digest, {len(fixture['excerpt_vectors'])} excerpt vectors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
