#!/usr/bin/env python3
"""
PHASE 2B — Paired 2×2×2 Variance Factorial Diagnostic

Design Lab diagnostic work only.
DO NOT modify or merge into the frozen v8.6.3 preregistration.

Purpose
-------
Test whether singularity/boundary behavior reflects joint weak
identifiability of the M1 random-effects structure rather than one
variance component in isolation.

M1:
    y ~ X + context_len + is_self
        + (1 | item_id)
        + (1 + is_self | model_id)

Fixed:
    n_models    = 24
    n_items     = 100
    target_corr = 0.60
    true_effect = 0.10 log-odds
    rho_model   = 0.30
    reps        = 20 paired seed blocks

Factorial:
    slope_sd  ∈ {0.02, 0.10}
    tau_model ∈ {0.03, 0.15}
    tau_item  ∈ {0.03, 0.15}

8 conditions × 20 paired seed blocks = 160 fits.

Pairing rule
------------
Within each replication block, ALL eight conditions use the SAME seed.
This creates common-random-number pairing across the diagnostic
conditions. It does not make the generated datasets identical; the DGP
parameters differ by condition.

Seeds are diagnostic only and separate from any confirmatory schedule.
"""

from pathlib import Path
import importlib.util
import itertools
import json
import math
import subprocess
import traceback

import numpy as np
import pandas as pd


DESIGNLAB = Path("/content/drive/MyDrive/DesignLab")
GENERATOR_PATH = DESIGNLAB / "confound_generator.py"
R_FIT_PATH = DESIGNLAB / "glmer_fit.R"

RESULTS_PATH = DESIGNLAB / "phase2b_results.csv"
SUMMARY_PATH = DESIGNLAB / "phase2b_summary.csv"
PAIRED_PATH = DESIGNLAB / "phase2b_paired_transitions.csv"

WORKDIR = DESIGNLAB / "_phase2b_work"
WORKDIR.mkdir(parents=True, exist_ok=True)

N_MODELS = 24
N_ITEMS = 100
TARGET_CORR = 0.60
TRUE_EFFECT = 0.10
RHO_MODEL = 0.30
N_REPS = 20

# Diagnostic namespace only.
BASE_SEED = 92619000

SLOPE_LEVELS = [0.02, 0.10]
MODEL_LEVELS = [0.03, 0.15]
ITEM_LEVELS = [0.03, 0.15]

CONDITIONS = []
for slope_sd, tau_model, tau_item in itertools.product(
    SLOPE_LEVELS, MODEL_LEVELS, ITEM_LEVELS
):
    label = (
        f"s{str(slope_sd).replace('.', 'p')}_"
        f"m{str(tau_model).replace('.', 'p')}_"
        f"i{str(tau_item).replace('.', 'p')}"
    )
    CONDITIONS.append({
        "condition": label,
        "slope_sd": slope_sd,
        "tau_model": tau_model,
        "tau_item": tau_item,
    })

EXPECTED_FITS = len(CONDITIONS) * N_REPS


