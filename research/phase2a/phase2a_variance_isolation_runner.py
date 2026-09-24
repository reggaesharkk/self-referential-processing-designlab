#!/usr/bin/env python3
"""
PHASE 2A — Variance Component Isolation Diagnostic

Purpose
-------
Diagnose which small DGP random-effect component is associated with the
near-universal singular fits observed in Phase 1.

This is Design Lab diagnostic work only.
It MUST NOT modify or be merged into the frozen v8.6.3 preregistration.

Design
------
M1 only:
    y ~ X + context_len + is_self
        + (1 | item_id)
        + (1 + is_self | model_id)

Fixed across conditions:
    n_models    = 24
    n_items     = 100
    target_corr = 0.60
    true_effect = 0.10 log-odds
    rho_model   = 0.30
    reps        = 30

Conditions:
    baseline : slope_sd=.02, tau_model=.03, tau_item=.03
    slope_up : slope_sd=.10, tau_model=.03, tau_item=.03
    model_up : slope_sd=.02, tau_model=.15, tau_item=.03
    item_up  : slope_sd=.02, tau_model=.03, tau_item=.15

Total: 4 * 30 = 120 fits.

Important
---------
Each condition/replication receives its own deterministic seed.
No confirmatory seed schedule is used.
The original generator and glmer_fit.R are read/called, not modified.
"""

from pathlib import Path
import importlib.util
import json
import math
import subprocess
import sys
import traceback

import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

DESIGNLAB = Path("/content/drive/MyDrive/DesignLab")

GENERATOR_PATH = DESIGNLAB / "confound_generator.py"
R_FIT_PATH = DESIGNLAB / "glmer_fit.R"

RESULTS_PATH = DESIGNLAB / "phase2a_results.csv"
SUMMARY_PATH = DESIGNLAB / "phase2a_summary.csv"

WORKDIR = DESIGNLAB / "_phase2a_work"
WORKDIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOCKED PHASE 2A DESIGN
# ============================================================

N_MODELS = 24
N_ITEMS = 100
TARGET_CORR = 0.60
TRUE_EFFECT = 0.10
RHO_MODEL = 0.30
N_REPS = 30

# Diagnostic seed namespace only — NOT confirmatory seeds.
BASE_SEED = 92618000

CONDITIONS = [
    {
        "condition": "baseline",
        "slope_sd": 0.02,
        "tau_model": 0.03,
        "tau_item": 0.03,
    },
    {
        "condition": "slope_up",
        "slope_sd": 0.10,
        "tau_model": 0.03,
        "tau_item": 0.03,
    },
    {
        "condition": "model_up",
        "slope_sd": 0.02,
        "tau_model": 0.15,
        "tau_item": 0.03,
    },
    {
        "condition": "item_up",
        "slope_sd": 0.02,
        "tau_model": 0.03,
        "tau_item": 0.15,
    },
]

EXPECTED_FITS = len(CONDITIONS) * N_REPS


# ============================================================
# HELPERS
# ============================================================

def load_generator():
    if not GENERATOR_PATH.exists():
        raise FileNotFoundError(f"Missing generator: {GENERATOR_PATH}")

    spec = importlib.util.spec_from_file_location(
        "phase2a_confound_generator",
        GENERATOR_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for name in ("generate_scenario", "scenario_to_dataframe"):
        if not hasattr(module, name):
            raise AttributeError(
                f"{GENERATOR_PATH.name} does not expose required function: {name}"
            )

    return module


def scalar_or_nan(value):
    if value is None:
        return np.nan
    if isinstance(value, bool):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def bool_or_nan(value):
    if value is None:
        return np.nan
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str):
        x = value.strip().lower()
        if x == "true":
            return True
        if x == "false":
            return False
    return np.nan


def finite_number(value):
    try:
        x = float(value)
        return math.isfinite(x)
    except (TypeError, ValueError):
        return False


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
    if finite_number(corr) and abs(float(corr)) > 0.999:
        return "model_corr_boundary"
    if finite_number(model_int) and float(model_int) < 1e-4:
        return "model_intercept_sd_zero"
    if finite_number(item_int) and float(item_int) < 1e-4:
        return "item_intercept_sd_zero"
    return "other_boundary"


