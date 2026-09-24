# Design Lab: Phase 7 Final Technical Report
## Inferential Validation of the Candidate Gate 5 Architecture
**Frozen Release v1.0 - 24 September 2026**  
**Author:** Prince Upadhyay, Independent Research  
**Email:** starxshark@gmail.com  
**GitHub:** reggaesharkk

## Executive summary
Phase 7 completed the prespecified inferential-validation experiment after recovery from a documented R-environment dependency failure. The recovered production set contains 4,000 GLMM fits across 500 deterministic replicates, four DGP cells, and two candidate analysis architectures (M1 correlated random intercept/slope; M2 uncorrelated random intercept/slope). All ten block manifests passed integrity verification; M1 and M2 were fit to identical datasets within each rep/cell pair.

Under the locked exact-binomial calibration rule, **M1 satisfies the prespecified null Type-I and 95% coverage compatibility screens in both tested covariance-generating conditions; M2 does not.** M1 therefore becomes the candidate architecture for a future prospective design under the locked Phase 7 decision rule. This is not a proof of universal calibration, nor a retroactive modification of the frozen v8.6.3 preregistration.

## 1. Scope and research boundary
This report is a Design Lab validation artifact. It does not amend the frozen Self-Referential Processing Pre-Registration v8.6.3. Phase 7 tests a candidate GLMM architecture for a future/new prospective design. The frozen Gate 5 confirmatory estimator remains the item-level linear probability model specified in that preregistration unless a new preregistration is filed.

## 2. Phase 7 locked design
- DGP cells: beta_Self = 0.00 or 0.10 log-odds crossed with true rho_model = 0.00 or 0.30.
- Architectures: M1 correlated `(1 + is_self | model_id)` and M2 uncorrelated `(1 + is_self || model_id)`, both with item random intercepts.
- Scale: 100 models x 400 items = 40,000 observations per generated dataset.
- Replicates: 500 deterministic production replicates; four DGP cells per replicate; two fits per cell = 4,000 GLMM fits.
- Primary calibration: all successful/evaluable fits, including singular fits when inferential quantities were returned.
- Null criterion: exact two-sided binomial compatibility with Type-I probability 0.05; p >= 0.05 required.
- Coverage criterion: exact two-sided binomial compatibility with nominal 0.95 coverage; p >= 0.05 required.
- Power under beta_Self = 0.10 is descriptive and not an acceptance criterion.

## 3. Recovery and integrity
The initial post-aggregation diagnostic found that Blocks 02-10 contained records but lacked GLMM estimates because the R runtime could not load `lme4`. Blocks 02-10 were archived, the dependency was restored, and only the originally failed prespecified blocks were rerun with unchanged frozen sources and original deterministic seeds. Block 01 was preserved. A partial Block 01 aggregate had been accidentally observed before recovery; no statistical specification or source code was changed afterward. The final aggregation then re-verified every block hash, replicate range, row count, source hash, M1/M2 pair, and same-dataset SHA.

Final integrity: 4,000 rows; 500 unique replicates; 4 cells; M1/M2 present; 10 block manifests; all block integrity passes; M1/M2 dataset SHA pairing passes; final `integrity_pass=True`.

## 4. Primary operating characteristics
| Cell | Spec | Type-I / Power | Coverage | Mean estimate | Bias | Singular | Calibration status |
|---|---:|---:|---:|---:|---:|---:|---|
| P7_A_NULL_RHO0 | M1 | 6.6% | 93.4% | 0.000265 | 0.000265 | 90.0% | PASS |
| P7_A_NULL_RHO0 | M2 | 7.2% | 92.8% | 0.000351 | 0.000351 | 85.6% | FAIL |
| P7_B_NULL_RHO30 | M1 | 6.4% | 93.6% | 0.000191 | 0.000191 | 87.0% | PASS |
| P7_B_NULL_RHO30 | M2 | 7.4% | 92.6% | 0.000277 | 0.000277 | 83.8% | FAIL |
| P7_C_EFFECT_RHO0 | M1 | 99.6% | 94.2% | 0.100405 | 0.000405 | 89.2% | Coverage PASS |
| P7_C_EFFECT_RHO0 | M2 | 99.8% | 93.4% | 0.100485 | 0.000485 | 83.6% | Coverage PASS |
| P7_D_EFFECT_RHO30 | M1 | 99.6% | 94.2% | 0.100415 | 0.000415 | 88.6% | Coverage PASS |
| P7_D_EFFECT_RHO30 | M2 | 99.6% | 93.8% | 0.100490 | 0.000490 | 82.8% | Coverage PASS |

