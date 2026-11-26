# My live-run accountability addendum — 26 November 2026

I prepared this addendum after receiving the second `v9_0_pilot_b_results.zip`. The earlier audit counted the first 10-call receipt because this newer results archive was not then available. I have now reconciled both receipts, the new four-call connectivity result, and the published PSI live-result files.

## Counts I can substantiate

| Category | My evidence-backed count | Record |
| --- | ---: | --- |
| 27 September engineering connectivity POST probes | 6: 4 HTTP 200, 1 HTTP 400, 1 HTTP 404 | Earlier provider diagnostics; non-study prompts |
| 26 November v9 connectivity probes | 4: all HTTP 200 | `api_ping_check_v9.json`; engineering checks only |
| Engineering connectivity probes total | 10: 8 HTTP 200, 1 HTTP 400, 1 HTTP 404 | I count these separately from pilots |
| Pilot A executions | 0 | I found no Pilot A receipt |
| Prospective Pilot B executions | 2 | One 10-call receipt and one 30-call receipt |
| Pilot B calls / responses | 40 / 40 | 10 + 30 |
| Pilot B estimated spend | USD 0.00173127 | USD 0.00053603 + USD 0.00119524 |
| Confirmatory study executions | 0 | Neither Pilot B receipt records confirmatory data |
| Provider catalog metadata GETs | 3 | I count these as metadata requests, not inference calls |
| PSI live Colab benchmark executions | 1 | Five model rows; four local T4 rows and one Groq API row |

I count 50 documented DesignLab model-inference POST calls: 10 connectivity probes plus 40 Pilot B calls. I count 53 documented DesignLab provider requests when I add the three catalog GETs. The PSI release confirms one live benchmark execution, but its published files do not include a request ledger, so I cannot state an exact external API-call count for PSI.

## What happened in my second Pilot B execution

I received 30 HTTP responses, all with status 200, and the receipt estimates USD 0.00119524 in spend against the USD 0.25 cap. The ledger contains calls for `TR_01` and `TR_02`; it contains no call records for `TR_03` through `TR_05`. The final summary marks all four model slots unavailable. Fourteen of the 30 call records are marked unavailable: 13 carry the style-scrub word-window blocker and one carries `finish_reason_length`. I therefore record this as a live but incomplete Pilot B execution, not a completed five-item pilot.

The four separate v9 connectivity checks returned HTTP 200 and recorded `finish_reason: stop`, with no reported reasoning tokens. I classify them as engineering probes, not study runs.

## PSI run record

I found one published PSI v5.0 live Colab execution dated `2026-11-25T21:08:18.171266+00:00`. The release contains five model result rows: four local T4 GPU results and one Groq API result. It does not contain a request ledger that supports an exact Groq HTTP-call total. I preserve this run in PSI and do not include unknown PSI API requests in my DesignLab totals.

## Colab bundle I rebuilt

I preserved my earlier Colab bundle in the D: audit folder at SHA-256 `0be63f216f3496c2f4a1efc12397aa45e13e2c362eddb47937edbe78488b0035`. I rebuilt `D:\v9_0_colab_pilot_bundle.zip` from my current v9 runner, both Pilot B receipt folders, the verified item pool, and the one-code-cell notebook. The new bundle contains 24 files, retains the pool at its verified SHA-256, and has SHA-256 `b75967165449abcdc6feab026839d7b3ae928376b84f25e46d03739236e60c3b`. I found zero provider-key-shaped values in the bundle or its nested source archive.

## Source records and hashes

- First Pilot B source archive: `v9_0_pilot_b_results (17).zip`; SHA-256 `7d0d9103e112288137bd52cc315f0560b0f20df45c23e70cb2140e888902b4a7`.
- First Pilot B receipt: SHA-256 `db82e60bf1aaffa3ecd76909c34aa1a90160224d5e2b5f8f6b3afb346fcdcfc3`.
- Second Pilot B source archive: `v9_0_pilot_b_results.zip`; SHA-256 `1a1cd21d6abbda29426a60e4e65135ab0311ac3e10139d207e917b85ed0c7188`.
- Second Pilot B receipt: SHA-256 `127a8dc8e1125ec43a41cb60255b3e6baddfa0ad612721228a98970b7b786443`.
- Second connectivity result: SHA-256 `1476ac940e27fe77dd2d391b5e94e1cfe79383ab6a07418dcb2087b6b3a75d59`.
- Item pool: 75,875 bytes; SHA-256 `128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3`; I left it outside Git and did not modify it.

I verified the second source ZIP's internal `SHA256SUMS.txt` against its six result files. I scanned the source ZIP and receipt outputs for provider-key-shaped values and found none. I did not read or log an API key. I did not send any provider requests while preparing this addendum. I did not modify frozen v8.6.3 files.

These are counts from records I found, not provider billing data. I did not query provider-side activity logs, so I cannot exclude calls that were not saved in the local evidence.
