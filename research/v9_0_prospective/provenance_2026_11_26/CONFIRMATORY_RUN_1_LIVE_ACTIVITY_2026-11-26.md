# My confirmatory run 1 live activity — 26 November 2026

I archived my supplied partial confirmatory ZIP in `confirmatory_receipts/2026-11-26_run_1_partial_402/` and kept the source ZIP and result records unchanged. The source ZIP SHA-256 is `3c95c500177a6960a791eaa2633e96ac7c0a270abefa2956a549faf92b6d9f3c`; the included result SHA-256 is `d83caec7364395005fd1fc5fd1ac61332cbd650c5cb74b3e322a2a205955fa7f`.

I count 180 confirmatory pipeline responses: 176 HTTP 200 and four HTTP 402, USD 0.01704482 estimated spend, and USD 0.10182801 reserved against my USD 1.25 cap. Qwen completed 27 items (TR_01–TR_27) and three stages on TR_28, giving 138 successful item-stage pairs. Gemma, Llama, and Mistral received an HTTP 402 on TR_01 Phase 0 and completed zero items.

The result JSON says `stopped_early=false` and `halt_reason=null`, but the call ledger shows the first HTTP 402 at Qwen/TR_28/Phase 1 followed by one Phase 0 HTTP 402 for each other slot. I preserve this mismatch as evidence of the prior runner's behavior. My updated runner and connectivity probe now stop after the first HTTP 402.

I count four connectivity probes separately; all four returned HTTP 200. This makes November v9 engineering probes 24, and all September/November engineering probes 30 total (28 HTTP 200, one 400, one 404). Together with 317 Pilot B calls and 540 Pilot A calls, I count 1,067 documented DesignLab POST requests and three provider catalog GETs. I have one partial confirmatory execution, so confirmatory data collection has begun; I have not completed the 260-item confirmatory run.

The screenshot I was given shows a USD 50 weekly API-key limit, USD 0.20 used, and USD 49.80 remaining. I keep the local pipeline cap at USD 1.25 because it is the lower limit. The USD 0.2005 provider wallet amount was reported to me and was not independently queried; it is a separate credit balance. The earlier USD 0.10182801 reservation leaves USD 1.14817199 of reservation headroom under my aggregate cap. A resume run carries that reservation forward and skips the 27 completed Qwen item pairs after verifying the item-pool hash and successful stage records.

I ran 17 offline unit tests and a resume dry run. I sent no external provider calls and read or logged no API keys while making this update. I did not modify frozen v8.6.3 files or `items_pool_v1.json`.