### Null calibration
- M1, rho=0: Type-I 6.6% (exact p=0.1007); coverage 93.4% (p=0.1007).
- M1, rho=.30: Type-I 6.4% (p=0.1504); coverage 93.6% (p=0.1504).
- M2, rho=0: Type-I 7.2% (p=0.0305); coverage 92.8% (p=0.0305).
- M2, rho=.30: Type-I 7.4% (p=0.0179); coverage 92.6% (p=0.0179).

## 5. Architecture decision
The locked rule states that if only one architecture demonstrates acceptable null calibration and confidence-interval coverage across both tested covariance-generating conditions, that architecture becomes the candidate for the prospective design. M1 passes those screens in both rho conditions; M2 fails them in both rho conditions. Therefore **M1 is the Phase 7 candidate architecture and M2 is not promoted.**

This wording is deliberately limited: the result is **no statistically detected departure from nominal calibration at resolution N=500 under the tested DGP**, not an equivalence proof and not a universal guarantee.

## 6. Effect recovery and power
- P7_C_EFFECT_RHO0 M1: mean estimate=0.100405; bias=0.000405; relative bias=0.405%; rejection rate=99.6%; coverage=94.2%.
- P7_C_EFFECT_RHO0 M2: mean estimate=0.100485; bias=0.000485; relative bias=0.485%; rejection rate=99.8%; coverage=93.4%.
- P7_D_EFFECT_RHO30 M1: mean estimate=0.100415; bias=0.000415; relative bias=0.415%; rejection rate=99.6%; coverage=94.2%.
- P7_D_EFFECT_RHO30 M2: mean estimate=0.100490; bias=0.000490; relative bias=0.490%; rejection rate=99.6%; coverage=93.8%.
Power is reported because it was prespecified, but it does not determine architecture validity.

## 7. Paired M1/M2 diagnostics
| Cell | Mean estimate diff (M2-M1) | Mean SE diff | M1 singular | M2 singular |
|---|---:|---:|---:|---:|
| P7_A_NULL_RHO0 | 0.000086 | -0.000346 | 90.0% | 85.6% |
| P7_B_NULL_RHO30 | 0.000086 | -0.000368 | 87.0% | 83.8% |
| P7_C_EFFECT_RHO0 | 0.000081 | -0.000379 | 89.2% | 83.6% |
| P7_D_EFFECT_RHO30 | 0.000075 | -0.000356 | 88.6% | 82.8% |
The paired fixed-effect differences are tiny, while singularity remains frequent in both architectures. M2 reduces singularity somewhat but does not satisfy the locked null calibration screen. The architecture decision therefore follows calibration, not warning count or singularity frequency.

## 8. Limitations
- The conclusions are conditional on the locked Phase 7 DGP, information scale, effect sizes, random-effects magnitudes, and software implementation.
- High singularity remains a structural warning about random-effect identifiability even though M1 fixed-effect operating characteristics passed the prespecified screen.
- Exact-binomial nonrejection is not evidence of equivalence; it means no departure was detected at the chosen Monte Carlo resolution.
- Phase 7 is a simulation validation study. It does not establish that the scientific Self effect exists in live model data.
- Adoption of M1 for a confirmatory study requires a new prospective preregistration if it differs from the frozen v8.6.3 Gate 5 estimator.

## 9. Reproducibility
Frozen source SHA-256 values:
- `cce97faba969a6da873d9a5a34d9da6421fdf24d1a04df29c1a599fb3044e3d0  phase7_results.csv`
- `e77755e76a3fa75ed8a130e578b864af75ca2b42a614f84306bc9b097f5e605e  phase7_summary.csv`
- `17c16f1279a72f2916a97544586e7a6095699281a3a21bcdfd3c0b21735ff1eb  phase7_paired.csv`
- `9ee3720597b35c553f0b3dd7a6f2ca159b904609b171cd41b4f0800ab2f8eae2  phase7_blocks_manifest.csv`
- `ae92741d95ce01c46b7b197cc7d18386a3ab87494fdf2c1f506682b270b6c318  phase7_integrity_report.txt`
- `7c33848597dd1fd928b600369ccf2ce11b483eeeedbf97f0e62b66ee8fcfce0d  phase7_design_lock.md`
- `1f9192b4e1f0d9bf21b90191165f2b83c7c0a8286856dd7e6d105a2f737717fe  phase7_inferential_validation_runner.py`
- `ac3f128af92a10fbdb1ca627a9f0e6af0ac032a6587155a47f6dc8280f187530  phase7_glmer_fit.R`
- `5aec0011ee756d7b3657ff07f733cd58170d5b3f2076332ed5d05c404f7a7de2  phase7_aggregate.py`

## 10. Release contents
The accompanying bundle contains the report source and PDF, the fresh final aggregate outputs, the frozen Phase 7 source files, all ten production block result/manifests, the documented recovery incident, and a release manifest with SHA-256 hashes.
