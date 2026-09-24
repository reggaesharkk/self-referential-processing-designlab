#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scipy.stats import binomtest
except Exception as e:
    raise RuntimeError(
        "scipy is required for exact-binomial Phase 7 aggregation."
    ) from e


BASE = Path("/content/drive/MyDrive/DesignLab")
BLOCK_DIR = BASE / "phase7_blocks"

N_BLOCKS = 10
N_REPS = 500

EXPECTED_CELLS = {
    "P7_A_NULL_RHO0",
    "P7_B_NULL_RHO30",
    "P7_C_EFFECT_RHO0",
    "P7_D_EFFECT_RHO30",
}

EXPECTED_SPECS = {"M1", "M2"}

EXPECTED_RUNNER_SHA256 = "1f9192b4e1f0d9bf21b90191165f2b83c7c0a8286856dd7e6d105a2f737717fe"
EXPECTED_RFITTER_SHA256 = "ac3f128af92a10fbdb1ca627a9f0e6af0ac032a6587155a47f6dc8280f187530"
EXPECTED_PHASE6_SHA256 = "5d9b0c6a17132d6d14261106972bdf6c35cb687cd9cf9c761a1e178aeff33358"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def is_missing(x):
    if x is None:
        return True

    if isinstance(x, float) and np.isnan(x):
        return True

    if isinstance(x, str) and x.strip().upper() in {
        "",
        "NA",
        "NAN",
        "NONE",
        "NULL",
    }:
        return True

    return False


def as_bool(x):
    if isinstance(x, bool):
        return x

    if isinstance(x, (int, np.integer)):
        return bool(x)

    if isinstance(x, str):
        z = x.strip().lower()

        if z in {"true", "t", "1"}:
            return True

        if z in {"false", "f", "0"}:
            return False

    return np.nan


def exact_binomial_metrics(k: int, n: int, p0: float):
    if n <= 0:
        return {
            "count": k,
            "n": n,
            "rate": np.nan,
            "mcse": np.nan,
            "exact_ci_low": np.nan,
            "exact_ci_high": np.nan,
            "exact_p_value": np.nan,
            "compatible": False,
        }

    bt = binomtest(k, n, p=p0, alternative="two-sided")
    ci = bt.proportion_ci(
        confidence_level=0.95,
        method="exact",
    )

    rate = k / n

    return {
        "count": int(k),
        "n": int(n),
        "rate": float(rate),
        "mcse": float(math.sqrt(rate * (1.0 - rate) / n)),
        "exact_ci_low": float(ci.low),
        "exact_ci_high": float(ci.high),
        "exact_p_value": float(bt.pvalue),
        "compatible": bool(bt.pvalue >= 0.05),
    }


