# My prospective v9 runner

I keep my connectivity check, Pilot B and Pilot A runners, confirmatory runner, rate card, Colab notebook, receipts, and run ledger here. I made these additions without changing the frozen v8.6.3 files or `items_pool_v1.json`. My entrypoints default to offline dry runs. My Colab notebook reads `OPENROUTER_API_KEY` from Colab Secrets without printing it, runs connectivity checks first, and only starts the confirmatory pipeline if all four slots pass.

## My verified pool and budget

Before a run, `pilot_b_v9.py` verifies the 260-item `items_pool_v1.json` file at SHA-256 `128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3`. I verified its size as 75,875 bytes. I include it in Colab bundles and keep it outside Git.

The attached account screenshot shows a USD 50 weekly API-key limit, USD 0.20 used, and USD 49.80 remaining, with a displayed reset of 30 November 2026 at 5:30 AM. I keep the local confirmatory cap at USD 1.25, which is lower than that remaining allowance. My reported USD 0.2005 provider balance at the time of the HTTP 402 is user-reported and was not independently queried; a weekly API-key limit is separate from provider wallet credit.

When I resume a confirmatory receipt, I verify its pool hash and complete item-stage call records, carry those calls forward, skip completed `(slot, item_id)` pairs, and count previous reservations against the same USD 1.25 aggregate cap. Run 1 reserved USD 0.10182801, leaving USD 1.14817199 of reservation headroom. The receipt's estimated actual spend was USD 0.01704482. The reservation is the conservative cap accounting used by the runner; neither number proves what the provider will bill.

## My engineering connectivity checks

I configured `api_ping_check_v9.py` to send one non-study request for each of four model families through OpenRouter chat completions. Each request uses the key only in an authorization header with temperature 0.0, top-p 1.0, and max_tokens 16. I reject non-200 responses, empty output, `finish_reason == length`, and positive reported reasoning-token counts. I store request hashes and redacted response metadata, not key values. If a probe returns HTTP 402, I stop and record which slots I did not attempt.

My rate card maps each tested slot one-to-one to its model:

| Slot | Model ID | Input / output USD per 1M tokens |
| --- | --- | ---: |
| qwen_72b | qwen/qwen-2.5-72b-instruct | $0.36 / $0.40 |
| gemma_27b | google/gemma-2-27b-it | $0.65 / $0.65 |
| llama_70b | meta-llama/llama-3.3-70b-instruct | $0.10 / $0.32 |
| mistral_24b | mistralai/mistral-small-24b-instruct-2501 | $0.05 / $0.08 |

I recorded 30 engineering connectivity POST probes: six on 27 September (four HTTP 200, one HTTP 400, one HTTP 404) and 24 on 26 November (all HTTP 200). The November count includes four probes each archived with Pilot B runs 2–5, four with Pilot A, and four with partial confirmatory run 1. These are engineering checks, separate from pipeline calls. I found three provider catalog metadata GET requests and count those separately.

## My pipeline and halt behavior

For each tested model slot, I use five stages: Phase 0 harvest (256 output tokens), utility-preserving perturbation (256), independent utility style scrub (192), Phase 1 digit evaluation (16), and Domain 2 digit evaluation (16). The two evaluation stages stay locked at 16 output tokens.

The style scrub asks for three neutral sentences totaling 48–52 whitespace-separated words within the locked 45–55 window. Gemma scrubs Qwen, Llama, and Mistral outputs; Mistral scrubs Gemma outputs. If Gemma exhausts its four word-count repairs for Qwen or Llama, Mistral is the independent fallback. I do not let a model scrub its own output. I reserve each request and transient retry before sending it at the actual billed-model rate, and retry HTTP 429/503 up to three times with 2/4/8-second backoff and at least 0.35 seconds between calls.

A provider HTTP 402 now stops the entire runner immediately, before any other model or item request. It records `halt_reason: http_402_insufficient_credits`. The engineering ping script follows the same first-402 stop. The archived run 1 receipt shows why I added this: it records the first 402 on Qwen/TR_28/Phase 1 and three more 402 calls on the other slots, even though its JSON says `stopped_early=false` and has no `halt_reason`.

My Pilot B entrypoint uses 5 items and a USD 0.25 cap. My Pilot A entrypoint locks 50 items and a USD 0.50 cap. My Confirmatory entrypoint locks all 260 items and a USD 1.25 cap. A resume deducts the earlier run's USD 0.10182801 reservation from that same cap before it allows a new request. My earlier USD 0.22–0.35 planning range for 260 items is an estimate, not a guaranteed cost.

If a style scrub exhausts the primary and fallback word-count repairs, I mark only that model/item row unavailable and continue to the next item. Other failures remain fail-closed for that model; HTTP 402 stops all remaining models and items. My reports retain item IDs, hashes, calls, stages, token counts, latency, estimated cost, and budget reservations, not item text, generated text, request headers, or key values.

## My recorded live work

I have five Pilot B receipts with 317 pipeline calls and USD 0.01926445 estimated spend total. Run 5 completed all 25 item-stage pairs for each of four slots on TR_01–TR_05.

I completed one 50-item Pilot A execution: 540 HTTP 200 responses, zero retries, and USD 0.04127526 estimated spend against the USD 0.50 cap. It records 405 successful item-stage pairs over TR_01–TR_40: 80 full five-stage item pipelines and five additional partial stages. Qwen completed 39 item pipelines, Llama 30, Gemma 9, and Mistral 2. I count its four connectivity probes separately.

