"""
Design Lab: confounding-scenario generator for the hierarchical logistic
Gate 5 replacement simulation.

STATUS: observational confounding stress test. One selected condition per
model-item row (IsSelf assignment is itself a function of model scale),
NOT the original paired self/control structure. This tests whether
adjustment for scale survives selection-induced confounding; it does not
replace a paired-condition simulation. This generator, and everything it
produces, belongs to the new Design Lab / future preregistration and must
never be merged into the frozen v8.6.3 materials.

--------------------------------------------------------------------------
EFFECT-SCALE NOTE (read before interpreting any results from this file)
--------------------------------------------------------------------------
- `true_effect` is a LOG-ODDS increment, added directly to the linear
  predictor as `true_effect * is_self`. It is NOT a probability-point
  effect. true_effect = 0.10 corresponds to an odds ratio of
  exp(0.10) ~= 1.105, i.e. roughly a 10.5% increase in the odds of
  y=1, not "+10 percentage points". Do not label this an "MDE of 0.15"
  in any probability sense without restating it as an odds ratio
  (exp(0.15) ~= 1.162) or converting via the local slope of the logistic
  curve at the relevant baseline probability.
- `beta0 = 0.50` is a logit intercept. Baseline probability at X=0,
  context=0, is_self=0, and zero random effects is
  1 / (1 + exp(-0.50)) ~= 0.6225, not 0.50. This is an intentional,
  documented modeling choice (asymmetric baseline), not a bug.
--------------------------------------------------------------------------

Scale is model-level: X_j = log10(active parameters_j), centered across
the sampled portfolio of models. ContextLen is a separate item-level
covariate. IsSelf assignment is made to correlate with X_j at a target
level via a calibrated logistic selection mechanism.

Outcome model:
    logit(p_ij) = b0 + bX*X_j + b3*IsSelf_ij + bC*ContextLen_ij
                  + b0j + b0i + u1j*IsSelf_ij

    (b0j, u1j) ~ N(0, Sigma),  Sigma = [[tau_model^2, rho_model*tau_model*slope_sd],
                                          [rho_model*tau_model*slope_sd, slope_sd^2]]
        model random intercept b0j and model-specific IsSelf slope u1j,
        drawn jointly (Cholesky) so their correlation matches the fitted
        (1 + is_self | model_id) term; rho_model=0 recovers independence.
    b0i  ~ N(0, tau_item^2)    item random intercept

Fitted model (companion R side, see glmer_fit.R):
    y ~ X + context_len + is_self + (1 | item_id) + (1 + is_self | model_id)
"""

import itertools
import os
import numpy as np
import pandas as pd
from scipy.optimize import brentq


def calibrate_gamma_x(X_by_row, target_corr, a=0.0, gamma_z=0.0, Z=None,
                       seed=0, mc_reps=5):
    """
    Find gamma_X such that the expected row-level correlation between
    X_j (broadcast to rows) and the IsSelf assignment matches target_corr,
    holding intercept a and gamma_Z fixed. Solved by bisection over a
    Monte-Carlo-averaged objective since there's no closed form once an
    item-level selection variable Z is included.

    FIX (common random numbers): a single (mc_reps x n_rows) uniform
    matrix is pre-drawn once, before brentq starts, and reused for every
    candidate gamma_x. Assignment is is_self = (U < p(gamma_x)) rather
    than a fresh rng.binomial() draw per evaluation. This makes
    realized_corr(gamma_x) a deterministic, monotonic function of
    gamma_x (same underlying uniforms, only the threshold surface p
    moves), so brentq sees a reproducible, well-behaved objective
    instead of a different Monte Carlo function on every call.
    """
    if target_corr == 0.0:
        return 0.0

    rng = np.random.default_rng(seed)
    n_rows = X_by_row.shape[0]
    U = rng.uniform(size=(mc_reps, n_rows))  # fixed draws, shared across all evaluations

    def realized_corr(gamma_x):
        logits = a + gamma_x * X_by_row
        if gamma_z != 0.0 and Z is not None:
            logits = logits + gamma_z * Z
        p = 1 / (1 + np.exp(-logits))
        vals = []
        for r in range(mc_reps):
            is_self = (U[r] < p).astype(int)
            if is_self.std() == 0 or X_by_row.std() == 0:
                vals.append(0.0)
            else:
                vals.append(np.corrcoef(X_by_row, is_self)[0, 1])
        return np.mean(vals)

    def objective(gamma_x):
        return realized_corr(gamma_x) - target_corr

    lo, hi = -8.0, 8.0
    return brentq(objective, lo, hi, xtol=1e-3)


