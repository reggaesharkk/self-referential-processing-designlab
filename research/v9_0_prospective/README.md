# My prospective v9 runner

I keep my prospective v9 connectivity and Pilot B runner here. I added this work without changing my frozen v8.6.3 materials or tracking the frozen item pool. Both Python programs default to offline dry runs; the live records below came from separate executed runs.

I use `MANIFEST_SHA256.txt` to verify the six root source and support files listed there. It does not hash itself. I keep the live receipts and their source archives under `pilot_receipts/`. My `.gitattributes` file keeps source line endings stable across Windows and Linux.

## The item pool I use

Before a run, `pilot_b_v9.py` verifies the exact 260-item `items_pool_v1.json` file at SHA-256 `128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3`. I verified the local file at 75,875 bytes. I include it in my Colab bundle but keep it out of Git.

## My engineering connectivity checks

I configured `api_ping_check_v9.py` to send one non-study request for each of four model families through `https://openrouter.ai/api/v1/chat/completions`. Each request uses `OPENROUTER_API_KEY` only in an `Authorization: Bearer` header, temperature `0.0`, top-p `1.0`, and `max_tokens: 16`. I reject non-200 responses, empty output, `finish_reason == "length"`, and positive reported reasoning-token counts. I store hashes and metadata, not response text, headers, or key values.

My rate card maps each runner slot one-to-one to its OpenRouter model:

| Slot | Model ID | Input / output USD per 1M tokens |
| --- | --- | ---: |
| `qwen_72b` | `qwen/qwen-2.5-72b-instruct` | $0.36 / $0.40 |
| `gemma_27b` | `google/gemma-2-27b-it` | $0.65 / $0.65 |
| `llama_70b` | `meta-llama/llama-3.3-70b-instruct` | $0.10 / $0.32 |
| `mistral_24b` | `mistralai/mistral-small-24b-instruct-2501` | $0.05 / $0.08 |

I recorded four v9 connectivity checks on 26 November 2026; all returned HTTP 200. I list these as engineering probes, not Pilot A/B or confirmatory runs. I treat the rates as a dated snapshot and recheck [Qwen](https://openrouter.ai/qwen/qwen-2.5-72b-instruct/pricing), [Gemma](https://openrouter.ai/google/gemma-2-27b-it/pricing), [Llama](https://openrouter.ai/meta-llama/llama-3.3-70b-instruct/pricing), and [Mistral](https://openrouter.ai/mistralai/mistral-small-24b-instruct-2501/pricing) before a future run.

I run the offline check with:

```powershell
python research/v9_0_prospective/api_ping_check_v9.py
```

I add `--execute` only when I intend to send live engineering requests. My default output paths are timestamped, and my scripts refuse to overwrite existing outputs.

## My prospective Pilot B pipeline

I run the first five verified pool rows through these stages for each model slot:

1. Phase 0 harvest, capped at 256 output tokens.
2. Utility-preserving perturbation, capped at 256 output tokens.
3. Utility style scrub, capped at 192 output tokens. I instruct it to write 3 plain, neutral sentences totaling strictly 48 to 52 whitespace-separated words, with a locked minimum of 45 and maximum of 55.
4. Phase 1 utility digit evaluation, strictly capped at 16 output tokens.
5. Domain 2 style-and-utility digit evaluation, strictly capped at 16 output tokens.

I allow at most four targeted style-scrub repairs when word count is the only blocker. The base prompt and each repair use the same instruction: “Write 3 plain, neutral sentences totaling strictly 48 to 52 whitespace-separated words (minimum 45, maximum 55).” Each repair states the exact current count, targets 48–52 words, and remains inside the 45–55 acceptance window. If the rewrite still falls outside the locked window, or another blocker remains, I fail that model/item path closed. My baseline is 100 calls across four models and five items; my maximum is 45 calls per model and 180 overall, including all four retries per item/model. I reserve each request before sending it, using the stage token cap with twice that output allowance for reservation, under the same USD 0.25 estimated-spend cap. I record token counts, latency, and estimated cost per model. The cap is an estimate guard, not a provider invoice guarantee.

I validate the pool offline with:

```powershell
python research/v9_0_prospective/pilot_b_v9.py --items 'C:\path\to\items_pool_v1.json'
```

I add `--execute` only for a live Pilot B run. My reports retain item IDs and hashes, not item text, generated text, headers, or key values.

## Live records I have

I have three prospective Pilot B receipts. My first records 10 calls, 10 responses, and USD 0.00053603 estimated spend for `TR_01`. My second records 30 calls, 30 HTTP 200 responses, and USD 0.00119524 estimated spend; its four model slots were unavailable at the end. My third records 80 calls, 80 HTTP 200 responses, and USD 0.00494411 estimated spend. In that run, Gemma completed all 25 item-stage pairs across `TR_01`–`TR_05`. Llama completed 17 of 25 pairs, with all five stages complete for `TR_01`–`TR_03`; Qwen completed 2 pairs and Mistral 7 pairs. I archive the third receipt under [`pilot_receipts/2026-11-26_run_3/`](pilot_receipts/2026-11-26_run_3/).

The request accompanying my third source ZIP stated SHA-256 `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430680`, while the supplied archive bytes hash to `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430600`. I preserved the supplied ZIP and recorded the discrepancy in the run 3 reconciliation note and manifest.

Across my three Pilot B runs, I recorded 120 calls and USD 0.00667538 estimated spend. I also recorded four v9 engineering connectivity probes, all HTTP 200, and six 27 September engineering probes: four HTTP 200, one HTTP 400, and one HTTP 404. I found three provider catalog metadata GET requests. I found no Pilot A run and no confirmatory study run; `confirmatory_data_collected` is false in all three Pilot B receipts. My cumulative counts and limitations are in [`provenance_2026_11_26/`](provenance_2026_11_26/).