def run_r_fit(input_csv, output_json):
    cmd = [
        "Rscript",
        str(R_FIT_PATH),
        str(input_csv),
        str(output_json),
        str(TRUE_EFFECT),
    ]

    p = subprocess.run(cmd, text=True, capture_output=True)

    if p.returncode != 0:
        err = (p.stderr or p.stdout or "").strip()
        raise RuntimeError(
            f"Rscript return code {p.returncode}: {err}"
        )

    if not output_json.exists():
        raise RuntimeError("Rscript returned 0 but did not create JSON output.")

    fit = json.loads(output_json.read_text())

    internal_error = fit.get("error")
    if internal_error not in (None, "", "null"):
        raise RuntimeError(f"GLMM internal error: {internal_error}")

    return fit, (p.stderr or "").strip()


def write_checkpoint(rows):
    pd.DataFrame(rows).to_csv(RESULTS_PATH, index=False)


def rate(series):
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() == 0:
        return np.nan
    return float(s.mean())


def summarize(results):
    summaries = []

    for cond in [c["condition"] for c in CONDITIONS]:
        g = results.loc[results["condition"] == cond].copy()

        fitted = g.loc[g["fit_error"].isna()].copy()
        singular_bool = fitted["singular"].map(
            lambda x: 1.0 if x is True else (0.0 if x is False else np.nan)
        )
        conv_bool = fitted["converged"].map(
            lambda x: 1.0 if x is True else (0.0 if x is False else np.nan)
        )

        corr = pd.to_numeric(
            fitted["model_intercept_slope_corr"], errors="coerce"
        )
        slope = pd.to_numeric(fitted["model_slope_sd"], errors="coerce")
        model_int = pd.to_numeric(
            fitted["model_intercept_sd"], errors="coerce"
        )
        item_int = pd.to_numeric(
            fitted["item_intercept_sd"], errors="coerce"
        )
        eig = pd.to_numeric(
            fitted["model_cov_min_eigenvalue"], errors="coerce"
        )
        est = pd.to_numeric(fitted["estimate"], errors="coerce")
        bias = pd.to_numeric(fitted["bias"], errors="coerce")
        reject = fitted["rejected_at_05"].map(
            lambda x: 1.0 if x is True else (0.0 if x is False else np.nan)
        )
        cover = fitted["ci_covers_truth"].map(
            lambda x: 1.0 if x is True else (0.0 if x is False else np.nan)
        )
        near_sep = fitted["near_separation"].map(
            lambda x: 1.0 if x is True else (0.0 if x is False else np.nan)
        )

        summaries.append({
            "condition": cond,
            "n_models": int(g["n_models"].iloc[0]),
            "n_items": int(g["n_items"].iloc[0]),
            "slope_sd_true": float(g["slope_sd_true"].iloc[0]),
            "tau_model_true": float(g["tau_model_true"].iloc[0]),
            "tau_item_true": float(g["tau_item_true"].iloc[0]),
            "n_attempted": len(g),
            "n_fitted": len(fitted),
            "n_fit_errors": int(g["fit_error"].notna().sum()),
            "convergence_rate": conv_bool.mean(),
            "singular_fit_rate": singular_bool.mean(),
            "n_singular": int((singular_bool == 1).sum()),
            "corr_abs_ge_0_999_rate": (
                (corr.abs() >= 0.999).mean() if corr.notna().any() else np.nan
            ),
            "slope_sd_lt_1e_4_rate": (
                (slope < 1e-4).mean() if slope.notna().any() else np.nan
            ),
            "model_sd_lt_1e_4_rate": (
                (model_int < 1e-4).mean()
                if model_int.notna().any() else np.nan
            ),
            "item_sd_lt_1e_4_rate": (
                (item_int < 1e-4).mean()
                if item_int.notna().any() else np.nan
            ),
            "median_model_slope_sd": slope.median(),
            "median_model_intercept_sd": model_int.median(),
            "median_item_intercept_sd": item_int.median(),
            "median_abs_model_corr": corr.abs().median(),
            "median_model_cov_min_eigenvalue": eig.median(),
            "mean_estimate": est.mean(),
            "mean_bias": bias.mean(),
            "rejection_rate": reject.mean(),
            "ci_coverage_rate": cover.mean(),
            "near_separation_rate": near_sep.mean(),
        })

    return pd.DataFrame(summaries)


# ============================================================
# MAIN
# ============================================================

