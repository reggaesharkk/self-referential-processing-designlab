# Prospective v9 runner

This directory contains the prospective v9 connectivity and Pilot B runner on branch `v9-0-prospective-runner`. It is additive and leaves frozen v8.6.3 materials and the item pool out of Git unchanged. Both Python programs default to no-network dry runs. Building this release made no provider requests.

`MANIFEST_SHA256.txt` hashes the six root source/support files listed in the manifest and does not hash itself. The separate `pilot_receipts/` directory preserves the attached live-run receipt and has its own provenance manifest. `.gitattributes` keeps the root source/support file line endings stable across Windows and Linux.

## Frozen item pool

`pilot_b_v9.py` requires the exact 260-item `items_pool_v1.json` bytes with SHA-256 `128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3`. It validates the digest and schema before reading the API-key environment variable or sending requests. The user-supplied local file was verified at 75,875 bytes with the expected SHA-256; the pool is bundled for Colab but is not tracked in this repository.

## Engineering connectivity check

`api_ping_check_v9.py --execute` sends four non-study probes through `https://openrouter.ai/api/v1/chat/completions`, one for each model family below. All candidate slots read the same `OPENROUTER_API_KEY` and send it only as an `Authorization: Bearer` HTTP header. The request uses temperature `0.0`, top-p `1.0`, `max_tokens: 16`, and the prompt “Engineering connectivity test. Reply with exactly the single digit 1.” The check rejects HTTP statuses other than 200, empty output, `finish_reason == "length"`, and positive reported reasoning-token counts. It stores output hashes and metadata rather than raw model text, headers, or key values.

| Slot | OpenRouter model ID | Input / output USD per 1M tokens |
| --- | --- | ---: |
| `qwen_72b` | `qwen/qwen-2.5-72b-instruct` | $0.36 / $0.40 |
| `gemma_27b` | `google/gemma-2-27b-it` | $0.65 / $0.65 |
| `llama_70b` | `meta-llama/llama-3.3-70b-instruct` | $0.10 / $0.32 |
| `mistral_24b` | `mistralai/mistral-small-24b-instruct-2501` | $0.05 / $0.08 |

The four rate-card entries match the four slots one-to-one. Prices are a snapshot; recheck `model_rates_v9.json` before any future live run. Price sources: [Qwen](https://openrouter.ai/qwen/qwen-2.5-72b-instruct/pricing), [Gemma](https://openrouter.ai/google/gemma-2-27b-it/pricing), [Llama](https://openrouter.ai/meta-llama/llama-3.3-70b-instruct/pricing), and [Mistral](https://openrouter.ai/mistralai/mistral-small-24b-instruct-2501/pricing). OpenRouter's request format and bearer authentication are documented in its [chat completion API reference](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request?explorer=true).

Run a no-network dry run:

```powershell
python research/v9_0_prospective/api_ping_check_v9.py
```

Add `--execute` only when an actual engineering connectivity run is intended. The default output name is timestamped; existing output paths are refused to preserve prior records. A connectivity probe is not a Pilot A/B run or confirmatory study run.

## Prospective Pilot B

The runner applies this five-stage pipeline to the first five verified pool rows, independently for each of the four model slots:

1. Phase 0 harvest.
2. Utility-preserving perturbation.
3. Utility style scrub in a locked 45–55 whitespace-delimited word window.
4. Phase 1 utility digit evaluation, capped at 16 output tokens.
5. Domain 2 style-and-utility digit evaluation, capped at 16 output tokens.

The baseline is 25 calls per slot and 100 total. If a style-scrub answer is outside the locked word window and its word count is the only blocker, the runner makes at most two targeted repair calls. Each repair prompt includes the exact current count and targets 48–52 words. A request that still fails the word window after the two repairs, or has any other blocker, fails closed for that item/model pipeline. The absolute maximum is 35 calls per slot and 140 total; the shared USD 0.25 estimated-spend cap applies to every original and repair call.

The two digit evaluations accept only a single `0` or `1` (surrounding whitespace is ignored). Reports contain item IDs/categories and item, prompt, request, and response hashes; they do not store item text, generated text, headers, or key values. Token counts, summed latency, estimated USD cost, baseline and maximum call counts, and repair counts are recorded by slot/model.

Before each request, the runner reserves estimated cost using the versioned rate card, a UTF-8 byte-based input upper bound, and twice the output-token limit. It stops before issuing a request whose reservation would cross USD 0.25. This is the runner's cap on its local estimate, not an upstream provider billing limit or an invoice guarantee. Refresh the rate card before a future live run.

Validate the pool offline without reading a key or making HTTP calls:

```powershell
python research/v9_0_prospective/pilot_b_v9.py --items 'C:\path\to\items_pool_v1.json'
```

Add `--execute` only to run Pilot B. The timestamped output is written before the first request and updated after each attempt; existing paths are refused. Runs are labeled prospective Pilot B and explicitly state that confirmatory data were not collected.

## Prior live Pilot B provenance

`pilot_receipts/pilot_b_v9_result.json` is the byte-preserved receipt supplied in `v9_0_pilot_b_results (17).zip`. Its archive and receipt hashes, 10-call reconciliation, and classification are in the adjacent provenance note. The recorded run is Pilot B, not a confirmatory study; it had 10 HTTP calls started, 10 HTTP responses, and $0.00053603 estimated total spend. The receipt remains evidence of that earlier run; these updated scripts do not rewrite it.
