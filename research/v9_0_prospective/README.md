# My prospective v9 runner

I keep my prospective v9 connectivity, Pilot B, and Pilot A runner here. I added this work without changing my frozen v8.6.3 materials or tracking the frozen item pool. All three Python programs default to offline dry runs. I keep separate one-code-cell [Pilot B](DesignLab_v9_0_Colab_PilotB.ipynb) and [Pilot A](DesignLab_v9_0_Colab_PilotA.ipynb) Colab launchers beside the runners. Each reads OPENROUTER_API_KEY from Colab Secrets, runs the connectivity check first, and starts its locked pipeline only if all four model probes pass. The live records below came from separate executed runs.

I use `MANIFEST_SHA256.txt` to verify all ten root source and support files listed there. It does not hash itself. I keep the live receipts and their source archives under `pilot_receipts/`. My `.gitattributes` file keeps source line endings stable across Windows and Linux.

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

I recorded 16 v9 connectivity checks on 26 November 2026 across four archived run outputs; all returned HTTP 200. I list these as engineering probes, not Pilot A/B or confirmatory runs. I treat the rates as a dated snapshot and recheck [Qwen](https://openrouter.ai/qwen/qwen-2.5-72b-instruct/pricing), [Gemma](https://openrouter.ai/google/gemma-2-27b-it/pricing), [Llama](https://openrouter.ai/meta-llama/llama-3.3-70b-instruct/pricing), and [Mistral](https://openrouter.ai/mistralai/mistral-small-24b-instruct-2501/pricing) before a future run.

I run the offline check with:

```powershell
python research/v9_0_prospective/api_ping_check_v9.py
```

I add `--execute` only when I intend to send live engineering requests. My default output paths are timestamped, and my scripts refuse to overwrite existing outputs.

## My prospective Pilot A and Pilot B pipelines

I select 5 items by default, or 50/260 with --num-items, from the verified pool and run the selected rows through these stages for each tested model slot:

1. Phase 0 harvest, capped at 256 output tokens.
2. Utility-preserving perturbation, capped at 256 output tokens.
3. Utility style scrub, capped at 192 output tokens. I instruct it to write 3 plain, neutral sentences totaling strictly 48 to 52 whitespace-separated words, with a locked minimum of 45 and maximum of 55.
4. Phase 1 utility digit evaluation, strictly capped at 16 output tokens.
5. Domain 2 style-and-utility digit evaluation, strictly capped at 16 output tokens.

I route utility_style_scrub through an independent shared utility model: Gemma scrubs Qwen, Llama, and Mistral outputs; Mistral scrubs Gemma outputs. If Gemma fails four word-count repairs for Qwen or Llama, Mistral is the independent fallback. I do not self-scrub and do not permit a fallback that would self-scrub. I allow at most four targeted style-scrub repairs when word count is the only blocker. The initial prompt and each repair ask for three plain, neutral sentences totaling strictly 48–52 whitespace-separated words (minimum 45, maximum 55); each repair includes the exact current count. My five-item baseline is 100 logical calls. With route-specific fallback and four repairs, the maximum is 230 logical calls (Qwen 70, Gemma 45, Llama 70, Mistral 45), or 920 physical HTTP attempts with three transient retries per attempt. I reserve every pipeline request and retry before sending it at the actual billed model rate. Pilot B is capped at USD 0.25; my dedicated Pilot A entrypoint locks 50 items under a USD 0.50 cap. I record tokens, latency, and estimated cost by tested slot and billing model. This cap is a local estimate guard, not a provider invoice guarantee. I retry only HTTP 429/503, with 2/4/8-second backoff and at least 0.35 seconds between HTTP attempts.

I validate the pool offline with:

```powershell
python research/v9_0_prospective/pilot_b_v9.py --items 'C:\path\to\items_pool_v1.json' --num-items 5
```

I add `--execute` only when I intend to send live connectivity or pilot requests. My reports retain item IDs and hashes, not item text, generated text, headers, or key values.

## My live records and next prepared run

I have five prospective Pilot B receipts. Run 1 records 10 calls and USD 0.00053603 estimated spend. Run 2 records 30 calls and USD 0.00119524; no model completed the five-item pipeline. Run 3 records 80 calls and USD 0.00494411; Gemma completed 25/25 pairs, Llama 17/25, Qwen 2, and Mistral 7. Run 4 records 70 calls and USD 0.00350597; Gemma and Mistral each completed 25/25 pairs. Run 5 records 127 HTTP 200 responses, zero transient retries, and USD 0.00908310 estimated spend; all four slots completed 25/25 pairs across `TR_01`–`TR_05`. I now record Pilot B as passed at 4/4 model slots.

Across the five Pilot B receipts, I recorded 317 calls, 317 responses, and USD 0.01926445 estimated spend. I recorded 22 engineering connectivity POST probes separately: six September probes (four HTTP 200, one HTTP 400, one HTTP 404) and 16 November probes (all HTTP 200) across four saved four-model ping reports. I found three provider catalog metadata GETs. I found no Pilot A execution and no confirmatory study execution. My documented DesignLab model-inference POST count is 339, and the total including catalog GETs is 342. I also document one PSI live Colab benchmark execution; its source does not contain a complete external API request ledger.

I prepared [my Pilot A entrypoint](pilot_a_v9.py) and [Pilot A Colab notebook](DesignLab_v9_0_Colab_PilotA.ipynb) for the first 50 rows of my hash-verified pool. The entrypoint fixes `NUM_ITEMS` at 50 and enforces a USD 0.50 pre-request cap. It records `prospective_pilot_a_not_confirmatory_study` and `confirmatory_data_collected: false`. My run 5 measured rate implies a planning estimate of USD 0.090831 for 50 items; actual cost can differ and the cap can stop a run early. I performed offline validation only. Pilot A remains unrun.

I preserve the fifth archive, extracted records, and manifest in [pilot_receipts/2026-11-26_run_5_PASS/](pilot_receipts/2026-11-26_run_5_PASS/). I keep cumulative counts, classifications, and scope notes in [provenance_2026_11_26/](provenance_2026_11_26/). I have not read or logged API keys, have not sent provider requests while preparing this update, and have not changed frozen v8.6.3 files or the item pool.
