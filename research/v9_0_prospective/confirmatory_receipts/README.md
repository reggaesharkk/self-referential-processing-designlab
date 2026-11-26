# My confirmatory run receipts

I preserve supplied confirmatory run archives, extracted files, reconciliations, and SHA-256 manifests here. I keep an unsuccessful or partial run as its own immutable record; I do not rewrite its result when I change the runner.

## Run 1 — partial, HTTP 402

I archived the supplied v9_0_confirmatory_results.zip in 2026-11-26_run_1_partial_402/. The measured source ZIP SHA-256 is 3c95c500177a6960a791eaa2633e96ac7c0a270abefa2956a549faf92b6d9f3c and the included result hash matches d83caec7364395005fd1fc5fd1ac61332cbd650c5cb74b3e322a2a205955fa7f.

The receipt records 180 calls (176 HTTP 200, four HTTP 402) and USD 0.01704482 estimated spend. Qwen completed 27 full item pipelines and three stages on TR_28; the other three slots each received an HTTP 402 on TR_01 Phase 0. Its report has no halt reason and stopped_early is false, so the saved evidence shows that the prior runner made three additional calls after the first 402. I corrected the runner to stop immediately on a 402. I keep the four successful connectivity probes separate from pipeline calls.


I preserved the run 1 receipt unchanged and added a replay-checked resume path in `confirmatory_v9.py` and my Colab notebook. The local cap remains USD 1.25 across the original and resumed calls. The attached account screenshot shows USD 49.80 remaining on a USD 50 weekly key limit; it does not remove the separate HTTP 402 provider-credit boundary.
