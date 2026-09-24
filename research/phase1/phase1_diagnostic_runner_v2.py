#!/usr/bin/env python3
"""
DesignLab Phase-1 diagnostic runner v2.

Uses the EXISTING confound_generator.py by importing generate_scenario()
and scenario_to_dataframe() directly. It does not assume a generator CLI.

Diagnostic only. Does not modify frozen v8.6.3 or existing DesignLab files.

Fixed design:
  n_models = 8, 12, 24, 50
  n_items = 100
  target_corr = 0.6
  true_effect = 0.10 log-odds
  rho_model = 0.3
  slope_sd = 0.02 (explicitly fixed to current generator default)
  30 replications
  M1 = (1 + is_self | model_id)
  M2 = (1 + is_self || model_id), diagnostic comparator only

Total = 240 fits.
"""

from pathlib import Path
import importlib.util
import json
import subprocess
import tempfile

import numpy as np
import pandas as pd

DESIGNLAB = Path("/content/drive/MyDrive/DesignLab")
GENERATOR = DESIGNLAB / "confound_generator.py"
BASE_R = DESIGNLAB / "glmer_fit.R"

OUT_RESULTS = DESIGNLAB / "phase1_results_v2.csv"
OUT_SUMMARY = DESIGNLAB / "phase1_summary_v2.csv"

N_MODELS = [8, 12, 24, 50]
N_ITEMS = 100
TARGET_CORR = 0.6
TRUE_EFFECT = 0.10
RHO_MODEL = 0.3
SLOPE_SD = 0.02
N_REPS = 30
BASE_SEED = 92617000


def fail(msg):
    raise RuntimeError(msg)


