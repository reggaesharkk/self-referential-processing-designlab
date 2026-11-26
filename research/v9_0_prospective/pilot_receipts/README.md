# My Pilot B receipts

I preserve each supplied live Pilot B result as a separate, byte-checked record. I keep the source ZIP, extracted output files, and a SHA-256 manifest for each archived execution. The index manifest covers this README and the receipt-level manifest files; each run manifest covers that run's source archive, extracted files, and reconciliation note. I do not replace an earlier receipt with output from a later script version.

## First receipt

I archived the first receipt from `v9_0_pilot_b_results (17).zip`. It records 10 calls, 10 responses, USD 0.00053603 estimated spend, and `TR_01`. Its source ZIP and receipt hashes are recorded in this directory. The receipt is a prospective Pilot B execution, not confirmatory data.

## Second receipt

I archived the second receipt from `v9_0_pilot_b_results.zip` in [`2026-11-26_run_2/`](2026-11-26_run_2/). Its ZIP SHA-256 is `1a1cd21d6abbda29426a60e4e65135ab0311ac3e10139d207e917b85ed0c7188`. The execution started 30 calls and received 30 HTTP 200 responses; its estimated spend was USD 0.00119524. The ledger contains calls for `TR_01` and `TR_02`, and the final summary marks all four model slots unavailable. I count it as a live but incomplete prospective Pilot B execution, not a completed five-item pilot or a confirmatory run.

## Third receipt

I archived the supplied `v9_0_pilot_b_results (1).zip` in [`2026-11-26_run_3/`](2026-11-26_run_3/). The source ZIP's measured SHA-256 is `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430600`. The request stated `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430680`; I recorded that discrepancy alongside the byte-preserved source archive. The ZIP's internal six-file SHA-256 list verifies.

The third execution records 80 calls, 80 HTTP 200 responses, and USD 0.00494411 estimated spend. Gemma (`google/gemma-2-27b-it`) completed 25/25 item-stage pairs across all five items. Llama (`meta-llama/llama-3.3-70b-instruct`) completed 17/25 pairs and all five stages for `TR_01`–`TR_03`. Qwen completed 2 pairs and Mistral 7 pairs. I classify this as a partial prospective Pilot B execution with one model completing the five-item pipeline; it is not confirmatory data.

Across the three receipts, I recorded 120 calls and USD 0.00667538 estimated spend. The same evidence includes no Pilot A run and no confirmatory study run. I keep the four v9 connectivity probes separate from Pilot B.