def load_and_verify_blocks():
    frames = []
    manifests = []

    expected_rep_sets = {
        block: set(
            range(
                (block - 1) * 50 + 1,
                block * 50 + 1,
            )
        )
        for block in range(1, N_BLOCKS + 1)
    }

    for block in range(1, N_BLOCKS + 1):
        rp = BLOCK_DIR / f"phase7_block_{block:02d}_results.csv"
        mp = BLOCK_DIR / f"phase7_block_{block:02d}_manifest.json"

        if not rp.exists():
            raise RuntimeError(f"Missing block results: {rp}")

        if not mp.exists():
            raise RuntimeError(f"Missing block manifest: {mp}")

        manifest = json.loads(mp.read_text(encoding="utf-8"))

        if manifest.get("integrity_pass") is not True:
            raise RuntimeError(
                f"Block {block:02d} manifest not integrity PASS."
            )

        if int(manifest.get("block", -1)) != block:
            raise RuntimeError(
                f"Block {block:02d} manifest block ID mismatch."
            )

        expected_start = (block - 1) * 50 + 1
        expected_end = block * 50

        if int(manifest.get("rep_start", -1)) != expected_start:
            raise RuntimeError(
                f"Block {block:02d} manifest rep_start mismatch."
            )

        if int(manifest.get("rep_end", -1)) != expected_end:
            raise RuntimeError(
                f"Block {block:02d} manifest rep_end mismatch."
            )

        if int(manifest.get("expected_fits", -1)) != 400:
            raise RuntimeError(
                f"Block {block:02d} expected_fits mismatch."
            )

        if int(manifest.get("recorded_rows", -1)) != 400:
            raise RuntimeError(
                f"Block {block:02d} recorded_rows mismatch."
            )

        if manifest.get("runner_sha256") != EXPECTED_RUNNER_SHA256:
            raise RuntimeError(
                f"Block {block:02d} runner SHA mismatch."
            )

        if manifest.get("r_fitter_sha256") != EXPECTED_RFITTER_SHA256:
            raise RuntimeError(
                f"Block {block:02d} R-fitter SHA mismatch."
            )

        if (
            manifest.get("phase6_generator_source_sha256")
            != EXPECTED_PHASE6_SHA256
        ):
            raise RuntimeError(
                f"Block {block:02d} Phase-6 source SHA mismatch."
            )

        actual_sha = sha256_file(rp)

        if actual_sha != manifest.get("results_sha256"):
            raise RuntimeError(
                f"Block {block:02d} results SHA mismatch."
            )

        df = pd.read_csv(rp)

        if len(df) != 400:
            raise RuntimeError(
                f"Block {block:02d} has {len(df)} rows, expected 400."
            )

        if set(df["rep"].unique()) != expected_rep_sets[block]:
            raise RuntimeError(
                f"Block {block:02d} replicate membership mismatch."
            )

        frames.append(df)

        manifests.append(
            {
                **manifest,
                "manifest_file": mp.name,
                "manifest_sha256": sha256_file(mp),
            }
        )

    all_results = pd.concat(frames, ignore_index=True)

    if len(all_results) != 4000:
        raise RuntimeError(
            f"Expected 4000 rows, found {len(all_results)}."
        )

    if all_results["rep"].nunique() != 500:
        raise RuntimeError("Expected 500 unique replicates.")

    if set(all_results["rep"].unique()) != set(range(1, 501)):
        raise RuntimeError(
            "Production replicate set must be exactly 1..500."
        )

    if set(all_results["cell"].unique()) != EXPECTED_CELLS:
        raise RuntimeError("Cell set mismatch.")

    if set(all_results["fit_spec"].unique()) != EXPECTED_SPECS:
        raise RuntimeError("Fit-spec set mismatch.")

    expected_grid = pd.MultiIndex.from_product(
        [
            range(1, 501),
            sorted(EXPECTED_CELLS),
            sorted(EXPECTED_SPECS),
        ],
        names=["rep", "cell", "fit_spec"],
    )

    actual_grid = pd.MultiIndex.from_frame(
        all_results[["rep", "cell", "fit_spec"]]
    )

    if actual_grid.has_duplicates:
        raise RuntimeError(
            "Duplicate rep/cell/fit_spec production rows detected."
        )

    if set(actual_grid.tolist()) != set(expected_grid.tolist()):
        raise RuntimeError(
            "Incomplete rep x cell x fit_spec Cartesian grid."
        )

    g = all_results.groupby(["rep", "cell"])

    if not g.size().eq(2).all():
        raise RuntimeError(
            "Each rep/cell must contain exactly two fits."
        )

    if not g["fit_spec"].nunique().eq(2).all():
        raise RuntimeError("M1/M2 pairing failure.")

    if not g["dataset_sha256"].nunique().eq(1).all():
        raise RuntimeError("M1/M2 dataset SHA mismatch.")

    return all_results, pd.DataFrame(manifests)

