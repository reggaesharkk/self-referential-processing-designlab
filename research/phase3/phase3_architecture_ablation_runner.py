#!/usr/bin/env python3
"""
PHASE 3 — RANDOM-EFFECTS ARCHITECTURE ABLATION
==============================================

Design Lab diagnostic work only.
DO NOT modify, overwrite, or merge into frozen OSF preregistration v8.6.3.

Scientific question
-------------------
Phase 1 and Phase 2 showed that:
  * optimizer convergence is not the main problem;
  * increasing cluster count alone does not remove singularity;
  * removing the model intercept/slope correlation alone does not remove it;
  * increasing individual DGP variance scales improves recovery of some
    components but does not eliminate the dominant singularity pattern.

Phase 3 therefore changes the FITTED random-effects architecture while holding
the generated dataset fixed within each replication.

Baseline DGP (held fixed)
-------------------------
n_models    = 24
n_items     = 100
target_corr = 0.60
true_effect = 0.10 log-odds
slope_sd    = 0.02
tau_model   = 0.03
tau_item    = 0.03
rho_model   = 0.30

Architectures
-------------
M1_FULL_CORR:
    y ~ X + context_len + is_self
      + (1 | item_id)
      + (1 + is_self | model_id)

M2_FULL_UNCORR:
    y ~ X + context_len + is_self
      + (1 | item_id)
      + (1 + is_self || model_id)

M3_NO_SLOPE:
    y ~ X + context_len + is_self
      + (1 | item_id)
      + (1 | model_id)

M4_ITEM_ONLY:
    y ~ X + context_len + is_self
      + (1 | item_id)

M5_MODEL_SLOPE_ONLY:
    y ~ X + context_len + is_self
      + (1 + is_self | model_id)

Pairing
-------
For each replication, the generator is called ONCE. The exact same CSV is then
fit by all five architectures. Thus architecture comparisons are paired.

Run modes
---------
    python phase3_architecture_ablation_runner.py --preflight
        1 generated dataset × 5 architectures = 5 fits

    python phase3_architecture_ablation_runner.py --full
        30 generated datasets × 5 architectures = 150 fits

The runner creates temporary R fitters in _phase3_work and never modifies
glmer_fit.R.
"""

from pathlib import Path
import argparse
import importlib.util
import json
import math
import re
import subprocess
import traceback

import numpy as np
import pandas as pd


DESIGNLAB = Path("/content/drive/MyDrive/DesignLab")
GENERATOR_PATH = DESIGNLAB / "confound_generator.py"
SOURCE_R_PATH = DESIGNLAB / "glmer_fit.R"
WORKDIR = DESIGNLAB / "_phase3_work"
WORKDIR.mkdir(parents=True, exist_ok=True)

BASE_SEED = 92620000

# Fixed baseline DGP.
N_MODELS = 24
N_ITEMS = 100
TARGET_CORR = 0.60
TRUE_EFFECT = 0.10
SLOPE_SD = 0.02
TAU_MODEL = 0.03
TAU_ITEM = 0.03
RHO_MODEL = 0.30

ARCHITECTURES = [
    {
        "model_spec": "M1_FULL_CORR",
        "formula": "y ~ X + context_len + is_self + (1 | item_id) + (1 + is_self | model_id)",
    },
    {
        "model_spec": "M2_FULL_UNCORR",
        "formula": "y ~ X + context_len + is_self + (1 | item_id) + (1 + is_self || model_id)",
    },
    {
        "model_spec": "M3_NO_SLOPE",
        "formula": "y ~ X + context_len + is_self + (1 | item_id) + (1 | model_id)",
    },
    {
        "model_spec": "M4_ITEM_ONLY",
        "formula": "y ~ X + context_len + is_self + (1 | item_id)",
    },
    {
        "model_spec": "M5_MODEL_SLOPE_ONLY",
        "formula": "y ~ X + context_len + is_self + (1 + is_self | model_id)",
    },
]


def load_generator():
    if not GENERATOR_PATH.exists():
        raise FileNotFoundError(f"Missing generator: {GENERATOR_PATH}")
    spec = importlib.util.spec_from_file_location("phase3_generator", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for fn in ("generate_scenario", "scenario_to_dataframe"):
        if not hasattr(module, fn):
            raise AttributeError(f"Generator missing required function: {fn}")
    return module


def finite(x):
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def to_num(x):
    if x is None:
        return np.nan
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def to_bool(x):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, str):
        z = x.strip().lower()
        if z == "true":
            return True
        if z == "false":
            return False
    return np.nan