def main():
    print("============================================================")
    print("PHASE 2A — VARIANCE COMPONENT ISOLATION")
    print("============================================================")
    print(f"Expected fits: {EXPECTED_FITS}")
    print("M1 only; 24 models; 100 items; 30 reps/condition")
    print("Frozen v8.6.3 files are NOT modified.")
    print()

    if not R_FIT_PATH.exists():
        raise FileNotFoundError(f"Missing R fitter: {R_FIT_PATH}")

    generator = load_generator()

    rows = []
    fit_index = 0

    for condition_index, cfg in enumerate(CONDITIONS):
        for rep in range(1, N_REPS + 1):
            fit_index += 1

            # Unique deterministic diagnostic seed.
            seed = BASE_SEED + condition_index * 1000 + rep

            label = (
                f"[{fit_index:03d}/{EXPECTED_FITS}] "
                f"{cfg['condition']} rep={rep:02d} seed={seed}"
            )
            print(label, flush=True)

            input_csv = WORKDIR / (
                f"{cfg['condition']}_rep{rep:02d}_seed{seed}.csv"
            )
            output_json = WORKDIR / (
                f"{cfg['condition']}_rep{rep:02d}_seed{seed}.json"
            )

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
                    "pct_below_low": scalar_or_nan(
                        diag.get("pct_below_low")
                    ),
                    "pct_above_high": scalar_or_nan(
                        diag.get("pct_above_high")
                    ),
                    "near_separation": bool_or_nan(
                        diag.get("near_separation")
                    ),
                    "realized_corr": scalar_or_nan(
                        diag.get("realized_corr")
                    ),
                    "gamma_x": scalar_or_nan(diag.get("gamma_x")),
                    "rho_model_target": scalar_or_nan(
                        diag.get("rho_model_target")
                    ),
                    "rho_model_realized": scalar_or_nan(
                        diag.get("rho_model_realized")
                    ),
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
                    "rejected_at_05": bool_or_nan(
                        fit.get("rejected_at_05")
                    ),
                    "bias": scalar_or_nan(fit.get("bias")),
                    "ci_covers_truth": bool_or_nan(
                        fit.get("ci_covers_truth")
                    ),
                    "model_intercept_sd": scalar_or_nan(
                        fit.get("model_intercept_sd")
                    ),
                    "model_slope_sd": scalar_or_nan(
                        fit.get("model_slope_sd")
                    ),
                    "model_intercept_slope_corr": scalar_or_nan(
                        fit.get("model_intercept_slope_corr")
                    ),
                    "item_intercept_sd": scalar_or_nan(
                        fit.get("item_intercept_sd")
                    ),
                    "model_cov_min_eigenvalue": scalar_or_nan(
                        fit.get("model_cov_min_eigenvalue")
                    ),
                    "theta": json.dumps(fit.get("theta")),
                    "theta_lower": json.dumps(fit.get("theta_lower")),
                    "singular_component_reported": fit.get(
                        "singular_component"
                    ),
                    "singular_component_reclassified":
                        classify_boundary(fit),
                })

            except Exception as exc:
                row["fit_error"] = f"{type(exc).__name__}: {exc}"
                row["traceback"] = traceback.format_exc(limit=4)

            rows.append(row)
            write_checkpoint(rows)

    results = pd.DataFrame(rows)
    summary = summarize(results)

    results.to_csv(RESULTS_PATH, index=False)
    summary.to_csv(SUMMARY_PATH, index=False)

    n_attempted = len(results)
    n_fitted = int(results["fit_error"].isna().sum())
    n_errors = int(results["fit_error"].notna().sum())

    print()
    print("============================================================")
    print("PHASE 2A FINAL VALIDATION")
    print("============================================================")
    print("Total rows:", n_attempted)
    print("Successful GLMM fits:", n_fitted)
    print("Fit errors:", n_errors)
    print()
    print(summary.to_string(index=False))
    print()

    if n_attempted != EXPECTED_FITS:
        raise RuntimeError(
            f"PHASE 2A FAILED: expected {EXPECTED_FITS} rows, "
            f"found {n_attempted}."
        )

    if n_fitted == 0:
        raise RuntimeError(
            f"PHASE 2A FAILED: {n_attempted} rows were created "
            "but ZERO GLMM fits succeeded."
        )

    if n_errors != 0:
        raise RuntimeError(
            f"PHASE 2A INCOMPLETE: {n_errors}/{EXPECTED_FITS} fits "
            "failed. Inspect results before interpretation."
        )

    print("============================================================")
    print(f"PHASE 2A COMPLETE: {n_fitted}/{EXPECTED_FITS} fits succeeded.")
    print("Upload these files to ChatGPT:")
    print(f"1. {RESULTS_PATH.name}")
    print(f"2. {SUMMARY_PATH.name}")
    print("Do not modify the frozen v8.6.3 preregistration.")
    print("============================================================")


if __name__ == "__main__":
    main()
