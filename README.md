# covctl

[![ci](https://github.com/vincentofweb3/covctl/actions/workflows/ci.yml/badge.svg)](https://github.com/vincentofweb3/covctl/actions/workflows/ci.yml)

A covenant compiler, policy linter and digest for GenLayer `CovenantGuard`.

**Site:** <https://vincentofweb3.github.io/covctl/> · **Related:** [Covenant](https://github.com/vincentofweb3/covenant)

`covctl` is a single-file, dependency-free CLI. It is meant to be run **before**
a covenant is deployed, because the defects it catches are silent at runtime —
they show up as downgraded verdicts, not errors. It never calls the chain.

```console
$ covctl lint examples/covenant.md --strict
INFO    I020: 5 permitting and 2 prohibiting clause(s). Confirm none address the same subject; the model cannot resolve a genuine contradiction and will pick one.

5 clause(s), 451 chars (contract length)
0 error(s), 0 warning(s), 1 info
```

## What the contract does with the text

The linter is only useful if it agrees with the contract. `CovenantGuard`
stores `str(value).strip()` and hashes those exact bytes. Before deciding an
`ALLOWED` verdict it strips the model's excerpt, truncates it to
`MAX_EXCERPT_LEN` (320), and requires the result to be a verbatim substring of
the stored covenant. Text longer than `MAX_COVENANT_LEN` (8000) and any of eight
control markers are rejected at the boundary.

That produces three ways to write a policy that looks fine and still cannot
permit what it appears to permit:

| Defect | What happens on-chain | What `covctl` reports |
|---|---|---|
| Clause longer than the excerpt cap | It can be cited **in part**, never in full: the tail is truncated, so a ruling may miss a condition | `W010` warning, with the character count |
| Clause too short to be distinctive | It does not narrow the model's judgement | `W011` warning |
| Prohibitions with no permissions | A compliant action and an unmentioned one look the same; the guard can only refuse | `W012` warning |

It also rejects active control language at the boundary (`E003`) and flags a
covenant that both permits and prohibits (`I020`): the model cannot resolve a
genuine collision between them and will silently pick one.

```console
$ covctl lint bad.md
ERROR   E003: contains 'ignore previous instructions'; the contract rejects this at the boundary as active control language
WARNING W030: the covenant says nothing about what to do when evidence is ambiguous. ...
```

### Rule map

`error` means the contract will reject the covenant, or every ruling will fail.
`warning` is advisory: the covenant deploys, but a rule is weak or unsafe.

| Code | Severity | Meaning |
|---|---|---|
| `E001` | error | empty after trimming; the contract rejects it |
| `E002` | error | over `MAX_COVENANT_LEN` after trimming |
| `E003` | error | contains a control marker the contract rejects |
| `W010` | warning | over `MAX_EXCERPT_LEN`; cannot be cited in full |
| `W011` | warning | under 24 characters; too weak to narrow a decision |
| `W012` | warning | forbids everything and permits nothing |
| `I020` | info | both permitting and prohibiting clauses; confirm they do not collide |
| `W021` | warning | threshold number with no unit |
| `W030` | warning | no ambiguity fallback |
| `W040` | warning | referenced list is never defined |
| `W050` | warning | numbering gap |

## Contract parity

The exact contract source is vendored byte for byte at
[`vendor/covenant_guard.py`](vendor/covenant_guard.py) (MIT, from Covenant at
commit `0034b5e`), and its observable surface is checked in as
[`fixtures/covenant_guard_constants.json`](fixtures/covenant_guard_constants.json).
The fixture records the source repository, path, commit and sha256, plus the
four constants, four normalisation vectors, six digest vectors and nine excerpt
vectors.

[`tests/test_contract_parity.py`](tests/test_contract_parity.py) re-derives
every vector independently, parses the vendored source to extract the constants
and checks the formula and limit code, so a bug shared by the generator and the
tool still fails.

```console
$ covctl selftest
OK: 4 normalization, 6 digest and 9 excerpt vectors match the contract
    fixture: https://github.com/vincentofweb3/covenant/contracts/covenant_guard.py @ 0034b5e40a88
    sha256:  e55b9c3f082c17a300506f1645d8a349af5c11be70624e10dbf267d12bee2b12
```

`selftest` also requires the vendored source's sha256 to match the pinned
provenance, so silent drift is a hard failure. When no fixture is found, it
**exits 1** rather than skipping with a success code.

Regenerate the fixture from the contract with:

```console
$ python3 scripts/gen_fixture.py --contract ../covenant/contracts/covenant_guard.py
```

### Exact input handling

Two details decide whether the digest is right:

- the text is stripped before length checks, the digest and storage — a trailing
  newline changes nothing;
- files are read with `newline=""`, so CRLF is preserved byte for byte. LF and
  CRLF covenants hash differently, because they are different text.

`split_clauses` supports numbered clauses (`Clause 3: ...`, `3. ...`) and
blank-line separated paragraphs, and every `citable` value is an exact
substring of the stored covenant.

## The digest is the contract's digest

`covctl digest` reproduces `covenant_guard._digest("covenant", [text])` byte for
byte:

```python
payload = "|".join(["covenant-sha256-v1", "covenant", covenant])
hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

This is the point of the tool. A compiler that prints the wrong hash is worse
than no compiler, because the published digest would not match the deployed
contract and nobody would notice until an auditor checked. The digest for
`examples/covenant.md` is pinned in the test suite and matches the live
deployment's `get_covenant_hash`:

```
afd824702fd05cd7c277adf84d8d1c9feba669eeda8ba50681b67259d363837b
```

## Install

No install is required — it is one stdlib-only file:

```console
$ python3 covctl.py digest examples/covenant.md
```

Or install the `covctl` command:

```console
$ pipx install git+https://github.com/vincentofweb3/covctl
```

## Commands

| Command | Purpose |
|---|---|
| `lint PATH [--strict]` | report defects that would degrade or defeat rulings |
| `compile PATH` | emit parsed clauses and the digest as canonical JSON |
| `digest PATH` | print the digest the contract will compute |
| `check-excerpt PATH --excerpt TEXT` | apply the contract's exact citation test locally |
| `selftest` | verify constants, digest and excerpt vectors against the pinned fixture |

`check-excerpt` mirrors the on-chain check, including truncation:

```console
$ covctl check-excerpt examples/covenant.md --excerpt "Recurring monthly payments to an approved vendor are permitted."
VALID: cited from Clause 2

$ covctl check-excerpt examples/covenant.md --excerpt "Recurring payments to an approved vendor are permitted."
INVALID: excerpt does not occur verbatim in the stored covenant
        the contract would discard it and record AMBIGUOUS / UNVERIFIED_EXCERPT
```

Exit codes: `0` success, `1` errors or a failed check.

## Scope

This checks the covenant **text**. It cannot tell you whether a model will read
a clause the way you meant it — only that the clause is citable, distinctive and
not self-contradictory. The runtime guarantees belong to the contract.

## Related

[Covenant](https://github.com/vincentofweb3/covenant) — the guard this tool
checks covenants for, and the deployment that pins the digest above.
