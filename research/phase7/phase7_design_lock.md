# PHASE 7 DESIGN LOCK
## Inferential Operating-Characteristics Validation

Status: LOCKED BEFORE PRODUCTION
Production replicates completed at lock time: 0 / 500
Production GLMM fits completed at lock time: 0 / 4000

This phase is diagnostic validation for a future prospective design.
It does not modify, amend, merge with, or supersede the frozen
Self-Referential Processing Pre-Registration v8.6.3.

---

## 1. Scientific question

Phase 7 evaluates whether inference for the fixed Self effect is adequately
calibrated under repeated sampling for either of two prespecified GLMM
architectures, despite the random-effects boundary behavior documented in
earlier Design Lab phases.

The phase does not attempt to make singular warnings disappear.

The two generating effects are:

H0: beta_Self = 0.00 log-odds
H1: beta_Self = 0.10 log-odds

The value 0.10 is a log-odds coefficient. It is not a ten-percentage-point
probability effect.

---

## 2. Fit architectures

M1 — correlated model intercept/random-slope architecture:

y ~ X + context_len + is_self +
    (1 | item_id) +
    (1 + is_self | model_id)

M2 — uncorrelated model intercept/random-slope architecture:

y ~ X + context_len + is_self +
    (1 | item_id) +
    (1 + is_self || model_id)

Every generated dataset is fitted with both M1 and M2.

There is no architecture selection within a replicate.

There is no adaptive optimizer switching, warning suppression, fallback model,
or result-dependent refitting.

---

## 3. Locked data-generating parameters

n_models = 100
n_items = 400
n_obs = 40000

tau_model = 0.03
slope_sd = 0.02
tau_item = 0.03

beta_x = 0.15
beta_c = 0.05

beta_c is the fixed coefficient for context_len.

Assignment is exactly balanced within each model:
200 Self observations and 200 Control observations.

The Phase-7 high-information DGP inherits the substantive generator geometry
of the frozen Phase-6 100-model x 400-item HIGH condition:

- X_j is generated as Uniform(9,12) and mean-centered across the 100-model block.
- context_len is an item-level N(0,1) variable shared across models.
- the first 100 items contain exactly 50 Self and 50 Control observations per model.
- items 100 through 399 contain exactly 150 Self and 150 Control observations per model.
- model intercept and Self-slope random effects are generated jointly from the
  locked 2x2 covariance matrix.
- one item random intercept is shared across models for each item.
- Bernoulli outcomes are generated from common stored outcome uniforms.

Phase 7 changes the true Self coefficient across null/effect conditions and
uses a new deterministic production seed namespace; it does not intentionally
change the established Phase-6 HIGH-cell substantive DGP geometry.

Two true model intercept–slope correlations are evaluated:

rho_model = 0.00
rho_model = 0.30

---

## 4. Factorial design

P7_A_NULL_RHO0:
    beta_Self = 0.00
    rho_model = 0.00

P7_B_NULL_RHO30:
    beta_Self = 0.00
    rho_model = 0.30

P7_C_EFFECT_RHO0:
    beta_Self = 0.10
    rho_model = 0.00

P7_D_EFFECT_RHO30:
    beta_Self = 0.10
    rho_model = 0.30

There are 500 production replicates arranged into 10 immutable production blocks of 50 replicates each.

Each replicate contains four generated DGP cells.

Each generated cell is fitted by M1 and M2.

Total production fits:

500 replicates × 4 DGP cells × 2 fit architectures = 4000 GLMM fits.

---

## 5. Deterministic production namespace

PHASE7_BASE_SEED = 92622000

Production replicate numbers are 1 through 500.

Production is executed in ten immutable blocks:

Block 01: reps   1–50
Block 02: reps  51–100
Block 03: reps 101–150
Block 04: reps 151–200
Block 05: reps 201–250
Block 06: reps 251–300
Block 07: reps 301–350
Block 08: reps 351–400
Block 09: reps 401–450
Block 10: reps 451–500

Within a replicate and true-rho condition, null and alternative datasets use
common underlying latent/random-number draws and differ in the locked
beta_Self parameter.

Within a replicate, rho_model = 0.00 and rho_model = 0.30 begin from the same
six underlying random-number streams for X, context, assignment, model-effect
standard-normal draws, item effects, and Bernoulli outcome uniforms. The
rho_model value changes only the locked covariance transformation applied to
the shared underlying model-effect standard-normal draws before outcomes are
generated.

Within each generated DGP cell, M1 and M2 are fitted to the literal same CSV.
Dataset SHA256 is recorded and must be identical across the M1/M2 pair.

Production seeds are never replaced because of convergence, singularity,
warnings, fit failure, or scientific results.

---

## 6. Primary operating characteristics

For beta_Self = 0.00:

