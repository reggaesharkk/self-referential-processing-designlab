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
R_FIT = D / "glmer_fit.R"
WORK = D / "_phase5_work"
WORK.mkdir(parents=True, exist_ok=True)

TRUE_EFFECT = .10
SLOPE_SD = .02
TAU_MODEL = .03
TAU_ITEM = .03
RHO_MODEL = .30

BETA0 = .50
BETA_X = .15
BETA_C = .05

BASE_SEED = 92622000
N_REPS = 30

# Order deliberately chosen so the maximum 100x400 latent block can be
# generated once per replication and smaller cells can use deterministic
# prefixes. This gives stronger nesting than merely reseeding each cell.
MAX_MODELS = 100
MAX_ITEMS = 400

CELLS = [
    ("P5_A_24x100",   24, 100),
    ("P5_B_24x400",   24, 400),
    ("P5_C_50x100",   50, 100),
    ("P5_D_50x400",   50, 400),
    ("P5_E_100x100", 100, 100),
    ("P5_F_100x400", 100, 400),
]


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


def make_master(seed):
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
        [TAU_MODEL**2, RHO_MODEL * TAU_MODEL * SLOPE_SD],
        [RHO_MODEL * TAU_MODEL * SLOPE_SD, SLOPE_SD**2],
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


def fit_one(df, rep, label):
    csv = WORK / f"r{rep:03d}_{label}.csv"
    js = WORK / f"r{rep:03d}_{label}.json"

    df.to_csv(csv, index=False)

    if js.exists():
        js.unlink()

    cmd = [
        "Rscript",
        str(R_FIT),
        str(csv),
        str(js),
        str(TRUE_EFFECT),
    ]

    cp = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if cp.returncode != 0 or not js.exists():
        return {
            "fit_error":
                (cp.stderr or cp.stdout or "R fit failed")[-4000:]
        }

    try:
        out = json.loads(js.read_text())
    except Exception as e:
        return {"fit_error": f"JSON parse: {e}"}

    out["fit_error"] = np.nan
    return out


def enrich_results(r):
    r = r.copy()

    r["singular_bool"] = r["singular"].map(bval)

    numeric_cols = [
        "model_slope_sd",
        "model_intercept_sd",
        "item_intercept_sd",
        "model_intercept_slope_corr",
        "estimate",
        "bias",
        "se",
        "p_value",
        "ci_low",
        "ci_high",
    ]

    for col in numeric_cols:
        if col in r.columns:
            r[col + "_num"] = r[col].map(fnum)

    r["slope_zero"] = r["model_slope_sd_num"].lt(1e-4)
    r["model_zero"] = r["model_intercept_sd_num"].lt(1e-4)
    r["item_zero"] = r["item_intercept_sd_num"].lt(1e-4)

    c = r["model_intercept_slope_corr_num"]

    r["corr_finite"] = c.notna()
    r["corr_boundary"] = c.abs().gt(.999)

    return r


def summarize(r):
    rows = []

    for label, n_models, n_items in CELLS:
        q = r[r.cell == label].copy()

        def mean(c):
            return float(q[c].mean()) if c in q else np.nan

        def med(c):
            return float(q[c].median()) if c in q else np.nan

        finite = q[q["corr_finite"]]

        boundary_among_finite = (
            float(finite["corr_boundary"].mean())
            if len(finite) else np.nan
        )

        finite_corr_median_abs = (
            float(finite["model_intercept_slope_corr_num"].abs().median())
            if len(finite) else np.nan
        )

        rows.append(dict(
            cell=label,
            n=len(q),
            n_models=n_models,
            n_items=n_items,
            n_obs=n_models * n_items,

            singular_fit_rate=mean("singular_bool"),
            slope_zero_rate=mean("slope_zero"),
            model_zero_rate=mean("model_zero"),
            item_zero_rate=mean("item_zero"),

            corr_finite_rate=mean("corr_finite"),
            corr_boundary_rate_unconditional=mean("corr_boundary"),
            corr_boundary_rate_among_finite=boundary_among_finite,
            median_abs_corr_among_finite=finite_corr_median_abs,

            median_fitted_slope_sd=med("model_slope_sd_num"),
            median_fitted_model_intercept_sd=med("model_intercept_sd_num"),
            median_fitted_item_sd=med("item_intercept_sd_num"),

            mean_estimate=mean("estimate_num"),
            mean_bias=mean("bias_num"),
            median_se=med("se_num"),

            ci_coverage=mean("ci_covers_truth"),
            rejection_rate=mean("rejected_at_05"),

            mean_realized_corr=mean("realized_corr"),
            median_min_model_n_self=med("min_model_n_self"),
            median_min_model_n_control=med("min_model_n_control"),
            median_within_self_ss=med("median_within_self_ss"),
            mean_total_within_self_ss=mean("total_within_self_ss"),

            mean_rho_model_realized=mean("rho_model_realized"),
        ))

    return pd.DataFrame(rows)


def paired_table(r):
    """
    One row per replication with key diagnostics for all six scale cells.
    """
    vals = [
        "singular_bool",
        "slope_zero",
        "model_zero",
        "item_zero",
        "corr_finite",
        "corr_boundary",
        "model_slope_sd_num",
        "model_intercept_sd_num",
        "item_intercept_sd_num",
        "model_intercept_slope_corr_num",
        "estimate_num",
        "bias_num",
        "se_num",
    ]

    wide = r.pivot(
        index="rep",
        columns="cell",
        values=vals
    )

    wide.columns = [
        "__".join(map(str, c))
        for c in wide.columns
    ]

    return wide.reset_index()