def replace_formula(source_text, new_formula):
    """
    Replace the glmer formula in the known Phase-1/2 fitter while preserving all
    estimator/diagnostic code. Fail closed if the expected M1 formula cannot be
    found. This prevents silently fitting the wrong model.
    """
    patterns = [
        r"y\s*~\s*X\s*\+\s*context_len\s*\+\s*is_self\s*\+\s*"
        r"\(1\s*\|\s*item_id\)\s*\+\s*"
        r"\(1\s*\+\s*is_self\s*\|\s*model_id\)",
    ]

    for pattern in patterns:
        new_text, n = re.subn(pattern, new_formula, source_text, count=1)
        if n == 1:
            return new_text

    raise RuntimeError(
        "Could not locate the expected M1 formula in glmer_fit.R. "
        "Source fitter was NOT modified. Inspect glmer_fit.R before proceeding."
    )


def make_architecture_fitters():
    if not SOURCE_R_PATH.exists():
        raise FileNotFoundError(f"Missing R fitter: {SOURCE_R_PATH}")

    source = SOURCE_R_PATH.read_text(encoding="utf-8")
    paths = {}

    for arch in ARCHITECTURES:
        text = replace_formula(source, arch["formula"])
        # Add a harmless provenance comment only to temporary copies.
        text = (
            f"# PHASE 3 TEMP FITTER — {arch['model_spec']}\n"
            f"# FORMULA: {arch['formula']}\n" + text
        )
        path = WORKDIR / f"{arch['model_spec']}.R"
        path.write_text(text, encoding="utf-8")
        paths[arch["model_spec"]] = path

        # Mechanical guard: exact intended formula must be present.
        if arch["formula"] not in path.read_text(encoding="utf-8"):
            raise RuntimeError(f"Formula guard failed for {arch['model_spec']}")

    return paths


def run_r(r_path, csv_path, json_path):
    p = subprocess.run(
        ["Rscript", str(r_path), str(csv_path), str(json_path), str(TRUE_EFFECT)],
        text=True,
        capture_output=True,
    )
    if p.returncode != 0:
        raise RuntimeError(
            f"Rscript failed ({p.returncode}): "
            f"{(p.stderr or p.stdout or '').strip()}"
        )
    if not json_path.exists():
        raise RuntimeError("Rscript returned 0 but produced no JSON.")
    fit = json.loads(json_path.read_text(encoding="utf-8"))
    if fit.get("error") not in (None, "", "null"):
        raise RuntimeError(f"Internal GLMM error: {fit.get('error')}")
    return fit, (p.stderr or "").strip()


def component_flags(fit):
    slope = to_num(fit.get("model_slope_sd"))
    model_sd = to_num(fit.get("model_intercept_sd"))
    item_sd = to_num(fit.get("item_intercept_sd"))
    corr = to_num(fit.get("model_intercept_slope_corr"))

    return {
        "slope_zero": bool(slope < 1e-4) if finite(slope) else np.nan,
        "model_zero": bool(model_sd < 1e-4) if finite(model_sd) else np.nan,
        "item_zero": bool(item_sd < 1e-4) if finite(item_sd) else np.nan,
        "corr_boundary": bool(abs(corr) >= 0.999) if finite(corr) else np.nan,
    }


def classify(fit):
    singular = to_bool(fit.get("singular"))
    if singular is False:
        return "non_singular"
    if singular is not True:
        return "unknown"

    flags = component_flags(fit)
    if flags["slope_zero"] is True:
        return "model_slope_sd_zero"
    if flags["corr_boundary"] is True:
        return "model_corr_boundary"
    if flags["model_zero"] is True:
        return "model_intercept_sd_zero"
    if flags["item_zero"] is True:
        return "item_intercept_sd_zero"
    return "other_boundary"


