# Run 3 receipt reconciliation

I received `v9_0_pilot_b_results (1).zip` and preserved the supplied archive byte-for-byte as `source-results.zip`. The request listed SHA-256 `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430680`, but the supplied file hashes to `68859768a5bf7ff1f682df2ad54fe938dd28b70b3c66ad4ae692912d59430600`. I record the digest computed from the archived bytes and retain the discrepancy here; I do not substitute the requested digest for the measured one.

The archive is ZIP-valid, and all six entries in its internal `SHA256SUMS.txt` verify. It records 80 calls, 80 HTTP 200 responses, and USD 0.00494411 estimated spend. This is a prospective Pilot B execution; `confirmatory_data_collected` is false.

`gemma_27b` (`google/gemma-2-27b-it`) completed all 25 item-stage pairs across `TR_01`–`TR_05` (`complete_pipeline: true`) in 33 calls. `llama_70b` (`meta-llama/llama-3.3-70b-instruct`) completed 17 of 25 pairs in 31 calls, with all five stages complete for `TR_01`–`TR_03`. Qwen completed 2 pairs in 7 calls; Mistral completed 7 pairs in 9 calls. The receipt records Mistral style-scrub repair 1 on `TR_02` ending with `finish_reason: length` at 128 output tokens and 99 words; Qwen plateaued at 39 words, and Llama reached 44 words on `TR_04` after four repairs.

I did not make new provider requests while archiving this receipt. The source archive, extracted outputs, and this note are covered by `MANIFEST_SHA256.txt`.
