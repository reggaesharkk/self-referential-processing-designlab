# My Pilot B receipts

I preserve each supplied live Pilot B result as a separate, byte-checked record. I keep the source ZIP, extracted output files, and a SHA-256 manifest for each archived execution. I do not replace an earlier receipt with output from a later script version.

## First receipt

I archived the first receipt from `v9_0_pilot_b_results (17).zip`. It records 10 calls, 10 responses, USD 0.00053603 estimated spend, and `TR_01`. Its source ZIP and receipt hashes are recorded in this directory. The receipt is a prospective Pilot B execution, not confirmatory data.

## Second receipt

I archived the second receipt from `v9_0_pilot_b_results.zip` in [`2026-11-26_run_2/`](2026-11-26_run_2/). Its ZIP SHA-256 is `1a1cd21d6abbda29426a60e4e65135ab0311ac3e10139d207e917b85ed0c7188`. The execution started 30 calls and received 30 HTTP 200 responses; its estimated spend was USD 0.00119524. The ledger contains calls for `TR_01` and `TR_02`, and the final summary marks all four model slots unavailable. I count it as a live but incomplete prospective Pilot B execution, not a completed five-item pilot or a confirmatory run.

The same archive records four engineering connectivity probes; all four returned HTTP 200. I keep those probes separate from Pilot B.
