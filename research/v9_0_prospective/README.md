# My prospective v9 runner

I keep my connectivity check, Pilot B and Pilot A runners, confirmatory preparation, rate card, receipts, and run records here. I made this work additive; I did not change my frozen v8.6.3 files or track the frozen item pool. My Python entrypoints default to offline dry runs. Each Colab launcher reads OPENROUTER_API_KEY from Colab Secrets without printing it, runs the connectivity check first, and starts its configured pipeline only if all four model probes pass.

I use MANIFEST_SHA256.txt to verify the twelve root source and support files listed there. It does not hash itself. I keep each receipt, source archive, reconciliation, and run manifest under pilot_receipts/. My .gitattributes file keeps source line endings stable across Windows and Linux.

## The item pool I use

Before any run, pilot_b_v9.py verifies the exact 260-item items_pool_v1.json file at SHA-256 128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3. I verified that the local file is 75,875 bytes. I include it in Colab bundles and keep it outside Git.

## My engineering connectivity checks

I configured api_ping_check_v9.py to send one non-study request for each of four model families through OpenRouter's chat completions endpoint. Each request uses OPENROUTER_API_KEY only in an authorization header, with temperature 0.0, top-p 1.0, and max_tokens 16. I reject non-200 responses, empty output, finish_reason == length, and positive reported reasoning-token counts. I store hashes and request metadata, not key values.

My rate card maps each tested slot one-to-one to its model:

| Slot | Model ID | Input / output USD per 1M tokens |
| --- | --- | ---: |
| qwen_72b | qwen/qwen-2.5-72b-instruct | $0.36 / $0.40 |
| gemma_27b | google/gemma-2-27b-it | $0.65 / $0.65 |
| llama_70b | meta-llama/llama-3.3-70b-instruct | $0.10 / $0.32 |
| mistral_24b | mistralai/mistral-small-24b-instruct-2501 | $0.05 / $0.08 |

I recorded 26 engineering connectivity POST probes: six on 27 September (four HTTP 200, one HTTP 400, one HTTP 404) and 20 on 26 November (all HTTP 200). The November count includes four probe reports archived with Pilot B runs 2–5 and four probes in the Pilot A receipt archive. These are engineering checks, not pilot or confirmatory pipeline calls. I found three provider catalog metadata GETs and count them separately.

## My pipeline, failure handling, and budgets

For each tested model slot, I use five stages: Phase 0 harvest (256 output tokens), utility-preserving perturbation (256), independent utility style scrub (192), Phase 1 utility digit evaluation (16), and Domain 2 style-and-utility digit evaluation (16). The two evaluation stages remain locked at 16 output tokens.

The style scrub requests three plain, neutral sentences totaling strictly 48–52 whitespace-separated words, with a locked 45–55 word window. I route it through an independent model: Gemma scrubs Qwen, Llama, and Mistral outputs; Mistral scrubs Gemma outputs. If Gemma exhausts its four word-count repairs for Qwen or Llama, Mistral is the independent fallback. I do not allow a model to scrub its own output. I reserve each request and transient retry before sending it at the actual billed-model rate, and retry HTTP 429/503 up to three times with 2/4/8-second backoff and at least 0.35 seconds between attempts.

My Pilot B uses 5 items and a USD 0.25 cap. My Pilot A entrypoint fixes 50 items and a USD 0.50 cap. My confirmatory entrypoint fixes all 260 items and a USD 1.25 cap. My USD 0.22–0.35 planning range for 260 items uses the observed Pilot A rate; it is not a guaranteed cost. I record item status, token use, latency, and estimated cost by tested slot and billed model.

If a style scrub exhausts the primary and fallback word-count repairs, I mark only that model/item row available false with status skipped_due_to_style_scrub_range and continue to the next item. Other failures remain fail-closed for that model, and a spend-cap stop halts further requests.

I validate the pool offline by running pilot_b_v9.py with the verified item-pool path and no execute flag. I add execute only when I intend to send live requests. My reports retain item IDs and hashes, not item text, generated text, request headers, or key values.

## My recorded runs

I have five prospective Pilot B receipts. They record 10, 30, 80, 70, and 127 calls, totaling 317 calls, 317 responses, and USD 0.01926445 estimated spend. My fifth Pilot B receipt is the first one with all four model slots completing all 25 of 25 item-stage pairs across TR_01–TR_05.

I completed one 50-item Pilot A execution. The supplied source ZIP measures SHA-256 13b17189e60acf71a1e26d3b2a8c8fdcc39910a3eb22c6112ba558e287de321b; its receipt SHA-256 is 149563d29132439e2be5666b26ce4e1ddba57bae8d2063e0c8b9d3a354825e60. It records 540 HTTP 200 calls, zero retries, and USD 0.04127526 estimated spend against the USD 0.50 cap. It records 405 successful item-stage pairs across TR_01–TR_40: 80 full five-stage item pipelines account for 400 pairs, and five more pairs came from partial items. Qwen completed 39 full item pipelines, Llama 30, Gemma 9, and Mistral 2. These are partial model coverage, not a 4/4 completion. The archive's four connectivity probes are counted separately.

Across the records, I count 883 DesignLab POST requests: 26 engineering probes, 317 Pilot B calls, and 540 Pilot A calls. Three catalog metadata GETs bring the saved DesignLab request count to 886. I count seven live experimental executions across DesignLab and PSI: five Pilot B, one Pilot A, and one PSI benchmark. The PSI files do not provide a complete external request ledger, so I do not claim an exact PSI request count. Confirmatory study runs remain at zero.

I keep the Pilot A receipt in pilot_receipts/2026-11-26_pilot_a_run_1/ and current counts in provenance_2026_11_26/PILOT_A_LIVE_ACTIVITY_2026-11-26.md and run_count_summary.json.

## My prepared confirmatory entrypoint

I prepared confirmatory_v9.py and DesignLab_v9_0_Colab_Confirmatory.ipynb. They classify a future run as prospective_confirmatory_study, include all 260 items from the verified pool, and enforce the USD 1.25 cap. I have not run it: confirmatory_data_collected is false and the confirmatory run count is zero.

I read or logged no API key and sent no provider requests while preparing this update. I left my frozen v8.6.3 files and the item pool unchanged.
