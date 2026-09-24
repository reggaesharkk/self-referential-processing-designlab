#!/usr/bin/env python3
"""
PHASE 5 — Information-Scale / Variance-Detectability Experiment
===============================================================

Design Lab diagnostic only.
NEVER merge into or modify frozen OSF v8.6.3 materials.

Question:
Under clean exact within-model 50/50 Self/Control assignment, how does
increasing the number of model clusters and/or the item/within-model
information dimension affect recovery of the baseline tiny random-effects
structure under unchanged M1?

Hold fixed:
  true_effect = .10 log-odds
  slope_sd    = .02
  tau_model   = .03
  tau_item    = .03
  rho_model   = .30
  beta0       = .50
  beta_x      = .15
  beta_c      = .05

M1 unchanged:
  y ~ X + context_len + is_self
      + (1 | item_id) + (1 + is_self | model_id)

Assignment:
  Exactly half the items within every model are Self.
  Assignment occurs BEFORE outcome generation.

Scale cells:
  P5_A_24x100   24 models x 100 items
  P5_B_24x400   24 models x 400 items
  P5_C_50x100   50 models x 100 items
  P5_D_50x400   50 models x 400 items
  P5_E_100x100 100 models x 100 items
  P5_F_100x400 100 models x 400 items

Pairing / CRN:
  Each replication has one master SeedSequence.
  Each scale cell is generated deterministically from replication-level
  random streams. Comparisons are paired by replication seed.

Important limitation:
  Different dimensions cannot literally reuse identical arrays because their
  shapes differ. Pairing therefore means a common replication-level master
  seed and deterministic nested latent draws, not identical datasets.

Usage:
  python phase5_information_scale_runner.py --preflight
  python phase5_information_scale_runner.py --full
"""

from pathlib import Path
import argparse
import hashlib
import json
import math
import subprocess

import numpy as np
import pandas as pd

D = Path("/content/drive/MyDrive/DesignLab")
R_FIT = D / "phase6_glmer_fit.R"
WORK = D / "_phase6_work"
WORK.mkdir(parents=True, exist_ok=True)

TRUE_EFFECT = .10
SLOPE_SD = .02
TAU_MODEL = .03
TAU_ITEM = .03
RHO_MODEL = .30

BETA0 = .50
BETA_X = .15
BETA_C = .05

BASE_SEED = 92623000
N_REPS = 30

# Order deliberately chosen so the maximum 100x400 latent block can be
# generated once per replication and smaller cells can use deterministic
# prefixes. This gives stronger nesting than merely reseeding each cell.
MAX_MODELS = 100
MAX_ITEMS = 400

# Phase-6 DGP cells are defined below.


def sigmoid(x):
    x = np.asarray(x, float)
    return 1 / (1 + np.exp(-np.clip(x, -35, 35)))


def corr(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    if np.std(a) == 0 or np.std(b) == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def bval(v):
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, str):
        if v.lower() == "true":
            return True
        if v.lower() == "false":
            return False
    return np.nan