def load_generator():
    spec = importlib.util.spec_from_file_location("designlab_generator", GENERATOR)
    if spec is None or spec.loader is None:
        fail(f"Could not import {GENERATOR}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in ("generate_scenario", "scenario_to_dataframe"):
        if not hasattr(mod, name):
            fail(f"Generator is missing required function: {name}")
    return mod


def make_r_variant(base_text, spec):
    correlated = "(1 + is_self | model_id)"
    uncorrelated = "(1 + is_self || model_id)"
    if correlated not in base_text:
        fail("Current correlated model term was not found in glmer_fit.R.")
    if spec == "M1":
        return base_text
    if spec == "M2":
        # Temporary diagnostic copy only; source glmer_fit.R is untouched.
        return base_text.replace(correlated, uncorrelated)
    fail(f"Unknown model spec {spec}")


def normalize_warning(w):
    if isinstance(w, list):
        return "; ".join(str(x) for x in w) or None
    if isinstance(w, str):
        return w or None
    return None if w is None else str(w)


def main():
    if not GENERATOR.exists():
        fail(f"Missing {GENERATOR}")
    if not BASE_R.exists():
        fail(f"Missing {BASE_R}")

    gen = load_generator()
    base_r_text = BASE_R.read_text()

    # Mechanical safety checks on the corrected fitter.
    for exact in (
        "input_csv   <- args[1]",
        "output_json <- args[2]",
        "true_effect <- as.numeric(args[3])",
    ):
        if exact not in base_r_text:
            fail(f"Safety check failed. Missing exact line: {exact}")

    rows = []

    with tempfile.TemporaryDirectory(prefix="phase1_v2_") as td:
        td = Path(td)

        r_paths = {}
        for spec in ("M1", "M2"):
            rp = td / f"glmer_fit_{spec}.R"
            rp.write_text(make_r_variant(base_r_text, spec))
            r_paths[spec] = rp

        fit_no = 0

        for n_models in N_MODELS:
            for rep in range(N_REPS):
                seed = BASE_SEED + n_models * 1000 + rep

                # IMPORTANT: direct call to the actual generator API.
                generated = gen.generate_scenario(
                    n_models=n_models,
                    n_items=N_ITEMS,
                    target_corr=TARGET_CORR,
                    true_effect=TRUE_EFFECT,
                    slope_sd=SLOPE_SD,
                    rho_model=RHO_MODEL,
                    seed=seed,
                )
                diagnostics = generated.get("diagnostics", {})
                df = gen.scenario_to_dataframe(generated)

                expected_rows = n_models * N_ITEMS
                if len(df) != expected_rows:
                    fail(
                        f"Generator row-count mismatch: got {len(df)}, "
                        f"expected {expected_rows}."
                    )

                csv_path = td / f"nm{n_models}_rep{rep:02d}.csv"
                df.to_csv(csv_path, index=False)

                # Paired comparison: exact same generated dataset goes to M1 and M2.
                for model_spec in ("M1", "M2"):
                    fit_no += 1
                    print(
                        f"[{fit_no:03d}/240] n_models={n_models} "
                        f"rep={rep+1:02d} spec={model_spec}",
                        flush=True,
                    )

                    json_path = td / f"nm{n_models}_rep{rep:02d}_{model_spec}.json"

                    row = {
                        "model_spec": model_spec,
                        "n_models": n_models,
                        "n_items": N_ITEMS,
                        "target_corr": TARGET_CORR,
                        "true_effect": TRUE_EFFECT,
                        "rho_model": RHO_MODEL,
                        "slope_sd_dgp": SLOPE_SD,
                        "rep": rep + 1,
                        "seed": seed,
                        "generator_realized_corr": diagnostics.get("realized_corr"),
                        "generator_gamma_x": diagnostics.get("gamma_x"),
                        "generator_near_separation": diagnostics.get("near_separation"),
                        "generator_p_min": diagnostics.get("p_min"),
                        "generator_p_max": diagnostics.get("p_max"),
                        "generator_rho_model_realized": diagnostics.get("rho_model_realized"),
                        "converged": np.nan,
                        "singular": np.nan,
                        "warnings": None,
                        "estimate": np.nan,
                        "se": np.nan,
                        "p_value": np.nan,
                        "ci_low": np.nan,
                        "ci_high": np.nan,
                        "rejected_at_05": np.nan,
                        "bias": np.nan,
                        "ci_covers_truth": np.nan,
                        "model_intercept_sd": np.nan,
                        "model_slope_sd": np.nan,
                        "model_intercept_slope_corr": np.nan,
                        "item_intercept_sd": np.nan,
                        "model_cov_min_eigenvalue": np.nan,
                        "theta": None,
                        "theta_lower": None,
                        "singular_component": None,
                        "fit_error": None,
                    }

                    proc = subprocess.run(
                        [
                            "Rscript",
                            str(r_paths[model_spec]),
                            str(csv_path),
                            str(json_path),
                            str(TRUE_EFFECT),
                        ],
                        text=True,
                        capture_output=True,
                    )

                    if proc.returncode != 0:
                        row["fit_error"] = (
                            f"Rscript return code {proc.returncode}: "
                            f"{(proc.stderr or proc.stdout).strip()}"
                        )
                    elif not json_path.exists():
                        row["fit_error"] = "R fit returned no JSON output"
                    else:
                        try:
                            fit = json.loads(json_path.read_text())
                            row.update({
                                "converged": fit.get("converged"),
                                "singular": fit.get("singular"),
                                "warnings": normalize_warning(fit.get("warnings")),
                                "estimate": fit.get("estimate"),
                                "se": fit.get("se"),
                                "p_value": fit.get("p_value"),
                                "ci_low": fit.get("ci_low"),
                                "ci_high": fit.get("ci_high"),
                                "rejected_at_05": fit.get("rejected_at_05"),
                                "bias": fit.get("bias"),
                                "ci_covers_truth": fit.get("ci_covers_truth"),
                                "model_intercept_sd": fit.get("model_intercept_sd"),
                                "model_slope_sd": fit.get("model_slope_sd"),
                                "model_intercept_slope_corr": fit.get("model_intercept_slope_corr"),
                                "item_intercept_sd": fit.get("item_intercept_sd"),
                                "model_cov_min_eigenvalue": fit.get("model_cov_min_eigenvalue"),
                                "theta": json.dumps(fit.get("theta")) if fit.get("theta") is not None else None,
                                "theta_lower": json.dumps(fit.get("theta_lower")) if fit.get("theta_lower") is not None else None,
                                "singular_component": fit.get("singular_component"),
                                "fit_error": fit.get("error"),
                            })
                        except Exception as e:
                            row["fit_error"] = f"JSON parse/read error: {e}"

                    rows.append(row)

                    # Checkpoint after every fit.
                    pd.DataFrame(rows).to_csv(OUT_RESULTS, index=False)

    results = pd.DataFrame(rows)

    # HARD SUCCESS GUARD: 240 rows is not enough; fits must actually succeed.
    n_attempted = len(results)
    n_fit_errors = int(results["fit_error"].notna().sum())
    n_fitted = n_attempted - n_fit_errors

    if n_attempted != 240:
        fail(f"Expected 240 attempted fits, got {n_attempted}.")
    if n_fitted == 0:
        fail(
            "PHASE 1 FAILED: 240 rows were created but ZERO GLMM fits succeeded. "
            "Do not interpret these outputs."
        )

    summary_rows = []
    for (spec, nm), g in results.groupby(["model_spec", "n_models"], sort=True):
        gf = g[g["fit_error"].isna()].copy()
        nf = len(gf)

        if nf:
            conv = gf["converged"].fillna(False).astype(bool)
            sing = gf["singular"].fillna(False).astype(bool)
            corr = pd.to_numeric(gf["model_intercept_slope_corr"], errors="coerce").abs()
            slope = pd.to_numeric(gf["model_slope_sd"], errors="coerce")
            item = pd.to_numeric(gf["item_intercept_sd"], errors="coerce")
            eig = pd.to_numeric(gf["model_cov_min_eigenvalue"], errors="coerce")
        else:
            conv = sing = pd.Series(dtype=bool)
            corr = slope = item = eig = pd.Series(dtype=float)

        summary_rows.append({
            "model_spec": spec,
            "n_models": nm,
            "n_attempted": len(g),
            "n_fitted": nf,
            "n_fit_errors": int(g["fit_error"].notna().sum()),
            "convergence_rate": conv.mean() if nf else np.nan,
            "singular_fit_rate": sing.mean() if nf else np.nan,
            "n_singular": int(sing.sum()) if nf else 0,
            # M1 diagnostics are directly interpretable from the current extractor.
            # For M2, VarCorr is split by ||, so raw M2 component fields may be NA;
            # isSingular() remains the primary M2 diagnostic.
            "corr_abs_ge_0_999_rate": (corr >= 0.999).mean() if corr.notna().any() else np.nan,
            "slope_sd_lt_1e_4_rate": (slope < 1e-4).mean() if slope.notna().any() else np.nan,
            "item_sd_lt_1e_4_rate": (item < 1e-4).mean() if item.notna().any() else np.nan,
            "median_model_slope_sd": slope.median() if slope.notna().any() else np.nan,
            "median_abs_model_corr": corr.median() if corr.notna().any() else np.nan,
            "median_model_cov_min_eigenvalue": eig.median() if eig.notna().any() else np.nan,
            "mean_estimate": pd.to_numeric(gf["estimate"], errors="coerce").mean() if nf else np.nan,
            "mean_bias": pd.to_numeric(gf["bias"], errors="coerce").mean() if nf else np.nan,
            "rejection_rate": pd.to_numeric(gf["rejected_at_05"], errors="coerce").mean() if nf else np.nan,
            "near_separation_rate": gf["generator_near_separation"].fillna(False).astype(bool).mean() if nf else np.nan,
        })

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT_SUMMARY, index=False)
    results.to_csv(OUT_RESULTS, index=False)

    print("\n============================================")
    print("PHASE 1 V2 COMPLETE")
    print("============================================")
    print(f"Attempted fits: {n_attempted} / 240")
    print(f"Successful fits: {n_fitted}")
    print(f"Fit errors: {n_fit_errors}")
    print(f"Results: {OUT_RESULTS}")
    print(f"Summary: {OUT_SUMMARY}")
    print("\n", summary.to_string(index=False))

    if n_fit_errors > 0:
        print(
            "\nWARNING: Some fits failed. Phase 1 completed with partial data; "
            "send both CSVs to ChatGPT before interpreting."
        )
    else:
        print("\nSUCCESS: all 240 GLMM fits completed. Send both v2 CSVs to ChatGPT.")


if __name__ == "__main__":
    main()