def summarize(results):
    out = []
    for arch in ARCHITECTURES:
        spec = arch["model_spec"]
        g = results[results["model_spec"] == spec].copy()
        f = g[g["fit_error"].isna()].copy()

        def bool_mean(col):
            if col not in f:
                return np.nan
            vals = f[col].map(
                lambda x: 1.0 if x is True else (0.0 if x is False else np.nan)
            )
            return vals.mean()

        def num(col):
            return pd.to_numeric(f[col], errors="coerce")

        out.append({
            "model_spec": spec,
            "formula": arch["formula"],
            "n_attempted": len(g),
            "n_fitted": len(f),
            "n_fit_errors": int(g["fit_error"].notna().sum()),
            "convergence_rate": bool_mean("converged"),
            "singular_fit_rate": bool_mean("singular"),
            "n_singular": int(sum(x is True for x in f["singular"])),
            "slope_zero_rate": bool_mean("slope_zero"),
            "model_zero_rate": bool_mean("model_zero"),
            "item_zero_rate": bool_mean("item_zero"),
            "corr_boundary_rate": bool_mean("corr_boundary"),
            "median_model_slope_sd": num("model_slope_sd").median(),
            "median_model_intercept_sd": num("model_intercept_sd").median(),
            "median_item_intercept_sd": num("item_intercept_sd").median(),
            "median_abs_model_corr":
                num("model_intercept_slope_corr").abs().median(),
            "mean_estimate": num("estimate").mean(),
            "mean_bias": num("bias").mean(),
            "median_se": num("se").median(),
            "rejection_rate": bool_mean("rejected_at_05"),
            "ci_coverage_rate": bool_mean("ci_covers_truth"),
            "near_separation_rate": bool_mean("near_separation"),
        })
    return pd.DataFrame(out)


def paired_table(results):
    good = results[results["fit_error"].isna()].copy()
    metrics = [
        "singular", "slope_zero", "model_zero", "item_zero", "corr_boundary",
        "estimate", "bias", "se", "p_value"
    ]
    pieces = []
    for metric in metrics:
        p = good.pivot(index=["rep", "seed"], columns="model_spec", values=metric)
        p.columns = [f"{metric}__{c}" for c in p.columns]
        pieces.append(p)
    return pd.concat(pieces, axis=1).reset_index()


