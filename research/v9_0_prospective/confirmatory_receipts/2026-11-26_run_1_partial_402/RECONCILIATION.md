# My confirmatory run 1 receipt — partial, HTTP 402

I preserved the supplied ZIP byte-for-byte. Its measured SHA-256 is 3c95c500177a6960a791eaa2633e96ac7c0a270abefa2956a549faf92b6d9f3c. The ZIP passed its integrity test, and all six entries in its internal SHA256SUMS.txt match.

The included confirmatory_v9_result.json SHA-256 is d83caec7364395005fd1fc5fd1ac61332cbd650c5cb74b3e322a2a205955fa7f. The archive records 180 pipeline calls and responses: 176 HTTP 200 and four HTTP 402, with USD 0.01704482 estimated spend and USD 0.10182801 pre-request reservation against the configured USD 1.25 cap.

Qwen completed TR_01–TR_27. The receipt counts 138 successful item-stage pairs: 135 across those 27 complete items and three completed stages on TR_28 before Phase 1 returned HTTP 402. The receipt then records one HTTP 402 at Phase 0 for each remaining slot on TR_01. Gemma, Llama, and Mistral did not complete an item pipeline.

I preserve the evidence as received. The result JSON has stopped_early=false and halt_reason=null, and its call ledger contains four HTTP 402 responses. The request description said the run halted cleanly on the first HTTP 402 at Qwen TR_28 Phase 1; the archived output shows three further Phase 0 calls. I am recording that mismatch because it identifies the fail-fast defect corrected in the runner.

The ZIP also contains four separate engineering connectivity probes; all four were HTTP 200. I count those separately from the 180 confirmatory pipeline calls. The receipt classifies the run as prospective_confirmatory_study and sets confirmatory_data_collected=true.

I did not edit the supplied result files, the frozen v8.6.3 files, or items_pool_v1.json.