def add_analysis_columns(df):
    out = df.copy()

    numeric_cols = [
        "estimate",
        "se",
        "p_value",
        "ci_low",
        "ci_high",
        "true_effect",
    ]

    for c in numeric_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(
                out[c],
                errors="coerce",
            )

    required = [
        "estimate",
        "se",
        "p_value",
        "ci_low",
        "ci_high",
    ]

    evaluable = np.ones(len(out), dtype=bool)

    for c in required:
        if c not in out.columns:
            raise RuntimeError(
                f"Required inferential column missing: {c}"
            )

        evaluable &= out[c].notna().to_numpy()

    out["evaluable"] = evaluable

    out["rejected"] = np.where(
        out["evaluable"],
        out["p_value"] < 0.05,
        np.nan,
    )

    out["covered"] = np.where(
        out["evaluable"],
        (
            (out["ci_low"] <= out["true_effect"])
            & (out["ci_high"] >= out["true_effect"])
        ),
        np.nan,
    )

    out["bias"] = np.where(
        out["evaluable"],
        out["estimate"] - out["true_effect"],
        np.nan,
    )

    if "singular" in out.columns:
        out["singular_bool"] = out["singular"].map(as_bool)
    else:
        out["singular_bool"] = np.nan

    return out


def summarize_one(g):
    n_attempted = len(g)

    e = g[g["evaluable"]].copy()
    n_eval = len(e)

    true_effect = float(g["true_effect"].iloc[0])

    n_reject = int(e["rejected"].sum()) if n_eval else 0
    n_cover = int(e["covered"].sum()) if n_eval else 0

    target_rejection = 0.05 if true_effect == 0.0 else None

    rejection_exact = (
        exact_binomial_metrics(n_reject, n_eval, 0.05)
        if true_effect == 0.0
        else None
    )

    coverage_exact = exact_binomial_metrics(
        n_cover,
        n_eval,
        0.95,
    )

    empirical_sd = (
        float(e["estimate"].std(ddof=1))
        if n_eval >= 2
        else np.nan
    )

    mean_se = (
        float(e["se"].mean())
        if n_eval
        else np.nan
    )

    row = {
        "n_attempted": n_attempted,
        "n_evaluable": n_eval,
        "fit_failure_rate": 1.0 - n_eval / n_attempted,
        "true_effect": true_effect,
        "true_rho": float(g["true_rho"].iloc[0]),
        "mean_estimate": float(e["estimate"].mean()) if n_eval else np.nan,
        "mean_bias": float(e["bias"].mean()) if n_eval else np.nan,
        "relative_bias": (
            float(e["bias"].mean() / true_effect)
            if n_eval and true_effect != 0.0
            else np.nan
        ),
        "empirical_sd": empirical_sd,
        "mean_model_se": mean_se,
        "median_model_se": (
            float(e["se"].median())
            if n_eval
            else np.nan
        ),
        "empirical_sd_over_mean_se": (
            empirical_sd / mean_se
            if (
                np.isfinite(empirical_sd)
                and np.isfinite(mean_se)
                and mean_se != 0
            )
            else np.nan
        ),
        "rejection_count": n_reject,
        "rejection_rate": (
            n_reject / n_eval
            if n_eval
            else np.nan
        ),
        "coverage_count": n_cover,
        "coverage_rate": (
            n_cover / n_eval
            if n_eval
            else np.nan
        ),
    }

    if "converged" in g.columns:
        conv = g["converged"].map(as_bool)
        row["convergence_rate"] = float(
            np.nanmean(conv.astype(float))
        )
    else:
        row["convergence_rate"] = np.nan

    if "singular_bool" in g.columns:
        s = g["singular_bool"]
        row["singular_rate"] = float(
            np.nanmean(pd.to_numeric(s, errors="coerce"))
        )
    else:
        row["singular_rate"] = np.nan

    # Preserve known Phase-6 component flags when available.
    for c in [
        "slope_zero",
        "model_intercept_zero",
        "item_intercept_zero",
        "corr_boundary",
    ]:
        if c in g.columns:
            vals = g[c].map(as_bool)
            row[f"{c}_rate"] = float(
                np.nanmean(pd.to_numeric(vals, errors="coerce"))
            )
        else:
            row[f"{c}_rate"] = np.nan

    if rejection_exact is not None:
        row.update(
            {
                "type1_exact_ci_low": rejection_exact["exact_ci_low"],
                "type1_exact_ci_high": rejection_exact["exact_ci_high"],
                "type1_exact_p_value": rejection_exact["exact_p_value"],
                "type1_compatible": rejection_exact["compatible"],
                "type1_mcse": rejection_exact["mcse"],
            }
        )
    else:
        row.update(
            {
                "type1_exact_ci_low": np.nan,
                "type1_exact_ci_high": np.nan,
                "type1_exact_p_value": np.nan,
                "type1_compatible": np.nan,
                "type1_mcse": np.nan,
            }
        )

    row.update(
        {
            "coverage_exact_ci_low": coverage_exact["exact_ci_low"],
            "coverage_exact_ci_high": coverage_exact["exact_ci_high"],
            "coverage_exact_p_value": coverage_exact["exact_p_value"],
            "coverage_compatible": coverage_exact["compatible"],
            "coverage_mcse": coverage_exact["mcse"],
        }
    )

    return pd.Series(row)


