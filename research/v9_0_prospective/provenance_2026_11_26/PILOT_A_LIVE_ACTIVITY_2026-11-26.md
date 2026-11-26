# My live-run accountability record — 26 November 2026, after Pilot A run 1

I reconciled five supplied Pilot B receipts, the new Pilot A receipt and its connectivity report, September and November engineering records, and published PSI result files. These are counts in the records available to me, not provider billing logs.

## My current counts

| Category | Count in my saved records | Evidence |
| --- | ---: | --- |
| 27 September engineering connectivity probes | 6: 4 HTTP 200, 1 HTTP 400, 1 HTTP 404 | Non-study diagnostics |
| 26 November engineering connectivity probes | 20: all HTTP 200 | Four archived Pilot B ping reports plus the Pilot A archive's four-model ping report |
| Engineering connectivity probes total | 26: 24 HTTP 200, 1 HTTP 400, 1 HTTP 404 | Separate from pipeline calls |
| Pilot A executions | 1 | 540 HTTP 200 responses; zero retries; USD 0.04127526 estimated spend against USD 0.50 |
| Pilot B executions | 5 | 317 calls and responses; USD 0.01926445 estimated spend |
| Confirmatory study executions | 0 | My 260-item entrypoint is prepared but has not run |
| Provider catalog metadata GETs | 3 | Counted separately from POST requests |
| PSI live benchmark executions | 1 | Five result rows; its exact external request total is not recorded |

I count 883 DesignLab POST requests in saved records: 26 engineering probes, 317 Pilot B calls, and 540 Pilot A calls. Three catalog metadata GETs bring the DesignLab HTTP request count to 886. I also document one PSI live benchmark execution, but the PSI files do not establish an exact external request count. Across DesignLab and PSI, I document seven experimental executions: five Pilot B, one Pilot A, and one PSI benchmark.

## My Pilot A receipt

I preserved the supplied archive byte-for-byte. Its measured source ZIP SHA-256 is 13b17189e60acf71a1e26d3b2a8c8fdcc39910a3eb22c6112ba558e287de321b. The included receipt hash is 149563d29132439e2be5666b26ce4e1ddba57bae8d2063e0c8b9d3a354825e60; the call ledger hash is a7bdafd1130b56089d5b0f364be9412d0a3bffc2a9f14071607c855a1ab8258b; the token/spend report hash is 5bc022338352241f47eb8f7f8a509aac2335d6447a1bbefca05d087ff303896b; and the ping report hash is eff2839e27f80b20c59711823b4f2d7684a53e909fe04767aa286d18e7c03118. The ZIP integrity test and all included file hashes passed.

My Pilot A execution selected the first 50 pool items (TR_01–TR_50) and recorded 540 HTTP 200 responses, zero transient retries, and USD 0.04127526 estimated spend against its USD 0.50 cap. I counted 405 successful item-stage pairs: 80 full five-stage item pipelines account for 400 pairs, with five more successful stage pairs on partial items. The complete five-stage pipelines were Qwen 39 items (TR_01–TR_39), Llama 30 (TR_01–TR_30), Gemma 9 (TR_01–TR_09), and Mistral 2 (TR_01–TR_02). These counts show partial model coverage; the execution is not a 4/4 completion. The receipt classifies it as prospective_pilot_a_not_confirmatory_study with confirmatory_data_collected false.

The same archive contains four separate engineering connectivity probes, all HTTP 200 and with zero retries. I do not add those four probes to the 540 Pilot A pipeline calls.

## My item-isolation and 260-item preparation

I changed the shared runner so an exhausted style-scrub word-count repair marks only that model/item row unavailable with status skipped_due_to_style_scrub_range. The runner then advances to the next item. Other failed stages and spend-cap stops retain their fail-closed handling.

I prepared confirmatory_v9.py and DesignLab_v9_0_Colab_Confirmatory.ipynb to select all 260 pool items with classification prospective_confirmatory_study and a USD 1.25 cap. My planning range is USD 0.22–0.35 based on the observed Pilot A rate; it is an estimate. The entrypoint and notebook passed offline validation. This preparation did not run the pipeline, so confirmatory runs remain at zero and confirmatory_data_collected remains false.

I verified the unchanged item pool at 75,875 bytes and SHA-256 128ff78bb6beb1640fa51897ab97dbb9d07dc56de276973d05a48dda524b53d3. I read or logged no API keys and sent no provider requests while preparing this update.
