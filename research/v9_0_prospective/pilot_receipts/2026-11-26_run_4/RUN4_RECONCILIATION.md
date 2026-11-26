# Run 4 receipt reconciliation

I archived the supplied v9_0_pilot_b_results (3).zip byte-for-byte. Its measured SHA-256 is 50618f7279799d08f562490455f261bd024094617b72f95ca9d37f799f116f1b, matching the digest supplied with the request. The archive passes ZIP integrity and all six entries in its internal SHA256SUMS.txt verify.

The receipt records 70 calls, 70 HTTP responses, all 70 with HTTP 200, USD 0.00350597 estimated spend, and USD 0.02412054 reserved. confirmatory_data_collected is false. I classify this as a prospective Pilot B execution.

Gemma (google/gemma-2-27b-it) completed 25/25 item-stage pairs across TR_01–TR_05 in 26 calls. Mistral (mistralai/mistral-small-24b-instruct-2501) completed 25/25 in 30 calls. Qwen completed 2 pairs and Llama completed 2 pairs in this receipt.

I sent no provider requests while archiving this record. The run manifest covers this note, the source ZIP, and extracted output files.
