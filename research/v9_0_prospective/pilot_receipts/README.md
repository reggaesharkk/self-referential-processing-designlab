# Live Pilot B receipt provenance

`pilot_b_v9_result.json` is copied byte-for-byte from the only matching receipt member in the user-supplied `v9_0_pilot_b_results (17).zip`. It is an immutable record of the earlier run; it is not regenerated using the updated v9 scripts.

| Evidence | Value |
| --- | --- |
| Source ZIP SHA-256 | `7d0d9103e112288137bd52cc315f0560b0f20df45c23e70cb2140e888902b4a7` |
| Receipt SHA-256 | `db82e60bf1aaffa3ecd76909c34aa1a90160224d5e2b5f8f6b3afb346fcdcfc3` |
| Receipt size | 13,700 bytes |
| Item pool SHA-256 | `128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3` |
| HTTP calls started / responses | 10 / 10 |
| Estimated spend | USD 0.00053603 |
| Recorded reservation | USD 0.00506407 |
| Spend cap | USD 0.25 |
| Classification | `prospective_pilot_b_not_confirmatory_study` |
| Confirmatory data collected | `false` |

The receipt describes only `TR_01`. Calls 0001–0009 returned HTTP 200. The three style-scrub attempts failed only the locked word-count criterion, at 27 words (Qwen), 21 words (Gemma), and 22 words (Llama). Call 0010 (Mistral Small, previously routed via Gemini) returned HTTP 401 and has the recorded `http_status_not_200` and `raw_text_empty` blockers. That mismatch motivated routing every prospective slot through the OpenRouter bearer-authenticated endpoint. These values come from metadata fields only; generated model text and credentials are not reproduced here.

SHA-256 values in this folder are listed in `MANIFEST_SHA256.txt`; that manifest does not hash itself. A credential-pattern scan of the source ZIP and receipt found zero matches before copying. Recheck this manifest and the receipt bytes after checkout.