def overlap_diagnostics(p_assign, low=0.05, high=0.95):
    """
    Positivity/overlap check on IsSelf assignment propensities. At
    r=.6 with small portfolios, near-separation is expected; flag it
    explicitly so a downstream convergence failure or bias spike can be
    attributed to lack of overlap rather than a broken scale adjustment.
    """
    return {
        "p_min": float(p_assign.min()),
        "p_max": float(p_assign.max()),
        "pct_below_low": float((p_assign < low).mean()),
        "pct_above_high": float((p_assign > high).mean()),
        "near_separation": bool(
            (p_assign < low).mean() > 0.10 or (p_assign > high).mean() > 0.10
        ),
    }


def generate_scenario(
    n_models,
    n_items,
    target_corr,
    true_effect,         # LOG-ODDS increment — see EFFECT-SCALE NOTE above
    slope_sd=0.02,
    tau_model=0.03,
    tau_item=0.03,
    rho_model=0.0,         # correlation between model intercept b0_model and
                            # model IsSelf slope u1_model; matches the fitted
                            # (1 + is_self | model_id) correlated random-effect term
    beta0=0.50,           # logit intercept -> baseline p ~= 0.6225, documented above
    beta_x=0.15,          # PLACEHOLDER — calibrate to a defensible magnitude
    beta_c=0.05,          # PLACEHOLDER — same
    context_sd=1.0,
    gamma_z=0.0,           # optional item-level selection covariate, off by default
    param_log10_range=(9.0, 12.0),  # ~1B to ~1T active params
    seed=0,
):
    rng = np.random.default_rng(seed)

    # Model-level scale: log10(active params), centered across the
    # sampled portfolio.
    log10_params = rng.uniform(*param_log10_range, size=n_models)
    X_j = log10_params - log10_params.mean()

    # Item-level context-length covariate, standardized.
    context_i = rng.normal(0, context_sd, size=n_items)

    # Optional item-level selection covariate (inert unless gamma_z != 0).
    Z_i = rng.normal(0, 1, size=n_items) if gamma_z != 0.0 else None

    model_idx, item_idx = np.meshgrid(
        np.arange(n_models), np.arange(n_items), indexing="ij"
    )
    model_idx, item_idx = model_idx.ravel(), item_idx.ravel()
    X_row = X_j[model_idx]
    Z_row = Z_i[item_idx] if Z_i is not None else None

    gamma_x = calibrate_gamma_x(
        X_row, target_corr, gamma_z=gamma_z, Z=Z_row, seed=seed
    )

    assign_logit = gamma_x * X_row
    if gamma_z != 0.0:
        assign_logit = assign_logit + gamma_z * Z_row
    p_assign = 1 / (1 + np.exp(-assign_logit))
    is_self = rng.binomial(1, p_assign)

    # FIX (aligned random-effects structure): the fitted model uses
    # (1 + is_self | model_id), which estimates a correlation between the
    # model intercept and the model-specific IsSelf slope. Generate them
    # jointly from a bivariate normal via Cholesky decomposition so the
    # generator actually has the correlation structure the fitted model
    # is trying to recover (rho_model defaults to 0.0, i.e. independent,
    # but is a first-class knob for the Design Lab grid).
    Sigma = np.array([
        [tau_model ** 2,                   rho_model * tau_model * slope_sd],
        [rho_model * tau_model * slope_sd, slope_sd ** 2],
    ])
    L = np.linalg.cholesky(Sigma)
    z = rng.normal(0, 1, size=(n_models, 2))
    model_effects = z @ L.T
    b0_model = model_effects[:, 0]
    u1_model = model_effects[:, 1]

    b0_item = rng.normal(0, tau_item, size=n_items)

    diagnostics = overlap_diagnostics(p_assign)
    diagnostics["realized_corr"] = float(np.corrcoef(X_row, is_self)[0, 1])
    diagnostics["gamma_x"] = float(gamma_x)
    diagnostics["rho_model_target"] = float(rho_model)
    if n_models > 2 and b0_model.std() > 0 and u1_model.std() > 0:
        diagnostics["rho_model_realized"] = float(
            np.corrcoef(b0_model, u1_model)[0, 1]
        )
    else:
        diagnostics["rho_model_realized"] = float("nan")

    context_row = context_i[item_idx]

    logit_p = (
        beta0
        + beta_x * X_row
        + true_effect * is_self
        + beta_c * context_row
        + b0_model[model_idx]
        + b0_item[item_idx]
        + u1_model[model_idx] * is_self
    )
    p = 1 / (1 + np.exp(-logit_p))
    y = rng.binomial(1, p)

    return {
        "model_id": model_idx,
        "item_id": item_idx,
        "X": X_row,
        "context_len": context_row,
        "is_self": is_self,
        "y": y,
        "diagnostics": diagnostics,
    }


