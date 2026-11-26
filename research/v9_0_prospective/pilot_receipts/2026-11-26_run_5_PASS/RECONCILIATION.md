# My run 5 Pilot B receipt reconciliation

I preserved the supplied ZIP byte-for-byte as `source_v9_0_pilot_b_results_run_5.zip`. Its measured SHA-256 is `44873ec36a8ea48d29a4f98506b0ee9ce7b82af5edf2388f538bcfaf170afe64`. The extracted `pilot_b_v9_result.json` SHA-256 is `5a7357e69b3a15e853d61df1e94d0f571e4a478907358caf6d2d6d643e0a5149`, matching the supplied digest. I verified all seven ZIP members against the included SHA256SUMS.txt before extraction.

The receipt records 127 logical calls, 127 HTTP responses, all 127 responses HTTP 200, zero transient retries, USD 0.00908310 estimated spend, and USD 0.05747706 reserved under the USD 0.25 cap. All four slots completed 25/25 item-stage pairs across TR_01–TR_05: Qwen, Gemma, Llama, and Mistral. I classify this as a passed prospective Pilot B run; confirmatory_data_collected is false.