def build_summary(df):
    rows = []

    for (cell, fit_spec), g in df.groupby(
        ["cell", "fit_spec"],
        sort=True,
        dropna=False,
    ):
        # --------------------------------------------------
        # PRIMARY analysis: all attempted fits, with
        # inferential quantities calculated over evaluable
        # fits exactly as locked.
        # --------------------------------------------------
        primary = summarize_one(g).to_dict()

        primary.update(
            {
                "cell": cell,
                "fit_spec": fit_spec,
                "stratum": "all",
                "primary_calibration_stratum": True,
            }
        )

        rows.append(primary)

        # --------------------------------------------------
        # DESCRIPTIVE singular/nonsingular stratification.
        #
        # Unknown singularity states are not silently assigned
        # to either diagnostic stratum. They remain represented
        # in the primary 'all' row.
        # --------------------------------------------------
        s = pd.to_numeric(
            g["singular_bool"],
            errors="coerce",
        )

        for label, value in [
            ("singular", 1.0),
            ("nonsingular", 0.0),
        ]:
            subset = g[s == value].copy()

            if len(subset):
                diagnostic = summarize_one(subset).to_dict()
            else:
                diagnostic = {
                    key: np.nan
                    for key in primary.keys()
                    if key not in {
                        "cell",
                        "fit_spec",
                        "stratum",
                        "primary_calibration_stratum",
                    }
                }

                diagnostic["n_attempted"] = 0
                diagnostic["n_evaluable"] = 0
                diagnostic["fit_failure_rate"] = np.nan
                diagnostic["true_effect"] = float(
                    g["true_effect"].iloc[0]
                )
                diagnostic["true_rho"] = float(
                    g["true_rho"].iloc[0]
                )

            # Diagnostic strata must never be mistaken for
            # the prespecified architecture calibration screen.
            for key in [
                "type1_compatible",
                "coverage_compatible",
            ]:
                if key in diagnostic:
                    diagnostic[key] = np.nan

            diagnostic.update(
                {
                    "cell": cell,
                    "fit_spec": fit_spec,
                    "stratum": label,
                    "primary_calibration_stratum": False,
                }
            )

            rows.append(diagnostic)

    out = pd.DataFrame(rows)

    first = [
        "cell",
        "fit_spec",
        "stratum",
        "primary_calibration_stratum",
    ]

    rest = [
        c
        for c in out.columns
        if c not in first
    ]

    out = out[first + rest]

    expected_rows = len(EXPECTED_CELLS) * len(EXPECTED_SPECS) * 3

    if len(out) != expected_rows:
        raise RuntimeError(
            f"Expected {expected_rows} summary rows, got {len(out)}."
        )

    primary = out[
        out["primary_calibration_stratum"] == True
    ]

    if len(primary) != 8:
        raise RuntimeError(
            "Expected exactly 8 primary calibration rows."
        )

    if set(primary["stratum"]) != {"all"}:
        raise RuntimeError(
            "Primary calibration rows must be stratum='all'."
        )

    return out

