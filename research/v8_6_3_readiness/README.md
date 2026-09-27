# v8.6.3 operational-readiness snapshot — 27 September 2026

**Current state: PAUSED / BLOCKED (fail-closed).**

This directory records the latest additive operational work around the frozen
v8.6.3 preregistration. It does not amend `MASTER_LOCK_v8_6_3.md`, does not
replace any registered model, and does not convert engineering checks into
confirmatory observations.

## What is established

- The frozen item pool SHA-256 remains
  `128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3`.
- The recovered master-lock SHA-256 recorded by the offline readiness audit is
  `b3394f637a73ffe835866862d4781cb8928e137c586bd8d79241d9c3713ccbbf`.
- The offline readiness checker passes the recovered lock, item-pool, review
  sources, exact utility-name enforcement, collector fail-closed checks, and
  the credential-safe endpoint-checker source.
- All 12 frozen open-weight source identities have been mapped to pinned source
  revisions.
- No final study deployment binding has been accepted merely from a catalog
  alias or an optimized hosted label.
- No confirmatory collection has been started.

## Current blockers

The latest fail-closed report remains blocked on:

1. final 20-position `roster_bindings.json`;
2. the eight closed target IDs;
3. closed snapshot/same-vendor-successor evidence;
4. the registered-style eight-cell endpoint availability report;
5. the operational runtime lock;
6. completion of the remaining operational freeze inputs.

The open-weight binding audit further records **12/12 source identities pinned**
but **0/12 final deployment bindings accepted**. A deployment slot requires a
real ID, endpoint, revision/equivalent source-verification record, and explicit
verification evidence.

## Pause point

Work is intentionally paused at this boundary. The next valid continuation is
to resolve operational bindings and runtime evidence without changing the
frozen scientific specification. If those requirements cannot be met, v8.6.3
remains preserved as an unexecuted frozen confirmatory protocol rather than
being silently rewritten.

## Files in this snapshot

- `CURRENT_READINESS_REPORT.json` — exact offline readiness result.
- `OPEN_WEIGHT_BINDING_RESOLUTION_2026_09_27.md` — human-readable 12-model source-binding audit.
- `roster_bindings.template.json` — unresolved 20-position binding schema.
- `runtime_lock.template.json` — unresolved runtime-lock schema.
- `closed_endpoint_resolution.template.json` — unresolved closed-cell identity/successor schema.
- `SHA256SUMS.txt` — byte hashes for the archived readiness inputs/results represented here.

No credential values are stored in this directory.