def fnum(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def make_master(seed, rho_model):
    """
    Generate one maximum-size latent block per replication.

    Smaller scale cells use prefixes:
      models 0:n_models
      items  0:n_items

    Thus overlapping models/items share the same latent values across cells.
    """
    ss = np.random.SeedSequence(seed)

    sx, sc, sa, sre, si, sy = ss.spawn(6)

    rx = np.random.default_rng(sx)
    rc = np.random.default_rng(sc)
    ra = np.random.default_rng(sa)
    rr = np.random.default_rng(sre)
    ri = np.random.default_rng(si)
    ry = np.random.default_rng(sy)

    # Model-level X.
    logp = rx.uniform(9, 12, MAX_MODELS)
    # IMPORTANT:
    # Center once at the maximum block so overlapping models retain identical
    # X values across cells. Do NOT re-center separately by cell.
    Xj = logp - logp.mean()

    # Item-level context.
    context = rc.normal(0, 1, MAX_ITEMS)

    # Balanced-assignment ranking uniforms for every model x item.
    Uassign = ra.uniform(size=(MAX_MODELS, MAX_ITEMS))

    # Correlated model intercept / Self-slope random effects.
    Sigma = np.array([
        [TAU_MODEL**2, rho_model * TAU_MODEL * SLOPE_SD],
        [rho_model * TAU_MODEL * SLOPE_SD, SLOPE_SD**2],
    ])
    L = np.linalg.cholesky(Sigma)
    model_re = rr.normal(size=(MAX_MODELS, 2)) @ L.T

    # Item random intercepts.
    item_re = ri.normal(0, TAU_ITEM, MAX_ITEMS)

    # Outcome uniforms.
    Uy = ry.uniform(size=(MAX_MODELS, MAX_ITEMS))

    return dict(
        Xj=Xj,
        context=context,
        Uassign=Uassign,
        model_re=model_re,
        item_re=item_re,
        Uy=Uy,
    )


def make_dataset(master, n_models, n_items):
    """
    Exact balanced assignment:
      n_items/2 Self + n_items/2 Control within every model.

    The smaller cells are deterministic prefixes of the maximum latent block.
    Assignment ranking is recalculated within the included item prefix,
    ensuring exact balance at every scale.
    """
    if n_items % 2 != 0:
        raise ValueError("n_items must be even for exact 50/50 assignment")

    Xj = master["Xj"][:n_models]
    context = master["context"][:n_items]
    Uassign = master["Uassign"][:n_models, :n_items]
    model_re = master["model_re"][:n_models]
    item_re = master["item_re"][:n_items]
    Uy = master["Uy"][:n_models, :n_items]

    zmat = np.zeros((n_models, n_items), dtype=int)

    # Nested exact-balanced assignment.
    #
    # First 100 items:
    #   exactly 50 Self + 50 Control.
    #
    # If n_items == 400, the additional 300 items are balanced separately:
    #   exactly 150 Self + 150 Control.
    #
    # Therefore the first 100 Self/Control assignments are IDENTICAL
    # between the 100-item and 400-item cells, while the full 400-item
    # design remains exactly 200 Self + 200 Control per model.
    for j in range(n_models):
        first = np.argsort(Uassign[j, :100])[:50]
        zmat[j, first] = 1

        if n_items == 400:
            extra_local = np.argsort(Uassign[j, 100:400])[:150]
            extra = 100 + extra_local
            zmat[j, extra] = 1
        elif n_items != 100:
            raise ValueError(
                f"Unsupported n_items={n_items}; expected 100 or 400"
            )

    mi, ii = np.meshgrid(
        np.arange(n_models),
        np.arange(n_items),
        indexing="ij"
    )

    Xmat = Xj[:, None]
    Cmat = context[None, :]

    b0m = model_re[:, 0]
    u1m = model_re[:, 1]

    eta = (
        BETA0
        + BETA_X * Xmat
        + TRUE_EFFECT * zmat
        + BETA_C * Cmat
        + b0m[:, None]
        + item_re[None, :]
        + u1m[:, None] * zmat
    )

    py = sigmoid(eta)
    ymat = (Uy < py).astype(int)

    df = pd.DataFrame({
        "model_id": mi.ravel(),
        "item_id": ii.ravel(),
        "X": np.broadcast_to(Xmat, (n_models, n_items)).ravel(),
        "context_len": np.broadcast_to(Cmat, (n_models, n_items)).ravel(),
        "is_self": zmat.ravel(),
        "y": ymat.ravel(),
    })

    pm = df.groupby("model_id").is_self.agg(["sum", "mean"])
    ncontrol = n_items - pm["sum"]

    # Within-model information for binary Self indicator:
    # sum_i (z_ij - mean(z_j))^2 = n_items * p_j * (1-p_j)
    within_ss = n_items * pm["mean"] * (1 - pm["mean"])

    dg = dict(
        n_obs=len(df),
        realized_corr=corr(df.X, df.is_self),
        overall_self_prop=float(df.is_self.mean()),
        min_model_n_self=int(pm["sum"].min()),
        min_model_n_control=int(ncontrol.min()),
        min_model_self_prop=float(pm["mean"].min()),
        max_model_self_prop=float(pm["mean"].max()),
        median_model_self_prop=float(pm["mean"].median()),
        corr_model_selfprop_X=corr(pm["mean"].to_numpy(), Xj),
        min_within_self_ss=float(within_ss.min()),
        median_within_self_ss=float(within_ss.median()),
        total_within_self_ss=float(within_ss.sum()),
        rho_model_realized=corr(model_re[:, 0], model_re[:, 1]),
        p_min=float(py.min()),
        p_max=float(py.max()),
        pct_outcome_p_below_05=float((py < .05).mean()),
        pct_outcome_p_above_95=float((py > .95).mean()),
    )

    return df, dg



# ============================================================================
# PHASE 6 — COVARIANCE-IDENTIFIABILITY ABLATION
# ============================================================================

import json
import subprocess
import argparse
import pandas as pd
import numpy as np

PHASE6_R_EXPECTED_SHA = (
    "ad655fcd69c16423bab5c1367c794196e5ded6bfb1af7920ceb134ccc8f6c765"
)

# Two information scales x two true covariance geometries.
#
# LOW is a literal prefix/subset of HIGH within each rho condition because
# make_master() creates the 100 x 400 maximum block and make_dataset()
# takes deterministic prefixes.
#
# The rho=0 and rho=.30 DGPs are separate generated worlds. Within a DGP
# cell, M1 and M2 receive the literal identical CSV.

DGP_CELLS = [
    ("P6_A_LOW_RHO0",   24, 100, 0.00),
    ("P6_B_LOW_RHO30",  24, 100, 0.30),
    ("P6_C_HIGH_RHO0", 100, 400, 0.00),
    ("P6_D_HIGH_RHO30",100, 400, 0.30),
]

FIT_SPECS = ("M1", "M2")

N_REPS = 30


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fit_phase6(df, rep, cell, fit_spec):
    """
    Fit M1 or M2.

    Critical pairing rule:
    both specifications receive the same already-generated dataframe.
    """

    csv = WORK / f"r{rep:03d}_{cell}.csv"
    js = WORK / f"r{rep:03d}_{cell}_{fit_spec}.json"

    # Writing the same dataframe to the same cell CSV is intentional.
    # M1 and M2 are then both pointed to this exact path.
    if not csv.exists():
        df.to_csv(csv, index=False)

    if js.exists():
        js.unlink()

    cmd = [
        "Rscript",
        str(R_FIT),
        str(csv),
        str(js),
        str(TRUE_EFFECT),
        fit_spec,
    ]

    cp = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if cp.returncode != 0 or not js.exists():
        return {
            "fit_error": (
                cp.stderr or cp.stdout or "R fit failed"
            )[-4000:]
        }

    try:
        with open(js, "r", encoding="utf-8") as f:
            out = json.load(f)
    except Exception as e:
        return {
            "fit_error": f"JSON read failure: {repr(e)}"
        }

    return out


def make_phase6_master(seed, rho):
    """
    Separate master block for each true-rho world.

    The seed mapping is deterministic and locked.
    """
    return make_master(seed, rho)


def component_flags(row):
    """
    Raw component flags.

    These are preferable to relying only on the first-match
    singular_component convenience label.
    """

    def small(x):
        try:
            return np.isfinite(float(x)) and float(x) < 1e-4
        except Exception:
            return False

    def corr_boundary(x):
        try:
            return np.isfinite(float(x)) and abs(float(x)) > .999
        except Exception:
            return False

    return {
        "slope_zero": small(row.get("model_slope_sd")),
        "model_intercept_zero": small(row.get("model_intercept_sd")),
        "item_intercept_zero": small(row.get("item_intercept_sd")),
        "corr_boundary": (
            row.get("fit_spec") == "M1"
            and corr_boundary(row.get("model_intercept_slope_corr"))
        ),
    }


def build_summary(r):
    rows = []

    for (cell, spec), q in r.groupby(
        ["cell", "fit_spec"],
        sort=False
    ):
        def mean_bool(col):
            if col not in q:
                return np.nan
            return pd.to_numeric(
                q[col], errors="coerce"
            ).mean()

        def mean_num(col):
            return pd.to_numeric(
                q[col], errors="coerce"
            ).mean()

        def median_num(col):
            return pd.to_numeric(
                q[col], errors="coerce"
            ).median()

        corr = pd.to_numeric(
            q["model_intercept_slope_corr"],
            errors="coerce"
        )

        finite_corr = corr[np.isfinite(corr)]

        rows.append({
            "cell": cell,
            "fit_spec": spec,
            "n": len(q),

            "n_models": int(q["n_models"].iloc[0]),
            "n_items": int(q["n_items"].iloc[0]),
            "n_obs": int(q["n_obs"].iloc[0]),
            "true_rho": float(q["true_rho"].iloc[0]),

            "error_rate": q["fit_error"].notna().mean(),

            "convergence_rate": mean_bool("converged"),
            "singular_rate": mean_bool("singular"),

            "slope_zero_rate": mean_bool("slope_zero"),
            "model_intercept_zero_rate":
                mean_bool("model_intercept_zero"),
            "item_intercept_zero_rate":
                mean_bool("item_intercept_zero"),
            "corr_boundary_rate":
                mean_bool("corr_boundary"),

            "median_model_slope_sd":
                median_num("model_slope_sd"),
            "median_model_intercept_sd":
                median_num("model_intercept_sd"),
            "median_item_intercept_sd":
                median_num("item_intercept_sd"),

            "median_abs_corr_finite":
                (
                    np.median(np.abs(finite_corr))
                    if len(finite_corr)
                    else np.nan
                ),

            "mean_estimate": mean_num("estimate"),
            "mean_bias": mean_num("bias"),
            "median_se": median_num("se"),
            "coverage_rate": mean_bool("ci_covers_truth"),
            "rejection_rate": mean_bool("rejected_at_05"),
        })

    return pd.DataFrame(rows)


def build_paired(r):
    """
    One row per DGP dataset, with M1 and M2 diagnostics side by side.
    """

    key = [
        "rep",
        "seed",
        "cell",
        "n_models",
        "n_items",
        "true_rho",
    ]

    keep = [
        "singular",
        "converged",
        "estimate",
        "se",
        "bias",
        "model_intercept_sd",
        "model_slope_sd",
        "item_intercept_sd",
        "model_intercept_slope_corr",
        "model_cov_min_eigenvalue",
        "slope_zero",
        "model_intercept_zero",
        "item_intercept_zero",
        "corr_boundary",
    ]

    a = r[key + ["fit_spec"] + keep].copy()

    wide = a.pivot(
        index=key,
        columns="fit_spec",
        values=keep
    )

    wide.columns = [
        f"{metric}_{spec}"
        for metric, spec in wide.columns
    ]

    wide = wide.reset_index()

    # Paired singularity transition.
    def transition(x):
        m1 = bool(x["singular_M1"])
        m2 = bool(x["singular_M2"])

        if m1 and not m2:
            return "M1_singular_to_M2_nonsingular"
        if m1 and m2:
            return "both_singular"
        if not m1 and m2:
            return "M1_nonsingular_to_M2_singular"
        return "both_nonsingular"

    wide["singularity_transition"] = wide.apply(
        transition,
        axis=1
    )

    wide["estimate_difference_M2_minus_M1"] = (
        pd.to_numeric(wide["estimate_M2"], errors="coerce")
        - pd.to_numeric(wide["estimate_M1"], errors="coerce")
    )

    wide["se_difference_M2_minus_M1"] = (
        pd.to_numeric(wide["se_M2"], errors="coerce")
        - pd.to_numeric(wide["se_M1"], errors="coerce")
    )

    return wide


def integrity_gate(r, nreps):
    expected = nreps * len(DGP_CELLS) * len(FIT_SPECS)

    if len(r) != expected:
        raise RuntimeError(
            f"Expected {expected} rows, found {len(r)}"
        )

    if r["fit_error"].notna().any():
        bad = r.loc[
            r["fit_error"].notna(),
            ["rep", "cell", "fit_spec", "fit_error"]
        ]
        raise RuntimeError(
            "Fit errors detected:\n" + bad.to_string(index=False)
        )

    # Exactly 8 fits per replicate.
    per_rep = r.groupby("rep").size()
    if not per_rep.eq(
        len(DGP_CELLS) * len(FIT_SPECS)
    ).all():
        raise RuntimeError(
            "Wrong number of fits in at least one replicate"
        )

    # Every dataset gets exactly M1 + M2.
    g = r.groupby(["rep", "cell"])

    if not g.size().eq(2).all():
        raise RuntimeError(
            "Every dataset must have exactly two fits"
        )

    if not g["fit_spec"].nunique().eq(2).all():
        raise RuntimeError(
            "M1/M2 pairing failure"
        )

    # Both architectures must consume the literal same dataset.
    if not g["dataset_sha256"].nunique().eq(1).all():
        raise RuntimeError(
            "M1/M2 dataset SHA mismatch"
        )

    # Architecture identity from R output.
    if not (
        r["fit_spec"]
        == r["r_fit_spec"]
    ).all():
        raise RuntimeError(
            "Python/R fit-spec mismatch"
        )

    # Exact assignment balance.
    if not (
        r["min_model_n_self"]
        == r["n_items"] // 2
    ).all():
        raise RuntimeError(
            "Self balance gate failed"
        )

    if not (
        r["min_model_n_control"]
        == r["n_items"] // 2
    ).all():
        raise RuntimeError(
            "Control balance gate failed"
        )

    # Self/X assignment correlation must be effectively zero.
    if (
        pd.to_numeric(
            r["realized_corr"],
            errors="coerce"
        ).abs() > 1e-12
    ).any():
        raise RuntimeError(
            "Assignment/X orthogonality gate failed"
        )

    return expected


def run_phase6(nreps, prefix):
    WORK.mkdir(parents=True, exist_ok=True)

    # Do not run against an unexpected R fitter.
    r_sha = sha256_file(R_FIT)

    if r_sha != PHASE6_R_EXPECTED_SHA:
        raise RuntimeError(
            "STOP: Phase-6 R fitter fingerprint changed.\n"
            f"Expected: {PHASE6_R_EXPECTED_SHA}\n"
            f"Found:    {r_sha}"
        )

    rows = []

    print("=" * 80)
    print("PHASE 6 — COVARIANCE-IDENTIFIABILITY ABLATION")
    print(
        f"{nreps} paired blocks x "
        f"{len(DGP_CELLS)} DGP cells x "
        f"{len(FIT_SPECS)} architectures = "
        f"{nreps * len(DGP_CELLS) * len(FIT_SPECS)} fits"
    )
    print("=" * 80)
    print("R fitter SHA256:", r_sha)
    print()

    for rep in range(1, nreps + 1):

        seed = BASE_SEED + rep

        # Create one master for each rho world.
        masters = {
            0.00: make_phase6_master(seed, 0.00),
            0.30: make_phase6_master(seed, 0.30),
        }

        for cell, n_models, n_items, true_rho in DGP_CELLS:

            master = masters[true_rho]

            df, dg = make_dataset(
                master,
                n_models,
                n_items
            )

            # A dataset fingerprint proves M1/M2 identity.
            dataset_csv = (
                WORK / f"r{rep:03d}_{cell}.csv"
            )

            if dataset_csv.exists():
                dataset_csv.unlink()

            df.to_csv(
                dataset_csv,
                index=False
            )

            dataset_sha = sha256_file(
                dataset_csv
            )

            for fit_spec in FIT_SPECS:

                fit = fit_phase6(
                    df,
                    rep,
                    cell,
                    fit_spec
                )

                row = {
                    "rep": rep,
                    "seed": seed,
                    "cell": cell,
                    "fit_spec": fit_spec,
                    "n_models": n_models,
                    "n_items": n_items,
                    "n_obs": n_models * n_items,
                    "true_rho": true_rho,
                    "true_effect": TRUE_EFFECT,
                    "true_slope_sd": SLOPE_SD,
                    "true_tau_model": TAU_MODEL,
                    "true_tau_item": TAU_ITEM,
                    "dataset_sha256": dataset_sha,
                }

                # Generator diagnostics
                row.update(dg)

                # Fit diagnostics
                row["fit_error"] = fit.get(
                    "fit_error",
                    fit.get("error")
                )

                row["r_fit_spec"] = fit.get(
                    "fit_spec"
                )

                for k in [
                    "converged",
                    "singular",
                    "warnings",
                    "estimate",
                    "se",
                    "p_value",
                    "ci_low",
                    "ci_high",
                    "rejected_at_05",
                    "bias",
                    "ci_covers_truth",
                    "model_intercept_sd",
                    "model_slope_sd",
                    "model_intercept_slope_corr",
                    "item_intercept_sd",
                    "model_cov_min_eigenvalue",
                    "theta",
                    "theta_lower",
                    "singular_component",
                ]:
                    row[k] = fit.get(k)

                row.update(
                    component_flags(row)
                )

                rows.append(row)

                print(
                    f"rep={rep:02d} "
                    f"{cell:18s} "
                    f"{fit_spec} "
                    f"singular={row['singular']} "
                    f"est={row['estimate']} "
                    f"se={row['se']}"
                )

    r = pd.DataFrame(rows)

    integrity_gate(r, nreps)

    summary = build_summary(r)
    paired = build_paired(r)

    raw_path = D / f"{prefix}_results.csv"
    summary_path = D / f"{prefix}_summary.csv"
    paired_path = D / f"{prefix}_paired.csv"

    r.to_csv(raw_path, index=False)
    summary.to_csv(summary_path, index=False)
    paired.to_csv(paired_path, index=False)

    print()
    print("=" * 80)
    print("PHASE 6 COMPLETE — INTEGRITY PASS")
    print("=" * 80)
    print("Results :", raw_path)
    print("Summary :", summary_path)
    print("Paired  :", paired_path)
    print("Rows    :", len(r))
    print("Errors  :", int(r["fit_error"].notna().sum()))

    print()
    print(summary.to_string(index=False))

    print()
    print("Paired singularity transitions:")
    print(
        paired.groupby(
            ["cell", "singularity_transition"]
        ).size().to_string()
    )

    return r, summary, paired


def source_audit():
    print("=" * 80)
    print("PHASE 6 — MECHANICAL AUDIT")
    print("ZERO FITS")
    print("=" * 80)

    assert len(DGP_CELLS) == 4
    assert FIT_SPECS == ("M1", "M2")
    assert N_REPS == 30

    assert set(
        (n, i)
        for _, n, i, _ in DGP_CELLS
    ) == {
        (24, 100),
        (100, 400),
    }

    assert set(
        rho
        for _, _, _, rho in DGP_CELLS
    ) == {
        0.00,
        0.30,
    }

    assert TRUE_EFFECT == .10
    assert SLOPE_SD == .02
    assert TAU_MODEL == .03
    assert TAU_ITEM == .03

    assert MAX_MODELS == 100
    assert MAX_ITEMS == 400

    assert sha256_file(
        R_FIT
    ) == PHASE6_R_EXPECTED_SHA

    print("[1] Four DGP cells ..................... PASS")
    print("[2] M1/M2 architectures ................ PASS")
    print("[3] 30 full replicates ................. PASS")
    print("[4] LOW/HIGH scales .................... PASS")
    print("[5] rho={0,.30} ........................ PASS")
    print("[6] true effect=.10 .................... PASS")
    print("[7] slope SD=.02 ....................... PASS")
    print("[8] tau_model=.03 ...................... PASS")
    print("[9] tau_item=.03 ....................... PASS")
    print("[10] max latent block=100x400 .......... PASS")
    print("[11] Phase-6 R fitter fingerprint ....... PASS")
    print()
    print("Preflight fits:", 1 * 4 * 2)
    print("Full fits     :", 30 * 4 * 2)
    print()
    print("MECHANICAL AUDIT PASS — ZERO FITS")


if __name__ == "__main__":

    ap = argparse.ArgumentParser()

    mode = ap.add_mutually_exclusive_group(
        required=True
    )

    mode.add_argument(
        "--audit",
        action="store_true"
    )

    mode.add_argument(
        "--preflight",
        action="store_true"
    )

    mode.add_argument(
        "--full",
        action="store_true"
    )

    args = ap.parse_args()

    if args.audit:
        source_audit()

    elif args.preflight:
        run_phase6(
            1,
            "phase6_preflight"
        )

    elif args.full:
        run_phase6(
            N_REPS,
            "phase6"
        )