I have one partial prospective confirmatory execution. Its preserved ZIP measures SHA-256 `3c95c500177a6960a791eaa2633e96ac7c0a270abefa2956a549faf92b6d9f3c`; its result JSON hash is `d83caec7364395005fd1fc5fd1ac61332cbd650c5cb74b3e322a2a205955fa7f`. It records 180 responses (176 HTTP 200, four HTTP 402), USD 0.01704482 estimated spend, and USD 0.10182801 reserved. Qwen completed 27 items and three stages on TR_28 (138 successful stage pairs); the other slots completed no items. The result marks `confirmatory_data_collected=true`. I count this as one partial confirmatory run, not a completed 260-item run.

The attached ZIP also contains four separate HTTP 200 connectivity probes. Across all local DesignLab receipts I count 30 engineering POST probes, 317 Pilot B requests (316 HTTP 200, one HTTP 401), 540 Pilot A requests, and 180 confirmatory requests (176 HTTP 200, four HTTP 402), or 1,067 documented POST requests. Across all POSTs, I count 1,060 HTTP 200, one HTTP 400, one HTTP 401, one HTTP 404, and four HTTP 402. Three catalog GETs make 1,070 saved DesignLab HTTP requests. I do not have provider-side billing logs, so this is a count of preserved records. My PSI repository provides one live run but no exact external API-call count. Across DesignLab and PSI, I can document nine live experimental executions across five Pilot B runs, one Pilot A run, one partial OpenRouter confirmatory run, one partial local-HF confirmatory run, and one PSI run.

I keep my partial receipt, source ZIP, extracted result files, reconciliation, and manifests under `confirmatory_receipts/2026-11-26_run_1_partial_402/`. The current cumulative counts are in `provenance_2026_11_26/run_count_summary.json`.

## My Confirmatory Colab run and resume

I prepared `confirmatory_v9.py` and `DesignLab_v9_0_Colab_Confirmatory.ipynb` for the full 260-item prospective confirmatory pipeline. The notebook defaults to the archived partial result as `RESUME_FROM_PATH`. If I later need to start a fresh run, I can set it to `None`. The runner preserves prior calls and item summaries, verifies completed pairs against successful stage records, and executes only incomplete pairs.

I validated the saved run 1 result offline: the resume check recognizes 27 completed Qwen item pairs and the unchanged SHA-256-verified pool. The dry run starts zero provider requests. I added offline tests for first-402 stops and resume merging. I sent no new provider request and read or logged no API key while preparing this revision.

## My zero-key local GPU variant

I prepared a separate local Hugging Face v9 runner for four open-weight model families. I run one tested family per session, load its independent utility scrubber only when needed, and release the previous model from GPU memory before loading the next one. I require at least 14 GiB of CUDA memory; a 16 GB T4 meets that preflight. I have not yet measured an end-to-end GPU run. Three families are loaded with bitsandbytes NF4; the Gemma 2 9B mirror is already published in NF4 format. I use the public [Gemma 2 mirror](https://huggingface.co/unsloth/gemma-2-9b-it-bnb-4bit) for weight access while retaining the Gemma model identity and license requirements; the canonical [Google Gemma model](https://huggingface.co/google/gemma-2-9b-it) has gated access.

| Slot | Model | Independent style scrubber |
| --- | --- | --- |
| qwen_7b | Qwen/Qwen2.5-7B-Instruct | gemma_9b |
| gemma_9b | google/gemma-2-9b-it (public NF4 mirror) | mistral_7b |
| llama_8b | NousResearch/Hermes-3-Llama-3.1-8B | gemma_9b |
| mistral_7b | mistralai/Mistral-7B-Instruct-v0.3 | gemma_9b |

I preserve the five-stage pipeline, deterministic decoding, the 45–55 word scrub window with up to four repairs, and 16-token limits for both digit-evaluation stages. I flush each completed item into a slot-specific JSON checkpoint on Google Drive. I can resume the same slot with --resume-from, then merge the four policy- and pool-verified checkpoints after all families are done. The dedicated single-cell notebook is DesignLab_v9_0_Colab_T4_Local_Confirmatory.ipynb; it requires a Colab T4. I also prepared GCE_EXISTING_VM.md and scripts for an already-running Debian GCE VM, without creating a VM. Both paths use no inference API keys. Public model-weight and software downloads still require internet access. Model inference API spend is USD 0.00; Colab GPU access is controlled by Colab, while GCE compute and disks remain billable.

I have prepared this as a distinct v9 local-HF protocol variant. My GCE setup first checks nvidia-smi and the 14 GiB threshold, before it creates a Python environment or downloads libraries. I processed 105 of 260 Qwen items on a Tesla T4 through DP_01, covering TR_01 through TR_52 and BE_01 through BE_52. I completed all five stages for 101 items and skipped TR_11, BE_26, BE_41, and BE_43 after their style scrubs missed the word-count window. I recorded zero failed items and 155 still to process for Qwen. My checkpoint records 673 local generations, zero external inference requests, and $0.00 external API spend. [My 26 November Qwen checkpoint](confirmatory_receipts/2026-11-26_local_hf_qwen_7b_part1/confirmatory_local_hf_qwen_7b.json) I do not treat this variant as an execution of frozen v8.6.3; any claim that it confirms that registered protocol requires a protocol amendment and matching registration.

I use `MANIFEST_SHA256.txt` to verify my listed source files; it does not hash itself. I keep receipt manifests next to each archived source. I have not modified any frozen v8.6.3 file or the item pool.