def run(mode):
    reps = 1 if mode == "preflight" else 30
    expected = reps * len(ARCHITECTURES)

    prefix = "phase3_preflight" if mode == "preflight" else "phase3"
    results_path = DESIGNLAB / f"{prefix}_results.csv"
    summary_path = DESIGNLAB / f"{prefix}_summary.csv"
    paired_path = DESIGNLAB / f"{prefix}_paired_architectures.csv"

    print("=" * 68)
    print(f"PHASE 3 — ARCHITECTURE ABLATION ({mode.upper()})")
    print("=" * 68)
    print(f"Generated datasets: {reps}")
    print(f"Architectures per dataset: {len(ARCHITECTURES)}")
    print(f"Expected GLMM fits: {expected}")
    print("Baseline DGP fixed at slope=.02, model=.03, item=.03, rho=.30")
    print("Each dataset is generated ONCE and reused across all five fits.")
    print("Frozen v8.6.3 is NOT modified.")
    print()

    generator = load_generator()
    fitters = make_architecture_fitters()

    print("TEMPORARY FITTER FORMULA CHECK:")
    for arch in ARCHITECTURES:
        print(f"  {arch['model_spec']}: {arch['formula']}")
    print()

    rows = []
    fit_index = 0

    for rep in range(1, reps + 1):
        seed = BASE_SEED + rep

        # Critical pairing rule: ONE generator call per replication.
        generated = generator.generate_scenario(
            n_models=N_MODELS,
            n_items=N_ITEMS,
            target_corr=TARGET_CORR,
            true_effect=TRUE_EFFECT,
            slope_sd=SLOPE_SD,
            tau_model=TAU_MODEL,
            tau_item=TAU_ITEM,
            rho_model=RHO_MODEL,
            seed=seed,
        )
        df = generator.scenario_to_dataframe(generated)
        if len(df) != N_MODELS * N_ITEMS:
            raise RuntimeError(
                f"rep={rep}: expected {N_MODELS*N_ITEMS} rows, got {len(df)}"
            )

        csv_path = WORKDIR / f"{prefix}_rep{rep:02d}_seed{seed}.csv"
        df.to_csv(csv_path, index=False)
        diag = generated.get("diagnostics", {}) or {}

        for arch in ARCHITECTURES:
            fit_index += 1
            spec = arch["model_spec"]
            print(
                f"[{fit_index:03d}/{expected}] rep={rep:02d} "
                f"seed={seed} {spec}",
                flush=True,
            )

            json_path = WORKDIR / (
                f"{prefix}_rep{rep:02d}_seed{seed}_{spec}.json"
            )

            row = {
                "rep": rep,
                "seed": seed,
                "model_spec": spec,
                "formula": arch["formula"],
                "n_models": N_MODELS,
                "n_items": N_ITEMS,
                "target_corr": TARGET_CORR,
                "true_effect": TRUE_EFFECT,
                "slope_sd_true": SLOPE_SD,
                "tau_model_true": TAU_MODEL,
                "tau_item_true": TAU_ITEM,
                "rho_model_true": RHO_MODEL,
                "generated_rows": len(df),
                "realized_corr": diag.get("realized_corr"),
                "rho_model_realized": diag.get("rho_model_realized"),
                "near_separation": to_bool(diag.get("near_separation")),
                "p_min": diag.get("p_min"),
                "p_max": diag.get("p_max"),
                "fit_error": None,
            }

            try:
                fit, stderr = run_r(
                    fitters[spec], csv_path, json_path
                )
                flags = component_flags(fit)

                row.update({
                    "converged": to_bool(fit.get("converged")),
                    "singular": to_bool(fit.get("singular")),
                    "warnings": fit.get("warnings"),
                    "r_stderr": stderr,
                    "estimate": to_num(fit.get("estimate")),
                    "se": to_num(fit.get("se")),
                    "p_value": to_num(fit.get("p_value")),
                    "ci_low": to_num(fit.get("ci_low")),
                    "ci_high": to_num(fit.get("ci_high")),
                    "rejected_at_05": to_bool(fit.get("rejected_at_05")),
                    "bias": to_num(fit.get("bias")),
                    "ci_covers_truth": to_bool(fit.get("ci_covers_truth")),
                    "model_intercept_sd":
                        to_num(fit.get("model_intercept_sd")),
                    "model_slope_sd":
                        to_num(fit.get("model_slope_sd")),
                    "model_intercept_slope_corr":
                        to_num(fit.get("model_intercept_slope_corr")),
                    "item_intercept_sd":
                        to_num(fit.get("item_intercept_sd")),
                    "model_cov_min_eigenvalue":
                        to_num(fit.get("model_cov_min_eigenvalue")),
                    "singular_component_reported":
                        fit.get("singular_component"),
                    "singular_component_reclassified": classify(fit),
                    **flags,
                })

            except Exception as exc:
                row["fit_error"] = f"{type(exc).__name__}: {exc}"
                row["traceback"] = traceback.format_exc(limit=5)

            rows.append(row)
            pd.DataFrame(rows).to_csv(results_path, index=False)

    results = pd.DataFrame(rows)
    summary = summarize(results)
    paired = paired_table(results)

    results.to_csv(results_path, index=False)
    summary.to_csv(summary_path, index=False)
    paired.to_csv(paired_path, index=False)

    successful = int(results["fit_error"].isna().sum())
    errors = int(results["fit_error"].notna().sum())

    print()
    print("=" * 68)
    print("PHASE 3 VALIDATION")
    print("=" * 68)
    print("Total rows:", len(results))
    print("Successful GLMM fits:", successful)
    print("Fit errors:", errors)
    print("Generated datasets:", results["rep"].nunique())
    print("Architectures:", results["model_spec"].nunique())
    print()
    print(summary.to_string(index=False))
    print()

    # Hard integrity gates.
    if len(results) != expected:
        raise RuntimeError(f"Expected {expected} rows, found {len(results)}.")
    if successful != expected or errors != 0:
        raise RuntimeError(
            f"Only {successful}/{expected} fits succeeded; inspect outputs."
        )

    per_rep_specs = results.groupby("rep")["model_spec"].nunique()
    per_rep_seed = results.groupby("rep")["seed"].nunique()
    per_rep_corr = results.groupby("rep")["realized_corr"].nunique(dropna=False)
    per_rep_rho = results.groupby("rep")["rho_model_realized"].nunique(dropna=False)

    if not (per_rep_specs == len(ARCHITECTURES)).all():
        raise RuntimeError("PAIRING FAILED: not all architectures per dataset.")
    if not (per_rep_seed == 1).all():
        raise RuntimeError("PAIRING FAILED: multiple seeds inside a replication.")
    if not (per_rep_corr == 1).all():
        raise RuntimeError("PAIRING FAILED: realized_corr differs within rep.")
    if not (per_rep_rho == 1).all():
        raise RuntimeError("PAIRING FAILED: rho realization differs within rep.")

    print("=" * 68)
    print(f"PHASE 3 {mode.upper()} COMPLETE — {successful}/{expected}")
    print("DATASET/ARCHITECTURE PAIRING — PASS")
    print("=" * 68)
    print("Outputs:")
    print(f"1. {results_path.name}")
    print(f"2. {summary_path.name}")
    print(f"3. {paired_path.name}")
    if mode == "preflight":
        print()
        print("DO NOT launch --full yet.")
        print("Send the complete output to ChatGPT.")
    else:
        print()
        print("Upload all three CSVs to ChatGPT for paired architecture analysis.")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--full", action="store_true")
    args = parser.parse_args()
    run("preflight" if args.preflight else "full")


if __name__ == "__main__":
    main()
