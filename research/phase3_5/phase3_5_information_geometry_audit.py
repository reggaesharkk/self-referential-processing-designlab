#!/usr/bin/env python3
from pathlib import Path
import importlib.util, numpy as np, pandas as pd

D=Path("/content/drive/MyDrive/DesignLab"); G=D/"confound_generator.py"
BASE=92620000

def loadgen():
    s=importlib.util.spec_from_file_location("g",G); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def corr(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float); ok=np.isfinite(a)&np.isfinite(b)
    a,b=a[ok],b[ok]
    return np.nan if len(a)<3 or np.std(a)==0 or np.std(b)==0 else float(np.corrcoef(a,b)[0,1])
def z(a):
    a=np.asarray(a,float); sd=np.std(a); return np.zeros_like(a) if sd==0 else (a-np.mean(a))/sd
def summ(s):
    s=pd.to_numeric(s,errors="coerce").dropna()
    return dict(mean=s.mean(),sd=s.std(),min=s.min(),q05=s.quantile(.05),q25=s.quantile(.25),
                median=s.median(),q75=s.quantile(.75),q95=s.quantile(.95),max=s.max())

g=loadgen(); ds=[]; ms=[]
print("="*70); print("PHASE 3.5 — INFORMATION-GEOMETRY AUDIT (NO GLMM FITTING)"); print("="*70)
for rep in range(1,31):
    seed=BASE+rep
    o=g.generate_scenario(n_models=24,n_items=100,target_corr=.60,true_effect=.10,
                          slope_sd=.02,tau_model=.03,tau_item=.03,rho_model=.30,seed=seed)
    d=g.scenario_to_dataframe(o).copy(); dg=o.get("diagnostics",{}) or {}
    need={"model_id","item_id","X","context_len","is_self","y"}
    if need-set(d): raise RuntimeError(f"rep {rep}: missing {need-set(d)}")
    if len(d)!=2400: raise RuntimeError(f"rep {rep}: {len(d)} rows, expected 2400")

    pm=d.groupby("model_id").agg(n=("is_self","size"),n_self=("is_self","sum"),
        self_prop=("is_self","mean"),y_mean=("y","mean"),X_mean=("X","mean"),
        context_mean=("context_len","mean")).reset_index()
    pm["n_control"]=pm.n-pm.n_self
    pm["both_levels"]=(pm.n_self>0)&(pm.n_control>0)
    pm["self_within_ss"]=pm.n*pm.self_prop*(1-pm.self_prop)
    pm["rep"]=rep; pm["seed"]=seed; ms.append(pm)

    # Fixed design matrix geometry.
    X=np.column_stack([np.ones(len(d)),z(d.X),z(d.context_len),d.is_self.to_numpy(float)])
    sv=np.linalg.svd(X,compute_uv=False); rank=np.linalg.matrix_rank(X)
    cond=float(sv[0]/sv[-1]) if sv[-1]>1e-12 else np.inf

    # is_self residual information after X/context.
    C=np.column_stack([np.ones(len(d)),z(d.X),z(d.context_len)])
    yy=d.is_self.to_numpy(float); bh=np.linalg.lstsq(C,yy,rcond=None)[0]; rr=yy-C@bh
    gm=d.groupby("model_id").is_self.transform("mean").to_numpy(float)
    within=yy-gm

    ds.append(dict(rep=rep,seed=seed,n_rows=len(d),n_models=d.model_id.nunique(),
        n_items=d.item_id.nunique(),overall_self_prop=d.is_self.mean(),
        min_model_self_prop=pm.self_prop.min(),median_model_self_prop=pm.self_prop.median(),
        max_model_self_prop=pm.self_prop.max(),sd_model_self_prop=pm.self_prop.std(),
        min_model_n_self=pm.n_self.min(),max_model_n_self=pm.n_self.max(),
        min_model_n_control=pm.n_control.min(),max_model_n_control=pm.n_control.max(),
        n_models_missing_one_self_level=(~pm.both_levels).sum(),
        min_model_self_within_ss=pm.self_within_ss.min(),
        median_model_self_within_ss=pm.self_within_ss.median(),
        corr_is_self_X=corr(d.is_self,d.X),
        corr_is_self_context=corr(d.is_self,d.context_len),
        corr_X_context=corr(d.X,d.context_len),
        corr_model_selfprop_Xmean=corr(pm.self_prop,pm.X_mean),
        corr_model_selfprop_contextmean=corr(pm.self_prop,pm.context_mean),
        fixed_X_rank=rank,fixed_X_ncols=X.shape[1],fixed_X_condition_number=cond,
        self_within_total_ss=np.sum(within**2),self_within_variance=np.var(within),
        self_residual_variance_after_X_context=np.var(rr),
        realized_corr=dg.get("realized_corr"),rho_model_realized=dg.get("rho_model_realized"),
        near_separation=dg.get("near_separation"),p_min=dg.get("p_min"),p_max=dg.get("p_max")))
    print(f"[{rep:02d}/30] seed={seed} self={d.is_self.mean():.3f} "
          f"p-range={pm.self_prop.min():.3f}..{pm.self_prop.max():.3f} "
          f"min counts={int(pm.n_self.min())}/{int(pm.n_control.min())} cond={cond:.2f}")

ds=pd.DataFrame(ds); ms=pd.concat(ms,ignore_index=True)
metrics=[c for c in ds.columns if c not in {"rep","seed","near_separation"}]
summary=pd.DataFrame([{"metric":c,**summ(ds[c])} for c in metrics])
cors=pd.DataFrame([
 {"relationship":"model self proportion vs model X mean","correlation":corr(ms.self_prop,ms.X_mean)},
 {"relationship":"model self proportion vs model context mean","correlation":corr(ms.self_prop,ms.context_mean)},
 {"relationship":"model self proportion vs model outcome mean","correlation":corr(ms.self_prop,ms.y_mean)},
 {"relationship":"within-model self information vs self proportion","correlation":corr(ms.self_within_ss,ms.self_prop)}])

if len(ds)!=30 or len(ms)!=720 or ds.seed.nunique()!=30: raise RuntimeError("Integrity failure")
paths=[D/"phase3_5_dataset_audit.csv",D/"phase3_5_model_audit.csv",D/"phase3_5_summary.csv",D/"phase3_5_correlations.csv"]
for x,q in zip([ds,ms,summary,cors],paths): x.to_csv(q,index=False)

print("\n"+"="*70); print("PHASE 3.5 COMPLETE — INTEGRITY PASS"); print("="*70)
print("Datasets:",len(ds)," Model-within-dataset rows:",len(ms))
for c in ["overall_self_prop","min_model_self_prop","max_model_self_prop","min_model_n_self",
          "min_model_n_control","n_models_missing_one_self_level","min_model_self_within_ss",
          "corr_is_self_X","corr_is_self_context","fixed_X_condition_number",
          "self_within_variance","self_residual_variance_after_X_context"]:
    r=summary.set_index("metric").loc[c]
    print(f"{c:40s} mean={r['mean']:.6g} min={r['min']:.6g} median={r['median']:.6g} max={r['max']:.6g}")
print("\n",cors.to_string(index=False))
print("\nUpload all FOUR CSVs to ChatGPT. Do NOT start Phase 4 yet.")
