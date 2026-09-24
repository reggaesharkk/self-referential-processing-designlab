#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd


BASE = Path("/content/drive/MyDrive/DesignLab")

PHASE6_RUNNER = BASE / "phase6_covariance_identifiability_runner.py"
PHASE7_RFITTER = BASE / "phase7_glmer_fit.R"

EXPECTED_PHASE6_RUNNER_SHA = (
    "5d9b0c6a17132d6d14261106972bdf6c35cb687cd9cf9c761a1e178aeff33358"
)

PHASE7_BASE_SEED = 92622000

N_MODELS = 100
N_ITEMS = 400
N_REPS = 500
BLOCK_SIZE = 50
N_BLOCKS = 10

TAU_MODEL = 0.03
SLOPE_SD = 0.02
TAU_ITEM = 0.03

BETA_X = 0.15
BETA_C = 0.05

ALPHA = 0.05

CELLS = [
    {
        "cell": "P7_A_NULL_RHO0",
        "true_effect": 0.00,
        "rho_model": 0.00,
    },
    {
        "cell": "P7_B_NULL_RHO30",
        "true_effect": 0.00,
        "rho_model": 0.30,
    },
    {
        "cell": "P7_C_EFFECT_RHO0",
        "true_effect": 0.10,
        "rho_model": 0.00,
    },
    {
        "cell": "P7_D_EFFECT_RHO30",
        "true_effect": 0.10,
        "rho_model": 0.30,
    },
]

