# covctl

A covenant compiler, policy linter and digest for GenLayer `CovenantGuard`.

`covctl` is a single-file, dependency-free CLI. It is meant to be run **before**
a covenant is deployed, because the defects it catches are silent at runtime —
they show up as downgraded verdicts, not errors.

```console
$ covctl lint examples/covenant.md --strict
INFO    I020: 5 permitting and 2 prohibiting clause(s). Confirm none address the same subject; the model cannot resolve a genuine contradiction and will pick one.

5 clause(s), 451 chars
0 error(s), 0 warning(s), 1 info
```

## What it catches

`CovenantGuard` only honours an `ALLOWED` verdict whose excerpt is a verbatim
substring of the stored covenant, capped at 320 characters. That single rule
creates three ways to write a policy that looks fine and never actually permits
anything:

| Defect | What happens on-chain | What `covctl` reports |
|---|---|---|
| Clause longer than the excerpt cap | It can never be cited in full, so every ruling relying on it degrades to `AMBIGUOUS` | error, with the character count |
| Clause too short to be distinctive | It does not narrow the model's judgement | warning |
| Prohibitions with no permissions | A compliant action is indistinguishable from a violation | warning |

It also rejects active control language (`ignore previous instructions`, …) at
the boundary, and warns when a clause pair addresses the same subject in
opposite directions — the model cannot resolve a genuine contradiction and will
silently pick one.

```console
$ covctl lint bad.md
ERROR   E003: contains 'ignore previous instructions'; the contract rejects this at the boundary as active control language
WARNING W030: the covenant says nothing about what to do when evidence is ambiguous. ...
```

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
| `selftest` | check the digest formula against `covenant_guard.py` |

`check-excerpt` mirrors the on-chain check, including the length cap:

```console
$ covctl check-excerpt examples/covenant.md --excerpt "Recurring monthly payments to an approved vendor are permitted."
VALID: cited from Clause 2

$ covctl check-excerpt examples/covenant.md --excerpt "Recurring payments to an approved vendor are permitted."
INVALID: excerpt does not occur verbatim in the covenant
        the contract would discard it and record AMBIGUOUS / UNVERIFIED_EXCERPT
```

Exit codes: `0` success, `1` errors or a failed check.

`selftest` compares the formula against the real contract when one is reachable:

```console
$ COVENANT_GUARD=../covenant/contracts/covenant_guard.py covctl selftest
OK: digest formula matches the contract's HASH_VERSION (...)
```

Without the contract it prints `SKIP` and exits `0`.

## Scope

This checks the covenant **text**. It cannot tell you whether a model will read
a clause the way you meant it — only that the clause is citable, distinctive and
not self-contradictory. The runtime guarantees belong to the contract.

## Licence

MIT. See [LICENSE](LICENSE).
