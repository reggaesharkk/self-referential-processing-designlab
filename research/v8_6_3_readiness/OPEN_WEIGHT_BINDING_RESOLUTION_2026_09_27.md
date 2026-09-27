# v8.6.3 Open-Weight Binding Resolution — 27 September 2026

**Status: BLOCKED (fail-closed).**

This is an additive operational-evidence artifact. It does **not** modify or supersede
`MASTER_LOCK_v8_6_3.md`, and no study item, candidate-model, closed-API ping, or
confirmatory collection call was made while producing it.

## What was resolved

The frozen 12-model open-weight portfolio can be mapped to concrete source repositories
and pinned source revisions. That is enough to establish **source identity**, but not
enough to satisfy the final `roster_bindings.json` gate.

The collection-readiness package requires each of the 20 roster positions to have a
resolved `id`, `endpoint`, `revision`, and `verification_evidence`. Public serverless
model names are not sufficient evidence for those four fields when the provider serves
an optimized variant or does not expose a source revision.

| # | Frozen canonical name | Source repository | Pinned source revision | Deployment binding |
|---:|---|---|---|---|
| 1 | Meta-Llama-3.1-8B-Instruct | `meta-llama/Llama-3.1-8B-Instruct` | `0e9e39f249a16976918f6564b8830bc894c89659` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 2 | Meta-Llama-3.1-70B-Instruct | `meta-llama/Llama-3.1-70B-Instruct` | `1605565b47bb9346c5515c34102e054115b4f98b` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 3 | Meta-Llama-3.1-405B-Instruct | `meta-llama/Llama-3.1-405B-Instruct` | `be673f326cab4cd22ccfef76109faf68e41aa5f1` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 4 | Meta-Llama-3.3-70B-Instruct | `meta-llama/Llama-3.3-70B-Instruct` | `6f6073b423013f6a7d4d9f39144961bfbfbc386b` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 5 | Qwen2.5-7B-Instruct | `Qwen/Qwen2.5-7B-Instruct` | `a09a35458c702b33eeacc393d103063234e8bc28` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 6 | Qwen2.5-32B-Instruct | `Qwen/Qwen2.5-32B-Instruct` | `5ede1c97bbab6ce5cda5812749b4c0bdf79b18dd` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 7 | Qwen2.5-72B-Instruct | `Qwen/Qwen2.5-72B-Instruct` | `495f39366efef23836d0cfae4fbe635880d2be31` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 8 | Mistral-7B-Instruct-v0.3 | `mistralai/Mistral-7B-Instruct-v0.3` | `c170c708c41dac9275d15a8fff4eca08d52bab71` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 9 | Mixtral-8x22B-Instruct-v0.1 | `mistralai/Mixtral-8x22B-Instruct-v0.1` | `cc88a6cc19fbd17d9f1c0ee0b0d70a748dce698d` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 10 | Gemma-2-9b-it | `google/gemma-2-9b-it` | `11c9b309abf73637e4b6f9a3fa1e92e615547819` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 11 | Gemma-2-27b-it | `google/gemma-2-27b-it` | `aaf20e6b9f4c0fcf043f6fb2a2068419086d77b0` | BLOCKED_PENDING_ACTUAL_ENDPOINT |
| 12 | DeepSeek-V2.5 | `deepseek-ai/DeepSeek-V2.5` | `c85b5ede86f2a598af339624cac5723861e557ed` | BLOCKED_PENDING_ACTUAL_ENDPOINT |

## Deployment conclusion

**Source pinning: 12/12. Actual study deployment bindings: 0/12 PASS.**

No `roster_bindings.json` is created from provider aliases alone. A roster entry is
accepted only after there is a real deployment resource with a unique model/deployment
ID, endpoint, pinned source revision or equivalent weight verification, and recorded
evidence.

## Recovery decision

v8.6.3 remains **recoverable in principle but not collection-ready**.

The clean route is:

1. keep the 12 source revisions in this ledger fixed;
2. resolve exact study deployments without changing the frozen identities;
3. record the actual unique ID, endpoint, source revision, serving configuration, and
   verification artifact for each deployment;
4. only after all 12 are real, generate the 20-position `roster_bindings.json`;
5. rerun the offline readiness gate;
6. then resolve the remaining runtime and closed-cell operational locks.

## Integrity boundary

- Frozen preregistration changed: **NO**
- Study item calls: **0**
- Candidate evaluation calls: **0**
- Closed API pings: **0**
- Credentials read: **NO**
- Confirmatory data collected: **NO**

Readiness package SHA-256:
`d5f50e128f8a4e7d7bdd93c62f995186412252321af607c3d3bee63fedeeb23d`

MASTER LOCK SHA-256 recorded by the readiness report:
`b3394f637a73ffe835866862d4781cb8928e137c586bd8d79241d9c3713ccbbf`

Item pool SHA-256:
`128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3`
