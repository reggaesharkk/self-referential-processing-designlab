# My live-run accountability addendum — 26 November 2026, run 4

I updated this addendum after receiving my fourth Pilot B archive. I reconciled all four local receipts, the September and November engineering probes, and the published PSI live-result files. These are counts I can substantiate from saved records, not provider billing data.

## Counts I can substantiate

| Category | My evidence-backed count | Record |
| --- | ---: | --- |
| 27 September engineering connectivity POST probes | 6: 4 HTTP 200, 1 HTTP 400, 1 HTTP 404 | Non-study provider diagnostics |
| 26 November v9 connectivity probes | 4: all HTTP 200 | Engineering checks only |
| Engineering connectivity probes total | 10: 8 HTTP 200, 1 HTTP 400, 1 HTTP 404 | I count these separately from pilots |
| Pilot A executions | 0 | I found no Pilot A receipt |
| Prospective Pilot B executions | 4 | 10, 30, 80, and 70-call receipts |
| Pilot B calls / responses | 190 / 190 | 10 + 30 + 80 + 70 |
| Pilot B estimated spend | USD 0.01018135 | USD 0.00053603 + USD 0.00119524 + USD 0.00494411 + USD 0.00350597 |
| Confirmatory study executions | 0 | No receipt records confirmatory data |
| Provider catalog metadata GETs | 3 | I count these separately from POST calls |
| PSI live Colab benchmark executions | 1 | Five model rows; four local T4 rows and one Groq API row |

I count 200 documented Design Lab model-inference POST requests: 10 engineering connectivity probes plus 190 Pilot B calls. I count 203 provider HTTP requests when I add the three catalog GETs. The PSI release confirms one live benchmark execution, but its published files do not include a request ledger, so I cannot state an exact external API-call count for PSI.

## What happened in my third Pilot B execution

I received 80 HTTP responses, all status 200, and the receipt estimates USD 0.00494411 in spend against the USD 0.25 cap; the pre-request reservation total was USD 0.03063528. Gemma completed all 25 item-stage pairs across `TR_01`–`TR_05` in 33 calls. Llama completed 17 of 25 pairs in 31 calls, with `TR_01`–`TR_03` fully complete. Qwen completed two pairs in seven calls; Mistral completed seven pairs in nine calls. I classify the run as partial model coverage with one complete five-item pipeline, not a confirmatory study.

The receipt shows why I changed the style-scrub prompt and cap. Mistral's `TR_02` repair 1 stopped at `finish_reason: length` with 128 output tokens and a 99-word rewrite. Qwen's `TR_01` repairs plateaued at 39 words, and Llama reached 44 words on `TR_04`. The runner now allows 192 style-scrub output tokens and instructs both the initial rewrite and repairs to produce three plain, neutral sentences totaling strictly 48–52 whitespace-separated words, within a 45–55 acceptance window. The evaluation stages remain locked at 16 tokens.

The request accompanying `v9_0_pilot_b_results (1).zip` stated SHA-256 `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430680`. The supplied file I received hashes to `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430600`. I preserved the supplied bytes and recorded the measured digest; I do not report the requested digest as the file's checksum. The ZIP passed its integrity check, and all six entries in its internal `SHA256SUMS.txt` matched. Its `pilot_b_v9_result.json` SHA-256 is `c6c19b5db0def4f4f4e4a5134fb4cac5f622a3659856fe5294c4fc068e56b3c2`.

## Earlier DesignLab and PSI records

My first Pilot B receipt records 10 calls, 10 responses, and USD 0.00053603 estimated spend for `TR_01`. My second records 30 calls, 30 HTTP 200 responses, and USD 0.00119524 estimated spend; its two-item ledger ended with all four model slots unavailable. I keep both earlier records unchanged.

The four separate v9 connectivity checks returned HTTP 200 and recorded `finish_reason: stop`, with no reported reasoning tokens. I classify them as engineering probes, not study runs. I found no Pilot A receipt and no confirmatory study execution.

I found one published PSI v5.0 live Colab execution dated `2026-11-25T21:08:18.171266+00:00`. The release contains five model result rows: four local T4 GPU results and one Groq API result. It does not contain a request ledger supporting an exact Groq HTTP-call total. I preserve this run in PSI and do not include unknown PSI API requests in my DesignLab totals.

## What happened in my fourth Pilot B execution

I received 70 HTTP responses, all status 200, and the receipt estimates USD 0.00350597 in spend against the USD 0.25 cap; the pre-request reservation total was USD 0.02412054. Gemma completed all 25 item-stage pairs across TR_01–TR_05 in 26 calls. Mistral completed all 25 pairs in 30 calls. Qwen completed two pairs and Llama completed two pairs. I classify this as a prospective Pilot B execution with two complete five-item model pipelines, not a confirmatory study.

The source ZIP v9_0_pilot_b_results (3).zip measures to SHA-256 50618f7279799d08f562490455f261bd024094617b72f95ca9d37f799f116f1b, which matches the digest supplied to me. The extracted pilot_b_v9_result.json measures to SHA-256 32a7b3323613f2ac99ee80791916b5b124093a28ad6048b8966e34221e2b7c74.

## Bundle and source records

Before run 3, I rebuilt `D:\v9_0_colab_pilot_bundle.zip` at SHA-256 `a723d402114dd5114836618d13f6f81ebd9843471cd8061c5f5bce5d34938772`. I preserve that version in the D: audit folder before replacing it. I do not put the next bundle's digest in this ledger because the ledger itself is packaged in that bundle; I record the new digest outside the archive after building it.

- First Pilot B source archive: `v9_0_pilot_b_results (17).zip`; SHA-256 `7d0d9103e112288137bd52cc315f0560b0f20df45c23e70cb2140e888902b4a7`.
- First Pilot B receipt: SHA-256 `db82e60bf1aaffa3ecd76909c34aa1a90160224d5e2b5f8f6b3afb346fcdcfc3`.
- Second Pilot B source archive: `v9_0_pilot_b_results.zip`; SHA-256 `1a1cd21d6abbda29426a60e4e65135ab0311ac3e10139d207e917b85ed0c7188`.
- Second Pilot B receipt: SHA-256 `127a8dc8e1125ec43a41cb60255b3e6baddfa0ad612721228a98970b7b786443`.
- Third Pilot B source archive: `v9_0_pilot_b_results (1).zip`; measured SHA-256 `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430600`; digest stated in the request `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430680`.
- Third Pilot B receipt: SHA-256 `c6c19b5db0def4f4f4e4a5134fb4cac5f622a3659856fe5294c4fc068e56b3c2`.
- Fourth Pilot B source archive: v9_0_pilot_b_results (3).zip; SHA-256 50618f7279799d08f562490455f261bd024094617b72f95ca9d37f799f116f1b.
- Fourth Pilot B receipt: SHA-256 32a7b3323613f2ac99ee80791916b5b124093a28ad6048b8966e34221e2b7c74.
- Item pool: 75,875 bytes; SHA-256 `128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3`; I left it outside Git and did not modify it.

I scanned the new source archive's receipt artifacts for credential-shaped values and found none. I did not read or log an API key and sent no provider requests while preparing this addendum. I did not modify frozen v8.6.3 files. I did not query provider-side activity logs, so unrecorded calls cannot be excluded.