def scenario_to_dataframe(out):
    df = pd.DataFrame({
        "model_id": out["model_id"],
        "item_id": out["item_id"],
        "X": out["X"],
        "context_len": out["context_len"],
        "is_self": out["is_self"],
        "y": out["y"],
    })
    return df


# --------------------------------------------------------------------------
# Grid enumeration for the full sweep
# --------------------------------------------------------------------------

GRID_N_MODELS = [8, 12, 16, 20, 24]
GRID_N_ITEMS = [100, 150, 260]
GRID_TARGET_CORR = [0.0, 0.3, 0.6]
GRID_TRUE_EFFECT = [0.0, 0.05, 0.10, 0.15]   # log-odds increments, see note above
GRID_RHO_MODEL = [0.0]   # matches generate_scenario's default (independent
                          # intercept/slope); pass multiple values to sweep it


def enumerate_grid(n_models_list=GRID_N_MODELS,
                    n_items_list=GRID_N_ITEMS,
                    target_corr_list=GRID_TARGET_CORR,
                    true_effect_list=GRID_TRUE_EFFECT,
                    rho_model_list=GRID_RHO_MODEL,
                    n_reps=200,
                    base_seed=1000):
    """
    Yields one dict per (cell, replication): the full parameter set needed
    to reproduce a single generate_scenario() call, plus a unique cell_id
    and rep index so results can be regrouped for aggregation.

    Total cells = len(n_models_list) * len(n_items_list)
                  * len(target_corr_list) * len(true_effect_list)
                  * len(rho_model_list)
    With the default grid: 5 * 3 * 3 * 4 * 1 = 180 cells.
    Total simulated datasets = cells * n_reps (180 * 200 = 36,000 by default
    — budget R runtime accordingly; see run_grid.py for batching notes).
    """
    cell_id = 0
    for n_models, n_items, target_corr, true_effect, rho_model in itertools.product(
        n_models_list, n_items_list, target_corr_list, true_effect_list, rho_model_list
    ):
        cell_id += 1
        for rep in range(n_reps):
            seed = base_seed + cell_id * 100000 + rep
            yield {
                "cell_id": cell_id,
                "rep": rep,
                "n_models": n_models,
                "n_items": n_items,
                "target_corr": target_corr,
                "true_effect": true_effect,
                "rho_model": rho_model,
                "seed": seed,
            }


def write_grid_manifest(path, **grid_kwargs):
    """Write the full job list (one row per cell x rep) to CSV for the driver."""
    rows = list(enumerate_grid(**grid_kwargs))
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return df


if __name__ == "__main__":
    # Smoke test: one cell, worst-case corner (small portfolio, high corr).
    out = generate_scenario(
        n_models=8, n_items=100, target_corr=0.6, true_effect=0.10, seed=1
    )
    print("single-cell diagnostics:", out["diagnostics"])

    manifest = write_grid_manifest(
        os.path.join(os.path.dirname(__file__), "grid_manifest.csv"),
        n_reps=5,  # small smoke value; use n_reps=200+ for the real sweep
    )
    print(f"grid manifest: {len(manifest)} jobs across "
          f"{manifest['cell_id'].nunique()} cells")