def integrity_check(r, nreps):
    expected = nreps * len(CELLS)

    if len(r) != expected:
        raise RuntimeError(
            f"Row-count failure: {len(r)} != {expected}"
        )

    errors = int(r["fit_error"].notna().sum())

    if errors:
        raise RuntimeError(
            f"Fit-error failure: {errors} fits failed"
        )

    g = r.groupby("rep")

    if not g.size().eq(len(CELLS)).all():
        raise RuntimeError(
            "Pairing failure: wrong number of cells in a replication"
        )

    if not g.cell.nunique().eq(len(CELLS)).all():
        raise RuntimeError(
            "Pairing failure: duplicate/missing scale cells"
        )

    if not g.seed.nunique().eq(1).all():
        raise RuntimeError(
            "Pairing failure: replication cells do not share seed"
        )

    expected_cells = set(x[0] for x in CELLS)

    for rep, q in g:
        if set(q.cell) != expected_cells:
            raise RuntimeError(
                f"Pairing failure in rep {rep}"
            )

    # Exact assignment balance is a HARD gate.
    if not np.allclose(r["overall_self_prop"], .5):
        raise RuntimeError(
            "Assignment gate failed: overall Self proportion != .5"
        )

    if not (
        r["min_model_n_self"].to_numpy()
        == (r["n_items"].to_numpy() // 2)
    ).all():
        raise RuntimeError(
            "Assignment gate failed: Self count not exactly half"
        )

    if not (
        r["min_model_n_control"].to_numpy()
        == (r["n_items"].to_numpy() // 2)
    ).all():
        raise RuntimeError(
            "Assignment gate failed: Control count not exactly half"
        )

    # With constant .5 Self proportion in every model, this should be NaN.
    nonnan = r["corr_model_selfprop_X"].notna().sum()
    if nonnan:
        raise RuntimeError(
            "Assignment gate failed: model Self proportion varies"
        )

    # X and Self should be mathematically orthogonal here up to floating error.
    if (r["realized_corr"].abs() > 1e-12).any():
        raise RuntimeError(
            "Assignment gate failed: X/Self correlation not ~0"
        )

    return expected, errors


def run(nreps, prefix):
    rows = []

    print("=" * 76)
    print("PHASE 5 — INFORMATION-SCALE / VARIANCE-DETECTABILITY")
    print(f"{nreps} paired blocks x {len(CELLS)} scale cells "
          f"= {nreps * len(CELLS)} fits")
    print("=" * 76)

    print("R fitter SHA256:", file_sha256(R_FIT))
    print()

    for rep in range(1, nreps + 1):
        seed = BASE_SEED + rep
        master = make_master(seed)

        for label, n_models, n_items in CELLS:
            try:
                df, dg = make_dataset(
                    master,
                    n_models=n_models,
                    n_items=n_items,
                )

                ft = fit_one(df, rep, label)

                row = dict(
                    rep=rep,
                    seed=seed,
                    cell=label,
                    n_models=n_models,
                    n_items=n_items,
                    true_effect=TRUE_EFFECT,
                    slope_sd=SLOPE_SD,
                    tau_model=TAU_MODEL,
                    tau_item=TAU_ITEM,
                    rho_model=RHO_MODEL,
                    beta0=BETA0,
                    beta_x=BETA_X,
                    beta_c=BETA_C,
                    **dg,
                    **ft,
                )

            except Exception as e:
                row = dict(
                    rep=rep,
                    seed=seed,
                    cell=label,
                    n_models=n_models,
                    n_items=n_items,
                    fit_error=f"{type(e).__name__}: {e}",
                )

            rows.append(row)

            print(
                f"rep {rep:02d}/{nreps} "
                f"{label:14s} "
                f"N={n_models*n_items:6d} "
                f"singular={row.get('singular', np.nan)} "
                f"error={pd.notna(row.get('fit_error'))}",
                flush=True,
            )

    r = pd.DataFrame(rows)

    raw = D / f"{prefix}_results.csv"
    r.to_csv(raw, index=False)

    # Fail closed BEFORE scientific summaries.
    expected = nreps * len(CELLS)
    errors = int(r["fit_error"].notna().sum())

    if len(r) != expected or errors:
        print()
        print("STOP — RAW CHECKPOINT PRESERVED")
        print(f"rows: {len(r)}/{expected}")
        print(f"fit errors: {errors}")
        print("Raw:", raw)
        return

    r = enrich_results(r)

    try:
        expected, errors = integrity_check(r, nreps)
    except Exception:
        # Preserve enriched raw file before stopping.
        r.to_csv(raw, index=False)
        raise

    s = summarize(r)
    p = paired_table(r)

    summary_path = D / f"{prefix}_summary.csv"
    paired_path = D / f"{prefix}_paired.csv"

    # Save enriched raw results.
    r.to_csv(raw, index=False)
    s.to_csv(summary_path, index=False)
    p.to_csv(paired_path, index=False)

    print()
    print("=" * 76)
    print("PHASE 5 COMPLETE — INTEGRITY PASS")
    print("=" * 76)
    print(
        f"fits: {len(r)}/{expected}; "
        f"errors: {errors}; "
        f"paired blocks: {nreps}"
    )
    print()
    print(s.to_string(index=False))
    print()
    print("Files:")
    print(raw.name)
    print(summary_path.name)
    print(paired_path.name)


def main():
    ap = argparse.ArgumentParser()

    x = ap.add_mutually_exclusive_group(required=True)
    x.add_argument("--preflight", action="store_true")
    x.add_argument("--full", action="store_true")

    a = ap.parse_args()

    if not R_FIT.exists():
        raise FileNotFoundError(f"Missing {R_FIT}")

    if a.preflight:
        run(1, "phase5_preflight")
    else:
        run(N_REPS, "phase5")


if __name__ == "__main__":
    main()