def build_paired(df):
    rows = []

    for (rep, cell), g in df.groupby(["rep", "cell"]):
        if set(g["fit_spec"]) != {"M1", "M2"}:
            raise RuntimeError(
                f"Pair missing for rep={rep}, cell={cell}"
            )

        m1 = g[g["fit_spec"] == "M1"].iloc[0]
        m2 = g[g["fit_spec"] == "M2"].iloc[0]

        def safe_diff(a, b):
            try:
                aa = float(a)
                bb = float(b)

                if np.isfinite(aa) and np.isfinite(bb):
                    return aa - bb
            except Exception:
                pass

            return np.nan

        rows.append(
            {
                "rep": rep,
                "cell": cell,
                "true_effect": m1["true_effect"],
                "true_rho": m1["true_rho"],
                "dataset_sha256": m1["dataset_sha256"],
                "M1_evaluable": bool(m1["evaluable"]),
                "M2_evaluable": bool(m2["evaluable"]),
                "estimate_difference_M2_minus_M1": safe_diff(
                    m2["estimate"],
                    m1["estimate"],
                ),
                "se_difference_M2_minus_M1": safe_diff(
                    m2["se"],
                    m1["se"],
                ),
                "M1_rejected": m1["rejected"],
                "M2_rejected": m2["rejected"],
                "M1_covered": m1["covered"],
                "M2_covered": m2["covered"],
                "M1_singular": m1["singular_bool"],
                "M2_singular": m2["singular_bool"],
            }
        )

    out = pd.DataFrame(rows)

    if len(out) != 2000:
        raise RuntimeError(
            f"Expected 2000 paired rows, got {len(out)}"
        )

    return out


def write_integrity_report(df, manifests):
    lines = [
        "PHASE 7 FINAL INTEGRITY REPORT",
        "",
        f"raw_rows={len(df)}",
        f"unique_reps={df['rep'].nunique()}",
        f"unique_cells={df['cell'].nunique()}",
        f"fit_specs={sorted(df['fit_spec'].unique().tolist())}",
        f"block_manifests={len(manifests)}",
        "all_block_integrity_pass=True",
        "M1_M2_dataset_sha_pairing=True",
        "expected_total_fits=4000",
        "integrity_pass=True",
        "",
    ]

    return "\n".join(lines)


def main():
    raw, manifests = load_and_verify_blocks()

    analyzed = add_analysis_columns(raw)

    summary = build_summary(analyzed)
    paired = build_paired(analyzed)

    results_path = BASE / "phase7_results.csv"
    summary_path = BASE / "phase7_summary.csv"
    paired_path = BASE / "phase7_paired.csv"
    manifest_path = BASE / "phase7_blocks_manifest.csv"
    integrity_path = BASE / "phase7_integrity_report.txt"
    sums_path = BASE / "phase7_SHA256SUMS.txt"

    outputs = [
        results_path,
        summary_path,
        paired_path,
        manifest_path,
        integrity_path,
        sums_path,
    ]

    existing = [p for p in outputs if p.exists()]

    if existing:
        raise RuntimeError(
            "Refusing to overwrite existing final Phase 7 outputs: "
            + ", ".join(str(p) for p in existing)
        )

    analyzed.to_csv(results_path, index=False)
    summary.to_csv(summary_path, index=False)
    paired.to_csv(paired_path, index=False)
    manifests.to_csv(manifest_path, index=False)

    integrity_path.write_text(
        write_integrity_report(analyzed, manifests),
        encoding="utf-8",
    )

    hash_targets = [
        results_path,
        summary_path,
        paired_path,
        manifest_path,
        integrity_path,
        BASE / "phase7_design_lock.md",
        BASE / "phase7_inferential_validation_runner.py",
        BASE / "phase7_glmer_fit.R",
        BASE / "phase7_aggregate.py",
    ]

    lines = []

    for p in hash_targets:
        lines.append(
            f"{sha256_file(p)}  {p.name}"
        )

    sums_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("PHASE 7 FINAL AGGREGATION — INTEGRITY PASS")
    print(f"results rows: {len(analyzed)}")
    print(f"summary rows: {len(summary)}")
    print(f"paired rows: {len(paired)}")


if __name__ == "__main__":
    main()