- Wald Type-I rejection rate at two-sided alpha = 0.05
- 95% Wald confidence-interval coverage of 0.00
- mean estimate
- signed bias
- empirical SD of estimates
- mean and median model-reported SE
- empirical-SD / mean-SE comparison
- convergence rate
- fit-failure rate
- singularity rate
- random-effect component-collapse rates
- M1 correlation-boundary rate

For beta_Self = 0.10:

- Wald power at two-sided alpha = 0.05
- 95% Wald confidence-interval coverage of 0.10
- mean estimate
- signed bias
- relative bias = bias / 0.10
- empirical SD of estimates
- mean and median model-reported SE
- empirical-SD / mean-SE comparison
- convergence rate
- fit-failure rate
- singularity rate
- random-effect component-collapse rates
- M1 correlation-boundary rate

---

## 7. Analysis population

Singular fits remain in the primary inferential analysis whenever the
prespecified fit successfully returns the required estimate, standard error,
p-value, and confidence interval.

No fit is excluded merely because isSingular() is TRUE.

A fit that fails to return the required inferential quantities is recorded as
a failure and is not regenerated, replaced, or assigned a new seed.

Inferential operating characteristics are calculated over successful evaluable
fits.

Fit-failure and convergence rates are separately calculated over all attempted
fits.

Results are additionally stratified descriptively by singular versus
nonsingular status.

---

## 8. Null calibration criterion

For each architecture and each true-rho condition, the observed Wald rejection
count under beta_Self = 0 will be evaluated for compatibility with nominal
Type-I error probability 0.05 using a prespecified two-sided exact binomial
test.

Both anti-conservative and excessively conservative departures are calibration
failures.

The following are reported:

- rejection count
- observed rejection rate
- exact binomial confidence interval
- exact two-sided binomial p-value against p = 0.05
- Monte Carlo standard error

No one-sided rule such as merely requiring alpha_hat <= 0.0691 is used.

Compatibility criterion:

two-sided exact-binomial p-value >= 0.05.

---

## 9. Coverage criterion

For each architecture, effect condition, and true-rho condition, the number of
95% Wald confidence intervals containing the true generating effect is
evaluated for compatibility with nominal coverage probability 0.95 using the
same prespecified two-sided exact-binomial framework.

The following are reported:

- coverage count
- observed coverage rate
- exact binomial confidence interval
- exact two-sided binomial p-value against p = 0.95
- Monte Carlo standard error

Compatibility criterion:

two-sided exact-binomial p-value >= 0.05.

---

## 10. Power

Power is reported for beta_Self = 0.10.

Power is not itself a validity/calibration acceptance criterion.

Low power indicates insufficient information under the tested design but does
not, by itself, establish estimator invalidity.

---

## 11. Paired M1/M2 diagnostics

Within every generated DGP cell, report paired:

estimate_M2 - estimate_M1
SE_M2 - SE_M1

and paired categorical transitions for:

- rejection
- coverage
- singularity
- fit evaluability

The paired comparison does not replace independent evaluation of M1 and M2
against the locked calibration criteria.

---

## 12. Architecture decision rule

M1 and M2 will be evaluated independently against the prespecified
operating-characteristic criteria. Architecture selection will not be based on
which model produces fewer warnings or on whichever yields the more favorable
substantive result.

If only one architecture demonstrates acceptable null calibration and
confidence-interval coverage across both tested covariance-generating
conditions, that architecture becomes the candidate for the prospective
design.

If both demonstrate acceptable calibration, model choice will be based on
correspondence between the assumed and scientifically intended random-effects
structure, with Phase 7 results reported for both.

If neither demonstrates acceptable calibration, neither architecture will be
promoted to the prospective confirmatory design; the analysis architecture
must instead be redesigned and independently revalidated.

---

## 13. No-peeking rule

During production blocks, only engineering information may be inspected:

- block completion
- attempted-fit counts
- exceptions
- expected seed ranges
- file existence
- SHA256
- dataset pairing
- runtime status
- structural integrity checks

Before all ten production blocks pass integrity verification, do not aggregate
or inspect:

- Type-I error
- power
- coverage
- bias
- architecture inferential comparisons
- singularity-conditioned inferential performance

Engineering smoke tests are permitted before production only with seeds outside
the production namespace and their results must never enter production files.

---

## 14. Production artifacts

Each block produces one immutable raw results CSV and one block manifest JSON.

After all ten blocks pass integrity verification, the aggregation program
creates:

phase7_results.csv
phase7_summary.csv
phase7_paired.csv
phase7_blocks_manifest.csv
phase7_integrity_report.txt
phase7_SHA256SUMS.txt

Canonical source files:

phase7_design_lock.md
phase7_inferential_validation_runner.py
phase7_glmer_fit.R
phase7_aggregate.py

---

## 15. Stop condition

Phase 7 is the final planned Design Lab operating-characteristics validation.

If an architecture satisfies the locked calibration requirements, the result
may inform a new prospective preregistration.

If neither architecture satisfies them, the analysis architecture must be
redesigned and separately validated.

No Phase 8 is automatically created merely because additional simulation is
possible.
