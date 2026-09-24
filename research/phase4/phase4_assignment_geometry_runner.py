#!/usr/bin/env python3
"""
PHASE 4 — Assignment-Geometry Intervention
==========================================

Design Lab diagnostic only. NEVER merge into frozen v8.6.3 materials.

Question:
Does assignment geometry materially contribute to M1 singularity?

Hold fixed:
  n_models=24, n_items=100, true_effect=.10 log-odds
  slope_sd=.02, tau_model=.03, tau_item=.03, rho_model=.30
  beta0=.50, beta_x=.15, beta_c=.05

Intervene BEFORE outcome generation:
  OBS_060 : logistic assignment calibrated toward corr(X,is_self)=.60
  OBS_030 : logistic assignment calibrated toward corr(X,is_self)=.30
  RAND_000: randomized Bernoulli(.5), independent of X
  BAL_050 : exactly 50 Self + 50 Control observations within every model

M1 is unchanged:
  y ~ X + context_len + is_self
      + (1 | item_id) + (1 + is_self | model_id)

Pairing:
Within a replication block, all four conditions share X, context,
model/item random effects, assignment uniforms, and outcome uniforms.
Only the assignment rule changes. Outcomes are then generated from each
condition's own assignment BEFORE fitting.

Usage:
  python phase4_assignment_geometry_runner.py --preflight
  python phase4_assignment_geometry_runner.py --full
"""

from pathlib import Path
import argparse, json, math, subprocess, tempfile, traceback
import numpy as np
import pandas as pd
from scipy.optimize import brentq

D = Path("/content/drive/MyDrive/DesignLab")
R_FIT = D / "glmer_fit.R"
WORK = D / "_phase4_work"
WORK.mkdir(parents=True, exist_ok=True)

N_MODELS, N_ITEMS = 24, 100
TRUE_EFFECT = .10
SLOPE_SD, TAU_MODEL, TAU_ITEM, RHO_MODEL = .02, .03, .03, .30
BETA0, BETA_X, BETA_C = .50, .15, .05
BASE_SEED = 92621000
N_REPS = 30

CONDS = [
    ("OBS_060", .60),
    ("OBS_030", .30),
    ("RAND_000", 0.0),
    ("BAL_050", None),
]

def sigmoid(x):
    x=np.asarray(x,float)
    return 1/(1+np.exp(-np.clip(x,-35,35)))

def corr(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float)
    if np.std(a)==0 or np.std(b)==0: return np.nan
    return float(np.corrcoef(a,b)[0,1])

def calibrate_gamma(Xrow, target, Ucal):
    if target == 0: return 0.0
    def rc(g):
        pp=sigmoid(g*Xrow)
        vals=[]
        for u in Ucal:
            z=(u<pp).astype(int)
            vals.append(corr(Xrow,z) if np.std(z)>0 else 0.0)
        return float(np.mean(vals))
    def f(g): return rc(g)-target
    lo,hi=-8.,8.
    flo,fhi=f(lo),f(hi)
    if flo*fhi>0:
        raise RuntimeError(f"Calibration target {target} not bracketed: {flo=}, {fhi=}")
    return float(brentq(f,lo,hi,xtol=1e-3))

def make_shared(seed):
    # Explicit independent substreams make common-random-number pairing exact.
    ss=np.random.SeedSequence(seed)
    sx,sc,sa,sre,si,sy,scal = ss.spawn(7)
    rx=np.random.default_rng(sx); rc=np.random.default_rng(sc)
    ra=np.random.default_rng(sa); rr=np.random.default_rng(sre)
    ri=np.random.default_rng(si); ry=np.random.default_rng(sy)
    rcal=np.random.default_rng(scal)

    logp=rx.uniform(9,12,N_MODELS); Xj=logp-logp.mean()
    context=rc.normal(0,1,N_ITEMS)
    mi,ii=np.meshgrid(np.arange(N_MODELS),np.arange(N_ITEMS),indexing="ij")
    mi,ii=mi.ravel(),ii.ravel()
    Xrow=Xj[mi]; crow=context[ii]

    # One assignment uniform vector is shared across stochastic conditions.
    U=ra.uniform(size=len(mi))
    Ucal=rcal.uniform(size=(5,len(mi)))

    Sigma=np.array([[TAU_MODEL**2,RHO_MODEL*TAU_MODEL*SLOPE_SD],
                    [RHO_MODEL*TAU_MODEL*SLOPE_SD,SLOPE_SD**2]])
    L=np.linalg.cholesky(Sigma)
    re=rr.normal(size=(N_MODELS,2))@L.T
    b0m,u1m=re[:,0],re[:,1]
    b0i=ri.normal(0,TAU_ITEM,N_ITEMS)

    # Shared uniforms for Bernoulli outcome generation.
    Uy=ry.uniform(size=len(mi))
    return dict(mi=mi,ii=ii,Xj=Xj,Xrow=Xrow,crow=crow,U=U,Ucal=Ucal,
                b0m=b0m,u1m=u1m,b0i=b0i,Uy=Uy)