FIT_SPECS = ["M1", "M2"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_phase6_module():
    if not PHASE6_RUNNER.exists():
        raise RuntimeError(f"Missing frozen Phase 6 runner: {PHASE6_RUNNER}")

    got = sha256_file(PHASE6_RUNNER)

    if got != EXPECTED_PHASE6_RUNNER_SHA:
        raise RuntimeError(
            "Frozen Phase 6 runner fingerprint mismatch: "
            f"{got}"
        )

    spec = importlib.util.spec_from_file_location(
        "phase6_frozen",
        PHASE6_RUNNER,
    )

    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    return module


P6 = load_phase6_module()


def block_bounds(block: int):
    if block < 1 or block > N_BLOCKS:
        raise ValueError(f"block must be 1..{N_BLOCKS}")

    start = (block - 1) * BLOCK_SIZE + 1
    end = block * BLOCK_SIZE

    return start, end


def production_seed(rep: int) -> int:
    if rep < 1 or rep > N_REPS:
        raise ValueError("production rep outside 1..500")

    return PHASE7_BASE_SEED + rep


def exact_binomial_assignment_from_uniforms(u: np.ndarray) -> np.ndarray:
    """
    Convert one uniform vector per model into exactly 200 Self and
    200 Control observations by rank.

    The assignment is deterministic given u and contains no dependence
    on the outcome.
    """
    if u.shape != (N_MODELS, N_ITEMS):
        raise ValueError(f"Unexpected assignment shape: {u.shape}")

    out = np.zeros((N_MODELS, N_ITEMS), dtype=np.int8)

    for j in range(N_MODELS):
        idx = np.argsort(u[j], kind="mergesort")
        out[j, idx[: N_ITEMS // 2]] = 1

    return out



def generate_master_randomness(rep: int, rho_model: float):
    """
    Phase-7 high-information master block.

    This deliberately reproduces the substantive Phase-6 high-information
    generator geometry while using the locked Phase-7 production seed
    namespace.

    Null and alternative conditions at the same rep/rho reuse this exact
    latent block and outcome-uniform matrix.
    """
    seed = production_seed(rep)

    # Exact Phase-6 cross-rho CRN structure:
    # both rho worlds begin from the same six random-number streams.
    # rho changes only the covariance transform applied to the shared
    # underlying model-RE standard-normal draws.
    ss = np.random.SeedSequence(seed)

    sx, sc, sa, sre, si, sy = ss.spawn(6)

    rx = np.random.default_rng(sx)
    rc = np.random.default_rng(sc)
    ra = np.random.default_rng(sa)
    rr = np.random.default_rng(sre)
    ri = np.random.default_rng(si)
    ry = np.random.default_rng(sy)

    # PHASE-6 GEOMETRY:
    # log10 parameter scale ~ Uniform(9,12), then mean-center.
    logp = rx.uniform(9, 12, N_MODELS)
    Xj = logp - logp.mean()

    # PHASE-6 GEOMETRY:
    # one item-level context value shared across models.
    context = rc.normal(0, 1, N_ITEMS)

    # Balanced-assignment ranking uniforms.
    Uassign = ra.uniform(
        size=(N_MODELS, N_ITEMS)
    )

    # PHASE-6 covariance construction.
    Sigma = np.array([
        [
            TAU_MODEL**2,
            rho_model * TAU_MODEL * SLOPE_SD,
        ],
        [
            rho_model * TAU_MODEL * SLOPE_SD,
            SLOPE_SD**2,
        ],
    ])

    L = np.linalg.cholesky(Sigma)

    model_re = (
        rr.normal(size=(N_MODELS, 2))
        @ L.T
    )

    # Item random intercepts.
    item_re = ri.normal(
        0,
        TAU_ITEM,
        N_ITEMS
    )

    # Common outcome uniforms.
    Uy = ry.uniform(
        size=(N_MODELS, N_ITEMS)
    )

    return {
        "Xj": Xj,
        "context": context,
        "Uassign": Uassign,
        "model_re": model_re,
        "item_re": item_re,
        "Uy": Uy,
    }



def make_dataset(rep: int, true_effect: float, rho_model: float):
    """
    Generate one Phase-7 100-model x 400-item dataset using the
    frozen Phase-6 HIGH-cell generator geometry.

    The only scientific effect manipulation introduced for Phase 7 is
    true_effect in {0.00, 0.10}.
    """
    master = generate_master_randomness(
        rep,
        rho_model,
    )

    Xj = master["Xj"]
    context = master["context"]
    Uassign = master["Uassign"]
    model_re = master["model_re"]
    item_re = master["item_re"]
    Uy = master["Uy"]

    # Exact Phase-6 HIGH-cell assignment geometry:
    #
    # first 100 items:
    #   50 Self + 50 Control
    #
    # remaining 300 items:
    #   150 Self + 150 Control
    #
    # total:
    #   200 Self + 200 Control per model
    zmat = np.zeros(
        (N_MODELS, N_ITEMS),
        dtype=int,
    )

    for j in range(N_MODELS):

        first = np.argsort(
            Uassign[j, :100]
        )[:50]

        zmat[j, first] = 1

        extra_local = np.argsort(
            Uassign[j, 100:400]
        )[:150]

        extra = 100 + extra_local

        zmat[j, extra] = 1

    mi, ii = np.meshgrid(
        np.arange(N_MODELS),
        np.arange(N_ITEMS),
        indexing="ij",
    )

    Xmat = Xj[:, None]
    Cmat = context[None, :]

    b0m = model_re[:, 0]
    u1m = model_re[:, 1]

    beta0 = 0.50

    eta = (
        beta0
        + BETA_X * Xmat
        + true_effect * zmat
        + BETA_C * Cmat
        + b0m[:, None]
        + item_re[None, :]
        + u1m[:, None] * zmat
    )

    p = 1.0 / (
        1.0 + np.exp(-eta)
    )

    ymat = (
        Uy < p
    ).astype(int)

    df = pd.DataFrame({
        "model_id": mi.ravel().astype(str),
        "item_id": ii.ravel().astype(str),
        "X": np.broadcast_to(
            Xmat,
            (N_MODELS, N_ITEMS)
        ).ravel(),
        "context_len": np.broadcast_to(
            Cmat,
            (N_MODELS, N_ITEMS)
        ).ravel(),
        "is_self": zmat.ravel(),
        "y": ymat.ravel(),
    })

    pm = (
        df.groupby("model_id")
        ["is_self"]
        .agg(["sum", "mean"])
    )

    if not (pm["sum"] == 200).all():
        raise RuntimeError(
            "Phase-6 HIGH-cell 200/200 balance invariant failed."
        )

    if len(df) != 40000:
        raise RuntimeError(
            "Phase-7 n_obs invariant failed."
        )

    # Diagnostics retain the production fields needed by the runner
    # while adding explicit cross-phase geometry checks.
    diagnostics = {
        "n_obs": int(len(df)),
        "min_model_n_self": int(
            pm["sum"].min()
        ),
        "max_model_n_self": int(
            pm["sum"].max()
        ),
        "overall_self_prop": float(
            df["is_self"].mean()
        ),
        "true_effect": float(
            true_effect
        ),
        "rho_model": float(
            rho_model
        ),
        "x_mean": float(
            Xj.mean()
        ),
        "x_sd": float(
            Xj.std(ddof=0)
        ),
        "context_item_level_shared": True,
        "phase6_high_assignment_geometry": True,
    }

    return df, diagnostics


def run_r_fit(csv_path: Path, json_path: Path, true_effect: float, fit_spec: str):
    cmd = [
        "Rscript",
        str(PHASE7_RFITTER),
        str(csv_path),
        str(json_path),
        str(true_effect),
        fit_spec,
    ]

    cp = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
    )

    if cp.returncode != 0:
        return {
            "fit_error": (
                f"R_RETURN_CODE_{cp.returncode}: "
                + cp.stderr[-4000:]
            ),
            "converged": False,
            "singular": np.nan,
        }

    if not json_path.exists():
        return {
            "fit_error": "R_JSON_MISSING",
            "converged": False,
            "singular": np.nan,
        }

    try:
        obj = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "fit_error": f"R_JSON_PARSE_ERROR: {e}",
            "converged": False,
            "singular": np.nan,
        }

    obj["fit_error"] = ""

    return obj


def normalize_missing(x):
    if x is None:
        return np.nan

    if isinstance(x, str) and x.strip().upper() in {
        "",
        "NA",
        "NAN",
        "NONE",
        "NULL",
    }:
        return np.nan

    return x


def fit_one(
    rep: int,
    cell: dict,
    fit_spec: str,
    df: pd.DataFrame,
    diagnostics: dict,
    work_dir: Path,
):
    cell_name = cell["cell"]

    csv_path = work_dir / f"r{rep:03d}_{cell_name}.csv"
    json_path = work_dir / f"r{rep:03d}_{cell_name}_{fit_spec}.json"

    # Dataset is written once per fit call, but its SHA is checked across
    # architectures. Content is deterministic and identical.
    df.to_csv(csv_path, index=False)

    dataset_sha = sha256_file(csv_path)

    if json_path.exists():
        json_path.unlink()

    out = run_r_fit(
        csv_path,
        json_path,
        cell["true_effect"],
        fit_spec,
    )

    row = {
        "rep": rep,
        "seed": production_seed(rep),
        "cell": cell_name,
        "fit_spec": fit_spec,
        "true_effect": cell["true_effect"],
        "true_rho": cell["rho_model"],
        "n_models": N_MODELS,
        "n_items": N_ITEMS,
        "n_obs": len(df),
        "dataset_sha256": dataset_sha,
        **diagnostics,
    }

    for k, v in out.items():
        row[k] = normalize_missing(v)

    return row


def validate_block_results(df: pd.DataFrame, block: int):
    start, end = block_bounds(block)

    expected_reps = set(range(start, end + 1))

    if len(df) != BLOCK_SIZE * len(CELLS) * len(FIT_SPECS):
        raise RuntimeError(
            f"Wrong row count: {len(df)}"
        )

    if set(df["rep"].unique()) != expected_reps:
        raise RuntimeError("Replicate set mismatch.")

    if df["cell"].nunique() != 4:
        raise RuntimeError("Expected four cells.")

    if set(df["fit_spec"].unique()) != {"M1", "M2"}:
        raise RuntimeError("Expected M1 and M2.")

    g = df.groupby(["rep", "cell"])

    if not g.size().eq(2).all():
        raise RuntimeError("Expected exactly two fits per rep/cell.")

    if not g["fit_spec"].nunique().eq(2).all():
        raise RuntimeError("M1/M2 pair missing.")

    if not g["dataset_sha256"].nunique().eq(1).all():
        raise RuntimeError("M1/M2 dataset SHA mismatch.")

    # Exact balance.
    if not (df["min_model_n_self"] == 200).all():
        raise RuntimeError("Self balance invariant failed.")

    if not np.isclose(df["overall_self_prop"], 0.5).all():
        raise RuntimeError("Overall Self proportion invariant failed.")

    return True


def block_paths(block: int):
    block_dir = BASE / "phase7_blocks"
    block_dir.mkdir(parents=True, exist_ok=True)

    results = block_dir / f"phase7_block_{block:02d}_results.csv"
    manifest = block_dir / f"phase7_block_{block:02d}_manifest.json"

    return block_dir, results, manifest


def run_block(block: int):
    start, end = block_bounds(block)

    block_dir, results_path, manifest_path = block_paths(block)

    if results_path.exists() or manifest_path.exists():
        raise RuntimeError(
            f"Block {block:02d} already has production artifacts. "
            "Refusing overwrite."
        )

    work_dir = BASE / "_phase7_work" / f"block_{block:02d}"
    work_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    t0 = time.time()

    print(
        f"PHASE 7 BLOCK {block:02d}: reps {start}-{end}; "
        f"expected fits={BLOCK_SIZE * 4 * 2}"
    )

    for rep in range(start, end + 1):
        for cell in CELLS:
            df, dg = make_dataset(
                rep=rep,
                true_effect=cell["true_effect"],
                rho_model=cell["rho_model"],
            )

            # Both architectures receive the same in-memory dataframe.
            for fit_spec in FIT_SPECS:
                row = fit_one(
                    rep,
                    cell,
                    fit_spec,
                    df,
                    dg,
                    work_dir,
                )

                rows.append(row)

        print(
            f"rep={rep:03d} complete "
            f"({len(rows)} fits recorded)",
            flush=True,
        )

    out = pd.DataFrame(rows)

    validate_block_results(out, block)

    # Production results are written only after the whole block passes
    # structural integrity.
    out.to_csv(results_path, index=False)

    results_sha = sha256_file(results_path)

    manifest = {
        "phase": 7,
        "block": block,
        "rep_start": start,
        "rep_end": end,
        "expected_fits": BLOCK_SIZE * 4 * 2,
        "recorded_rows": int(len(out)),
        "results_file": results_path.name,
        "results_sha256": results_sha,
        "runner_sha256": sha256_file(Path(__file__)),
        "r_fitter_sha256": sha256_file(PHASE7_RFITTER),
        "phase6_generator_source_sha256": sha256_file(PHASE6_RUNNER),
        "elapsed_seconds": time.time() - t0,
        "integrity_pass": True,
    }

    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print()
    print("BLOCK COMPLETE — INTEGRITY PASS")
    print("Results:", results_path)
    print("SHA256 :", results_sha)
    print("Manifest:", manifest_path)


def audit_only():
    """
    Zero-fit mechanical audit.
    """
    assert N_MODELS == 100
    assert N_ITEMS == 400
    assert N_REPS == 500
    assert BLOCK_SIZE == 50
    assert N_BLOCKS == 10
    assert PHASE7_BASE_SEED == 92622000

    assert len(CELLS) == 4
    assert FIT_SPECS == ["M1", "M2"]

    assert {
        (x["true_effect"], x["rho_model"])
        for x in CELLS
    } == {
        (0.00, 0.00),
        (0.00, 0.30),
        (0.10, 0.00),
        (0.10, 0.30),
    }

    assert N_REPS * len(CELLS) * len(FIT_SPECS) == 4000

    all_reps = []

    for b in range(1, N_BLOCKS + 1):
        lo, hi = block_bounds(b)
        all_reps.extend(range(lo, hi + 1))

    assert all_reps == list(range(1, 501))

    assert production_seed(1) == 92622001
    assert production_seed(500) == 92622500

    print("PHASE 7 ZERO-FIT RUNNER AUDIT PASS")
    print("Production fits executed: 0")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Mechanical audit only; runs zero GLMM fits.",
    )

    parser.add_argument(
        "--block",
        type=int,
        default=None,
        help="Production block number 1..10.",
    )

    args = parser.parse_args()

    if args.audit_only:
        audit_only()
        return

    if args.block is None:
        raise SystemExit(
            "Refusing to run production without explicit --block 1..10."
        )

    run_block(args.block)


if __name__ == "__main__":
    main()
