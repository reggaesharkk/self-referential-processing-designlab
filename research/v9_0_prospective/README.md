# My prospective v9 runner

I keep my prospective v9 connectivity and Pilot B runner here. I added this work without changing my frozen v8.6.3 materials or tracking the frozen item pool. Both Python programs default to offline dry runs. I keep the one-code-cell [Colab launcher](DesignLab_v9_0_Colab_PilotB.ipynb) beside the runner; it reads OPENROUTER_API_KEY from Colab Secrets, runs the connectivity check first, and starts the default five-item Pilot B only if all four model probes pass. The live records below came from separate executed runs.

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

I select 5 items by default, or 50/260 with --num-items, from the verified pool and run the selected rows through these stages for each tested model slot:

1. Phase 0 harvest, capped at 256 output tokens.
2. Utility-preserving perturbation, capped at 256 output tokens.
3. Utility style scrub, capped at 192 output tokens. I instruct it to write 3 plain, neutral sentences totaling strictly 48 to 52 whitespace-separated words, with a locked minimum of 45 and maximum of 55.
4. Phase 1 utility digit evaluation, strictly capped at 16 output tokens.
5. Domain 2 style-and-utility digit evaluation, strictly capped at 16 output tokens.

I route utility_style_scrub through an independent shared utility model: Gemma scrubs Qwen, Llama, and Mistral outputs; Mistral scrubs Gemma outputs. If Gemma fails four word-count repairs for Qwen or Llama, Mistral is the independent fallback. I do not self-scrub and do not permit a fallback that would self-scrub. I allow at most four targeted style-scrub repairs when word count is the only blocker. The initial prompt and each repair ask for three plain, neutral sentences totaling strictly 48–52 whitespace-separated words (minimum 45, maximum 55); each repair includes the exact current count. My five-item baseline is 100 logical calls. With route-specific fallback and four repairs, the maximum is 230 logical calls (Qwen 70, Gemma 45, Llama 70, Mistral 45), or 920 physical HTTP attempts with three transient retries per attempt. I reserve each Pilot B pipeline request and retry before sending it at the actual billed model rate, under the USD 0.25 estimated-spend cap. I record tokens, latency, and estimated cost by tested slot and billing model. This cap is a local estimate guard, not a provider invoice guarantee. I retry only HTTP 429/503, with 2/4/8-second backoff and at least 0.35 seconds between HTTP attempts.

I validate the pool offline with:

```powershell
python research/v9_0_prospective/pilot_b_v9.py --items 'C:\path\to\items_pool_v1.json' --num-items 5
```

I add `--execute` only for a live Pilot B run. My reports retain item IDs and hashes, not item text, generated text, headers, or key values.

## Live records I have

I have four prospective Pilot B receipts. Run 1 records 10 calls, 10 responses, and USD 0.00053603 estimated spend. Run 2 records 30 calls, 30 HTTP 200 responses, and USD 0.00119524 estimated spend; no slot completed its full five-item pipeline. Run 3 records 80 calls, 80 HTTP 200 responses, and USD 0.00494411 estimated spend: Gemma completed 25/25 pairs, Llama 17/25, Qwen 2, and Mistral 7. Run 4 records 70 calls, 70 HTTP 200 responses, and USD 0.00350597 estimated spend. Gemma (google/gemma-2-27b-it) and Mistral (mistralai/mistral-small-24b-instruct-2501) each completed 25/25 pairs with complete_pipeline: true. I archive it under [pilot_receipts/2026-11-26_run_4/](pilot_receipts/2026-11-26_run_4/).

Across those four Pilot B runs, I recorded 190 calls, 190 responses, and USD 0.01018135 estimated spend. I also recorded four November engineering connectivity probes, all HTTP 200, and six September engineering probes: four HTTP 200, one HTTP 400, and one HTTP 404. I found three provider catalog metadata GET requests. I found no Pilot A run and no confirmatory study run. The 260-item option is classified as confirmatory when explicitly executed; I have not executed it. The new Colab notebook defaults to five items and records actual billed-model token and cost totals. My cumulative counts and limitations are in [provenance_2026_11_26/](provenance_2026_11_26/).
