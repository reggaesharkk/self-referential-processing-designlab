# Prospective v9 runner (uncommitted build)

This directory is a prospective implementation on branch `v9-0-prospective-runner`. It does not change or supersede the frozen v8.6.3 materials. The two Python programs default to no-network dry runs. No provider request was sent while preparing this branch.

`MANIFEST_SHA256.txt` records SHA-256 digests for the six source and support files in this directory; the manifest does not hash itself. `.gitattributes` keeps their line endings stable so the recorded hashes survive checkout on Windows and Linux.

## Dataset gate

`pilot_b_v9.py` requires the exact 260-item `items_pool_v1.json` bytes with SHA-256 `128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3`. It validates the digest and schema before reading API-key environment variables or sending requests. The user supplied `C:\Users\Asus\CrossDevice\motorola edge 60 fusion (1)\storage\Download\items_pool_v1.json`; on 2026-11-26 its SHA-256 matched, its size was 75,875 bytes, and it had 260 rows with the required fields. The OSF master root (`NV7DZ`), linked v8 project roots (`8YHWF` and `UKZQR`), and cited original foundation root (`37H2Y`) returned no exact filename; OSF global search for `items_pool_v1.json` and `items_pool` also returned no results. The user reports that the pool is on OSF, but that specific OSF location remains unresolved. Pass the verified local path with `--items`; the runner independently repeats the hash and schema checks and fails closed on any mismatch.

## Engineering connectivity probe

`api_ping_check_v9.py` sends four engineering-only probes and two Together `logprobs=1` probes only when invoked with `--execute`. It uses the exact non-study prompt:

> Engineering connectivity test. Reply with exactly the single digit 1.

Each request uses temperature `0.0`, top-p `1.0`, and a token limit of `16`. Groq's OpenAI-compatible endpoint receives the provider-supported `max_completion_tokens: 16` field; the other chat endpoints receive `max_tokens: 16`, and Gemini receives `maxOutputTokens: 16`. Keys are read only from `TOGETHER_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, and `GEMINI_API_KEY`, then sent in HTTPS headers. The Gemini candidate uses Google's Gemini Developer API with the API key header; it does not implement Vertex OAuth authentication.

The four availability candidates are:

| Provider | Candidate model |
| --- | --- |
| Together | `Qwen/Qwen3.5-9B` |
| Groq | `qwen/qwen3.8-27b` |
| OpenRouter | `meta-llama/llama-3.3-70b-instruct` |
| Gemini API | `gemma-4-26b-a4b-it` |

The two additional Together logprobs probes use `meta-llama/Llama-3.3-70B-Instruct-Turbo` and `Qwen/Qwen2.5-72B-Instruct-Turbo`. A candidate is unavailable when its HTTP status is not 200, output text is empty, finish reason is `length`, or reported reasoning-token count is positive. The connectivity process exits successfully only when all four provider candidates are available; logprobs eligibility is reported separately. Reports store output hashes and counts, never raw model output, request headers, or key values. Each HTTP attempt is written to the run ledger before the request, so an interrupted run leaves a `started` row; `http_calls_started` counts local request attempts and `http_responses_received` separately counts HTTP responses.

Run a no-network dry run:

```powershell
python research/v9_0_prospective/api_ping_check_v9.py
```

Add `--execute` only when an actual connectivity run is intended. The default output name is timestamped; existing output paths are refused to preserve prior records.

## Prospective Pilot B

`pilot_b_v9.py` selects the first five pool rows and applies this five-call-per-item pipeline independently for each candidate model:

1. Phase 0 harvest.
2. Utility-preserving perturbation.
3. Utility style scrub constrained to 45–55 whitespace-delimited words.
4. Phase 1 utility digit evaluation, capped at 16 output tokens.
5. Domain 2 style-and-utility digit evaluation, capped at 16 output tokens.

That is at most 25 requests per model and 100 across all four providers. The two digit evaluations accept only a single `0` or `1` (surrounding whitespace is ignored). Reports contain item IDs/categories and item, prompt, request, and response hashes; they do not store the item text or model-generated text. Token counts, summed latency, and estimated USD cost are recorded per model.

The default cap is USD 0.25 and `--budget-usd` cannot exceed USD 0.25. Before each request the runner reserves cost using the versioned rate card in `model_rates_v9.json`, a UTF-8 byte-based input upper bound, and twice the output-token limit; it stops before issuing a request whose reservation would cross the cap. This is a cap on the runner's local estimate under the recorded price snapshot, not a guarantee against later price changes, provider-side billing rules, or invoice adjustments. Refresh and reconcile the rate card before any future live run.

Validate the supplied file offline (no key access or HTTP calls):

```powershell
python research/v9_0_prospective/pilot_b_v9.py --items 'C:\Users\Asus\CrossDevice\motorola edge 60 fusion (1)\storage\Download\items_pool_v1.json'
```

Add `--execute` only to run Pilot B. An output file is created before the first request and updated after each attempt. A `started` row persists if the process is interrupted around a call. Outputs are timestamped by default, and the runner refuses to overwrite an existing path. The run is explicitly labeled prospective Pilot B; it does not collect confirmatory study data.

## Price references

The checked rate-card source links are recorded with each provider in `model_rates_v9.json`: [Together serverless models](https://docs.together.ai/docs/serverless/models), [Groq Qwen model page](https://console.groq.com/docs/model/qwen/qwen3.8-27b), [OpenRouter provider rates](https://openrouter.ai/meta-llama/llama-3.3-70b-instruct/providers), and [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing). Model IDs and rates can change; recheck before use.