def assign(shared, label, target):
    Xrow=shared["Xrow"]; U=shared["U"]; mi=shared["mi"]
    if label=="BAL_050":
        z=np.zeros(len(mi),dtype=int)
        # Exactly half per model. The 50 smallest shared uniforms become Self.
        for j in range(N_MODELS):
            idx=np.flatnonzero(mi==j)
            chosen=idx[np.argsort(U[idx])[:N_ITEMS//2]]
            z[chosen]=1
        p=np.full(len(mi),.5); gamma=np.nan
    else:
        gamma=calibrate_gamma(Xrow,target,shared["Ucal"])
        p=sigmoid(gamma*Xrow)
        z=(U<p).astype(int)
    return z,p,gamma

def dataset(shared,label,target):
    z,p,gamma=assign(shared,label,target)
    mi,ii=shared["mi"],shared["ii"]
    eta=(BETA0+BETA_X*shared["Xrow"]+TRUE_EFFECT*z+BETA_C*shared["crow"]
         +shared["b0m"][mi]+shared["b0i"][ii]+shared["u1m"][mi]*z)
    py=sigmoid(eta)
    y=(shared["Uy"]<py).astype(int)

    df=pd.DataFrame(dict(model_id=mi,item_id=ii,X=shared["Xrow"],
                         context_len=shared["crow"],is_self=z,y=y))
    pm=df.groupby("model_id").is_self.agg(["sum","mean"])
    ncontrol=N_ITEMS-pm["sum"]
    d=dict(
        realized_corr=corr(df.X,df.is_self),
        gamma_x=gamma,
        p_min=float(p.min()),p_max=float(p.max()),
        pct_p_below_05=float((p<.05).mean()),
        pct_p_above_95=float((p>.95).mean()),
        overall_self_prop=float(z.mean()),
        min_model_n_self=int(pm["sum"].min()),
        min_model_n_control=int(ncontrol.min()),
        min_model_self_prop=float(pm["mean"].min()),
        max_model_self_prop=float(pm["mean"].max()),
        median_model_self_prop=float(pm["mean"].median()),
        corr_model_selfprop_X=corr(pm["mean"].to_numpy(),shared["Xj"]),
        rho_model_realized=corr(shared["b0m"],shared["u1m"]),
    )
    return df,d

def fit_one(df, rep, seed, label):
    csv=WORK/f"r{rep:03d}_{label}.csv"
    js=WORK/f"r{rep:03d}_{label}.json"
    df.to_csv(csv,index=False)
    cmd=["Rscript",str(R_FIT),str(csv),str(js),str(TRUE_EFFECT)]
    cp=subprocess.run(cmd,capture_output=True,text=True)
    if cp.returncode!=0 or not js.exists():
        return {"fit_error":(cp.stderr or cp.stdout or "R fit failed")[-2000:]}
    try:
        out=json.loads(js.read_text())
    except Exception as e:
        return {"fit_error":f"JSON parse: {e}"}
    out["fit_error"]=np.nan
    return out

def bval(v):
    if isinstance(v,bool): return v
    if isinstance(v,str):
        if v.lower()=="true": return True
        if v.lower()=="false": return False
    return np.nan

def fnum(v):
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except: return np.nan

def run(nreps,prefix):
    rows=[]
    for rep in range(1,nreps+1):
        seed=BASE_SEED+rep
        sh=make_shared(seed)
        for label,target in CONDS:
            try:
                df,dg=dataset(sh,label,target)
                ft=fit_one(df,rep,seed,label)
                row=dict(rep=rep,seed=seed,condition=label,target_corr=target,
                         n_models=N_MODELS,n_items=N_ITEMS,true_effect=TRUE_EFFECT,
                         slope_sd=SLOPE_SD,tau_model=TAU_MODEL,tau_item=TAU_ITEM,
                         rho_model=RHO_MODEL,**dg,**ft)
            except Exception as e:
                row=dict(rep=rep,seed=seed,condition=label,target_corr=target,
                         fit_error=f"{type(e).__name__}: {e}")
            rows.append(row)
            print(f"rep {rep:02d}/{nreps} {label:8s} "
                  f"r={row.get('realized_corr',np.nan): .3f} "
                  f"singular={row.get('singular',np.nan)} "
                  f"error={pd.notna(row.get('fit_error'))}",flush=True)

    r=pd.DataFrame(rows)
    raw=D/f"{prefix}_results.csv"; r.to_csv(raw,index=False)

    # Fail closed before summaries.
    expected=nreps*4
    errors=int(r.fit_error.notna().sum())
    if len(r)!=expected or errors:
        print(f"\nSTOP: rows={len(r)}/{expected}; fit errors={errors}")
        print("Raw checkpoint written:",raw)
        return

    # Pairing integrity.
    g=r.groupby("rep")
    pairing=(g.size().eq(4).all() and g.condition.nunique().eq(4).all()
             and g.seed.nunique().eq(1).all())
    if not pairing: raise RuntimeError("Pairing integrity failed")

    # Component flags from raw diagnostics.
    r["singular_bool"]=r["singular"].map(bval)
    for col in ["model_slope_sd","model_intercept_sd","item_intercept_sd",
                "model_intercept_slope_corr","estimate","bias","se","p_value",
                "ci_low","ci_high"]:
        if col in r: r[col+"_num"]=r[col].map(fnum)
    if "model_slope_sd_num" in r: r["slope_zero"]=r.model_slope_sd_num.lt(1e-4)
    if "model_intercept_sd_num" in r: r["model_zero"]=r.model_intercept_sd_num.lt(1e-4)
    if "item_intercept_sd_num" in r: r["item_zero"]=r.item_intercept_sd_num.lt(1e-4)
    if "model_intercept_slope_corr_num" in r:
        r["corr_boundary"]=r.model_intercept_slope_corr_num.abs().gt(.999)

    summary=[]
    for label,_ in CONDS:
        q=r[r.condition==label]
        def mean(c): return float(q[c].mean()) if c in q else np.nan
        def med(c): return float(q[c].median()) if c in q else np.nan
        summary.append(dict(
            condition=label,n=len(q),
            mean_realized_corr=mean("realized_corr"),
            mean_overall_self_prop=mean("overall_self_prop"),
            median_min_model_n_self=med("min_model_n_self"),
            median_min_model_n_control=med("min_model_n_control"),
            mean_corr_model_selfprop_X=mean("corr_model_selfprop_X"),
            singular_fit_rate=mean("singular_bool"),
            slope_zero_rate=mean("slope_zero"),
            model_zero_rate=mean("model_zero"),
            item_zero_rate=mean("item_zero"),
            corr_boundary_rate=mean("corr_boundary"),
            mean_estimate=mean("estimate_num"),
            mean_bias=mean("bias_num"),
            median_se=med("se_num"),
        ))
    s=pd.DataFrame(summary)
    sp=D/f"{prefix}_summary.csv"; s.to_csv(sp,index=False)

    # One row per rep: paired singular states + assignment geometry.
    wide=r.pivot(index="rep",columns="condition",
                 values=["singular_bool","realized_corr","min_model_n_self",
                         "min_model_n_control","corr_model_selfprop_X"])
    wide.columns=["__".join(map(str,c)) for c in wide.columns]
    wide=wide.reset_index()
    pp=D/f"{prefix}_paired.csv"; wide.to_csv(pp,index=False)

    # Save enriched raw results too.
    r.to_csv(raw,index=False)

    print("\n"+"="*72)
    print("PHASE 4 COMPLETE — INTEGRITY PASS")
    print("="*72)
    print(f"fits: {len(r)}/{expected}; errors: {errors}; paired blocks: {nreps}")
    print(s.to_string(index=False))
    print("\nFiles:")
    print(raw.name); print(sp.name); print(pp.name)

def main():
    ap=argparse.ArgumentParser()
    x=ap.add_mutually_exclusive_group(required=True)
    x.add_argument("--preflight",action="store_true")
    x.add_argument("--full",action="store_true")
    a=ap.parse_args()
    if not R_FIT.exists(): raise FileNotFoundError(f"Missing {R_FIT}")
    if a.preflight:
        run(1, "phase4_preflight")
    else:
        run(N_REPS, "phase4")

if __name__=="__main__":
    main()
