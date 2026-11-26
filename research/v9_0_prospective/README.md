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

1. Phase 0 harvest.
2. Utility-preserving perturbation.
3. Utility style scrub in a locked 45–55 whitespace-delimited word window.
4. Phase 1 utility digit evaluation, capped at 16 output tokens.
5. Domain 2 style-and-utility digit evaluation, capped at 16 output tokens.

I allow at most two targeted style-scrub repairs when word count is the only blocker. Each repair states the exact current count and targets 48–52 words. If the rewrite still falls outside the locked window, or another blocker remains, I fail that model/item path closed. My baseline is 100 calls across four models and five items; the maximum with repairs is 140. I apply a USD 0.25 local estimated-spend cap to every original and repair request. I record token counts, latency, and estimated cost per model. The cap is an estimate guard, not a provider invoice guarantee.

I validate the pool offline with:

```powershell
python research/v9_0_prospective/pilot_b_v9.py --items 'C:\path\to\items_pool_v1.json'
```

I add `--execute` only for a live Pilot B run. My reports retain item IDs and hashes, not item text, generated text, headers, or key values.

## Live records I have

I have two prospective Pilot B receipts. My first receipt records 10 calls, 10 responses, and USD 0.00053603 estimated spend for `TR_01`. My second receipt records 30 calls, all HTTP 200, and USD 0.00119524 estimated spend. The second ledger contains calls for `TR_01` and `TR_02`; all four slots are marked unavailable by its final summary, so I do not describe it as a completed five-item pilot. The receipt records style-scrub word-window blockers and one `finish_reason == "length"` blocker.

I recorded four separate v9 engineering probes, all HTTP 200. I have no Pilot A run and no confirmatory study run in these records. My cumulative request counts and limitations are in [`provenance_2026_11_26/`](provenance_2026_11_26/); I preserve each receipt under [`pilot_receipts/`](pilot_receipts/).
