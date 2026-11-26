# My Pilot B receipts

I preserve each supplied live Pilot B result as a separate, byte-checked record. I keep the source ZIP, extracted output files, and a SHA-256 manifest for each archived execution. The index manifest covers this README, my first standalone receipt, and each run-level manifest; each run manifest covers that run's source archive, extracted files, and reconciliation note. I do not replace an earlier receipt with output from a later script version.

## First receipt

I archived the first receipt from `v9_0_pilot_b_results (17).zip`. It records 10 calls, 10 responses, USD 0.00053603 estimated spend, and `TR_01`. Its source ZIP and receipt hashes are recorded in this directory. The receipt is a prospective Pilot B execution, not confirmatory data.

## Second receipt

I archived the second receipt from `v9_0_pilot_b_results.zip` in [`2026-11-26_run_2/`](2026-11-26_run_2/). Its ZIP SHA-256 is `1a1cd21d6abbda29426a60e4e65135ab0311ac3e10139d207e917b85ed0c7188`. The execution started 30 calls and received 30 HTTP 200 responses; its estimated spend was USD 0.00119524. The ledger contains calls for `TR_01` and `TR_02`, and the final summary marks all four model slots unavailable. I count it as a live but incomplete prospective Pilot B execution, not a completed five-item pilot or a confirmatory run.

## Third receipt

I archived the supplied `v9_0_pilot_b_results (1).zip` in [`2026-11-26_run_3/`](2026-11-26_run_3/). The source ZIP's measured SHA-256 is `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430600`. The request stated `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430680`; I recorded that discrepancy alongside the byte-preserved source archive. The ZIP's internal six-file SHA-256 list verifies.

The third execution records 80 calls, 80 HTTP 200 responses, and USD 0.00494411 estimated spend. Gemma (`google/gemma-2-27b-it`) completed 25/25 item-stage pairs across all five items. Llama (`meta-llama/llama-3.3-70b-instruct`) completed 17/25 pairs and all five stages for `TR_01`–`TR_03`. Qwen completed 2 pairs and Mistral 7 pairs. I classify this as a partial prospective Pilot B execution with one model completing the five-item pipeline; it is not confirmatory data.

## Fourth receipt

I archived the supplied v9_0_pilot_b_results (3).zip in [2026-11-26_run_4/](2026-11-26_run_4/). Its SHA-256 is 50618f7279799d08f562490455f261bd024094617b72f95ca9d37f799f116f1b, matching the supplied digest. The receipt records 70 calls, 70 HTTP 200 responses, USD 0.00350597 estimated spend, and USD 0.02412054 pre-request reservation. Gemma and Mistral each completed 25/25 item-stage pairs with complete_pipeline: true; Qwen and Llama each completed 2 pairs. Confirmatory data collected is false.

Across the four receipts, I recorded 190 calls, 190 responses, and USD 0.01018135 estimated spend. I found no Pilot A run and no confirmatory study run. I keep all engineering connectivity checks separate from Pilot B.