def load_generator():
    if not GENERATOR_PATH.exists():
        raise FileNotFoundError(f"Missing generator: {GENERATOR_PATH}")
    spec = importlib.util.spec_from_file_location(
        "phase2b_confound_generator", GENERATOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("generate_scenario", "scenario_to_dataframe"):
        if not hasattr(module, name):
            raise AttributeError(f"Generator missing required function: {name}")
    return module


def finite_number(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def bool_or_nan(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str):
        x = value.strip().lower()
        if x == "true":
            return True
        if x == "false":
            return False
    return np.nan


def scalar_or_nan(value):
    if value is None:
        return np.nan
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def classify_boundary(fit):
    """
    Convenience first-match classification only.
    Raw component diagnostics remain authoritative.
    """
    singular = bool_or_nan(fit.get("singular"))
    if singular is False:
        return "non_singular"
    if singular is not True:
        return "unknown"

    slope = fit.get("model_slope_sd")
    corr = fit.get("model_intercept_slope_corr")
    model_int = fit.get("model_intercept_sd")
    item_int = fit.get("item_intercept_sd")

    if finite_number(slope) and float(slope) < 1e-4:
        return "model_slope_sd_zero"
    if finite_number(corr) and abs(float(corr)) >= 0.999:
        return "model_corr_boundary"
    if finite_number(model_int) and float(model_int) < 1e-4:
        return "model_intercept_sd_zero"
    if finite_number(item_int) and float(item_int) < 1e-4:
        return "item_intercept_sd_zero"
    return "other_boundary"


def run_r_fit(input_csv, output_json):
    p = subprocess.run(
        [
            "Rscript",
            str(R_FIT_PATH),
            str(input_csv),
            str(output_json),
            str(TRUE_EFFECT),
        ],
        text=True,
        capture_output=True,
    )
    if p.returncode != 0:
        err = (p.stderr or p.stdout or "").strip()
        raise RuntimeError(f"Rscript return code {p.returncode}: {err}")
    if not output_json.exists():
        raise RuntimeError("R returned 0 but JSON output was not created.")

    fit = json.loads(output_json.read_text())
    internal_error = fit.get("error")
    if internal_error not in (None, "", "null"):
        raise RuntimeError(f"GLMM internal error: {internal_error}")
    return fit, (p.stderr or "").strip()


def checkpoint(rows):
    pd.DataFrame(rows).to_csv(RESULTS_PATH, index=False)


def summarize(results):
    rows = []
    for cfg in CONDITIONS:
        g = results[results["condition"] == cfg["condition"]].copy()
        f = g[g["fit_error"].isna()].copy()

        def bmean(col):
            vals = f[col].map(
                lambda x: 1.0 if x is True else
                (0.0 if x is False else np.nan)
            )
            return vals.mean()

        slope = pd.to_numeric(f["model_slope_sd"], errors="coerce")
        mi = pd.to_numeric(f["model_intercept_sd"], errors="coerce")
        ii = pd.to_numeric(f["item_intercept_sd"], errors="coerce")
        corr = pd.to_numeric(
            f["model_intercept_slope_corr"], errors="coerce"
        )
        eig = pd.to_numeric(
            f["model_cov_min_eigenvalue"], errors="coerce"
        )
        est = pd.to_numeric(f["estimate"], errors="coerce")
        bias = pd.to_numeric(f["bias"], errors="coerce")

        rows.append({
            "condition": cfg["condition"],
            "slope_sd_true": cfg["slope_sd"],
            "tau_model_true": cfg["tau_model"],
            "tau_item_true": cfg["tau_item"],
            "n_attempted": len(g),
            "n_fitted": len(f),
            "n_fit_errors": int(g["fit_error"].notna().sum()),
            "convergence_rate": bmean("converged"),
            "singular_fit_rate": bmean("singular"),
            "n_singular": int(sum(x is True for x in f["singular"])),
            "slope_sd_lt_1e_4_rate":
                (slope < 1e-4).mean() if slope.notna().any() else np.nan,
            "model_sd_lt_1e_4_rate":
                (mi < 1e-4).mean() if mi.notna().any() else np.nan,
            "item_sd_lt_1e_4_rate":
                (ii < 1e-4).mean() if ii.notna().any() else np.nan,
            "corr_abs_ge_0_999_rate":
                (corr.abs() >= 0.999).mean()
                if corr.notna().any() else np.nan,
            "median_model_slope_sd": slope.median(),
            "median_model_intercept_sd": mi.median(),
            "median_item_intercept_sd": ii.median(),
            "median_abs_model_corr": corr.abs().median(),
            "median_model_cov_min_eigenvalue": eig.median(),
            "mean_estimate": est.mean(),
            "mean_bias": bias.mean(),
            "rejection_rate": bmean("rejected_at_05"),
            "ci_coverage_rate": bmean("ci_covers_truth"),
            "near_separation_rate": bmean("near_separation"),
        })
    return pd.DataFrame(rows)


def make_paired_transitions(results):
    """
    Wide paired diagnostic table: one row per seed/rep, with singularity
    and component-collapse indicators for all 8 conditions.
    """
    good = results[results["fit_error"].isna()].copy()

    good["singular_i"] = good["singular"].map(
        lambda x: 1 if x is True else (0 if x is False else np.nan)
    )
    for source, target in [
        ("model_slope_sd", "slope_zero_i"),
        ("model_intercept_sd", "model_zero_i"),
        ("item_intercept_sd", "item_zero_i"),
    ]:
        v = pd.to_numeric(good[source], errors="coerce")
        good[target] = np.where(v.notna(), (v < 1e-4).astype(int), np.nan)

    corr = pd.to_numeric(
        good["model_intercept_slope_corr"], errors="coerce"
    )
    good["corr_boundary_i"] = np.where(
        corr.notna(), (corr.abs() >= 0.999).astype(int), np.nan
    )

    metrics = [
        "singular_i",
        "slope_zero_i",
        "model_zero_i",
        "item_zero_i",
        "corr_boundary_i",
        "estimate",
        "bias",
    ]

    wide_parts = []
    base = good[["rep", "seed"]].drop_duplicates().sort_values("rep")

    for metric in metrics:
        p = good.pivot(index=["rep", "seed"], columns="condition", values=metric)
        p.columns = [f"{metric}__{c}" for c in p.columns]
        wide_parts.append(p)

    wide = pd.concat(wide_parts, axis=1).reset_index()
    return base.merge(wide, on=["rep", "seed"], how="left")


def main():
    print("============================================================")
    print("PHASE 2B — PAIRED 2x2x2 VARIANCE FACTORIAL")
    print("============================================================")
    print(f"Conditions: {len(CONDITIONS)}")
    print(f"Paired seed blocks: {N_REPS}")
    print(f"Expected GLMM fits: {EXPECTED_FITS}")
    print("M1 only; n_models=24; n_items=100")
    print("Same seed used across all 8 conditions within each rep.")
    print("Frozen v8.6.3 is NOT modified.")
    print()

    if not R_FIT_PATH.exists():
        raise FileNotFoundError(f"Missing R fitter: {R_FIT_PATH}")

    generator = load_generator()
    rows = []
    fit_index = 0

    # Rep outermost so all 8 conditions in a paired block share a seed.
    for rep in range(1, N_REPS + 1):
        seed = BASE_SEED + rep

        for cfg in CONDITIONS:
            fit_index += 1
            print(
                f"[{fit_index:03d}/{EXPECTED_FITS}] "
                f"rep={rep:02d} seed={seed} {cfg['condition']}",
                flush=True,
            )

            stem = f"rep{rep:02d}_seed{seed}_{cfg['condition']}"
            input_csv = WORKDIR / f"{stem}.csv"
            output_json = WORKDIR / f"{stem}.json"

            row = {
                "condition": cfg["condition"],
                "rep": rep,
                "seed": seed,
                "model_spec": "M1",
                "n_models": N_MODELS,
                "n_items": N_ITEMS,
                "target_corr": TARGET_CORR,
                "true_effect": TRUE_EFFECT,
                "rho_model_true": RHO_MODEL,
                "slope_sd_true": cfg["slope_sd"],
                "tau_model_true": cfg["tau_model"],
                "tau_item_true": cfg["tau_item"],
                "fit_error": None,
            }

            try:
                out = generator.generate_scenario(
                    n_models=N_MODELS,
                    n_items=N_ITEMS,
                    target_corr=TARGET_CORR,
                    true_effect=TRUE_EFFECT,
                    slope_sd=cfg["slope_sd"],
                    tau_model=cfg["tau_model"],
                    tau_item=cfg["tau_item"],
                    rho_model=RHO_MODEL,
                    seed=seed,
                )
                df = generator.scenario_to_dataframe(out)
                expected_rows = N_MODELS * N_ITEMS
                if len(df) != expected_rows:
                    raise RuntimeError(
                        f"Generator produced {len(df)} rows; "
                        f"expected {expected_rows}."
                    )
                df.to_csv(input_csv, index=False)

                diag = out.get("diagnostics", {}) or {}
                row.update({
                    "generated_rows": len(df),
                    "p_min": scalar_or_nan(diag.get("p_min")),
                    "p_max": scalar_or_nan(diag.get("p_max")),
                    "pct_below_low":
                        scalar_or_nan(diag.get("pct_below_low")),
                    "pct_above_high":
                        scalar_or_nan(diag.get("pct_above_high")),
                    "near_separation":
                        bool_or_nan(diag.get("near_separation")),
                    "realized_corr":
                        scalar_or_nan(diag.get("realized_corr")),
                    "gamma_x": scalar_or_nan(diag.get("gamma_x")),
                    "rho_model_target":
                        scalar_or_nan(diag.get("rho_model_target")),
                    "rho_model_realized":
                        scalar_or_nan(diag.get("rho_model_realized")),
                })

                fit, r_stderr = run_r_fit(input_csv, output_json)

                row.update({
                    "converged": bool_or_nan(fit.get("converged")),
                    "singular": bool_or_nan(fit.get("singular")),
                    "warnings": fit.get("warnings"),
                    "r_stderr": r_stderr,
                    "estimate": scalar_or_nan(fit.get("estimate")),
                    "se": scalar_or_nan(fit.get("se")),
                    "p_value": scalar_or_nan(fit.get("p_value")),
                    "ci_low": scalar_or_nan(fit.get("ci_low")),
                    "ci_high": scalar_or_nan(fit.get("ci_high")),
                    "rejected_at_05":
                        bool_or_nan(fit.get("rejected_at_05")),
                    "bias": scalar_or_nan(fit.get("bias")),
                    "ci_covers_truth":
                        bool_or_nan(fit.get("ci_covers_truth")),
                    "model_intercept_sd":
                        scalar_or_nan(fit.get("model_intercept_sd")),
                    "model_slope_sd":
                        scalar_or_nan(fit.get("model_slope_sd")),
                    "model_intercept_slope_corr":
                        scalar_or_nan(
                            fit.get("model_intercept_slope_corr")
                        ),
                    "item_intercept_sd":
                        scalar_or_nan(fit.get("item_intercept_sd")),
                    "model_cov_min_eigenvalue":
                        scalar_or_nan(
                            fit.get("model_cov_min_eigenvalue")
                        ),
                    "theta": json.dumps(fit.get("theta")),
                    "theta_lower": json.dumps(fit.get("theta_lower")),
                    "singular_component_reported":
                        fit.get("singular_component"),
                    "singular_component_reclassified":
                        classify_boundary(fit),
                })

            except Exception as exc:
                row["fit_error"] = f"{type(exc).__name__}: {exc}"
                row["traceback"] = traceback.format_exc(limit=4)

            rows.append(row)
            checkpoint(rows)

    results = pd.DataFrame(rows)
    summary = summarize(results)
    paired = make_paired_transitions(results)

    results.to_csv(RESULTS_PATH, index=False)
    summary.to_csv(SUMMARY_PATH, index=False)
    paired.to_csv(PAIRED_PATH, index=False)

    n_attempted = len(results)
    n_fitted = int(results["fit_error"].isna().sum())
    n_errors = int(results["fit_error"].notna().sum())

    print()
    print("============================================================")
    print("PHASE 2B FINAL VALIDATION")
    print("============================================================")
    print("Total rows:", n_attempted)
    print("Successful GLMM fits:", n_fitted)
    print("Fit errors:", n_errors)
    print()
    print(summary.to_string(index=False))
    print()

    if n_attempted != EXPECTED_FITS:
        raise RuntimeError(
            f"Expected {EXPECTED_FITS} rows, found {n_attempted}."
        )
    if n_fitted == 0:
        raise RuntimeError(
            f"{n_attempted} rows created but ZERO GLMM fits succeeded."
        )
    if n_errors != 0:
        raise RuntimeError(
            f"{n_errors}/{EXPECTED_FITS} fits failed. Inspect before rerun."
        )

    # Pairing integrity gate.
    counts = results.groupby(["rep", "seed"])["condition"].nunique()
    if len(counts) != N_REPS or not (counts == len(CONDITIONS)).all():
        raise RuntimeError("PAIRING INTEGRITY FAILED.")

    seed_per_rep = results.groupby("rep")["seed"].nunique()
    if not (seed_per_rep == 1).all():
        raise RuntimeError("PAIRING INTEGRITY FAILED: >1 seed within a rep.")

    print("============================================================")
    print(f"PHASE 2B COMPLETE: {n_fitted}/{EXPECTED_FITS} fits succeeded.")
    print("Pairing integrity: PASS")
    print("Upload these THREE files to ChatGPT:")
    print(f"1. {RESULTS_PATH.name}")
    print(f"2. {SUMMARY_PATH.name}")
    print(f"3. {PAIRED_PATH.name}")
    print("Do not modify frozen v8.6.3.")
    print("============================================================")


if __name__ == "__main__":
    main()
