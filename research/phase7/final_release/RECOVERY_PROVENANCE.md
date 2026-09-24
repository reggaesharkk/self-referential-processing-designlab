# Phase 7 Recovery Provenance

Incident: Phase 7 Blocks 02-10 R environment dependency failure

Discovery: Post-aggregation diagnostic showed that Blocks 02-10 contained result records but no GLMM estimates because R returned code 1: package 'lme4' was unavailable.

Affected replicates: 51-500
Affected blocks: 02-10
Affected result rows: 3600

Block 01: Preserved; reps 1-50 contained completed inferential outputs and will not be rerun.

Recovery rule: Restore required R dependency and rerun only originally failed prespecified Blocks 02-10 using unchanged frozen Phase 7 sources and original deterministic seeds.

Disclosure: An accidental partial aggregate summary based on the 50 evaluable Block 01 replicates was observed before recovery. No Phase 7 source code or statistical specification was changed afterward.

No frozen Phase 7 source hash changed during recovery. The final aggregation was generated only after all ten active production blocks passed integrity checks.
