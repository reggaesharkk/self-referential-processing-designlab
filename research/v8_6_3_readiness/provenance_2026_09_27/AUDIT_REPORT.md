# Design 11 / Self-Referential DesignLab: accountability audit

Audit generated: 2026-11-26 00:15:54 +05:30  
Evidence date examined: 2026-09-27; GitHub snapshot: 2026-11-26 (Asia/Calcutta)  
GitHub account: reggaesharkk  
Target repository: https://github.com/reggaesharkk/self-referential-processing-designlab

## Executive findings

- GitHub exposes 19 repositories to the connected account (17 public, 2 private). All 19 default-branch trees were scanned (2,881 blobs in total); target repository non-default branches were scanned too. No requested September 27 generated result artifact was present in the scanned GitHub trees.
- Target repository main is at 10edbe34f1df741cfb4e7f3a7bb0dff4073e6186 (latest commit timestamp 2026-11-01T08:43:51Z), with 67 tracked files. Current D: checkout is at 10edbe34f1df741cfb4e7f3a7bb0dff4073e6186 and clean. Desktop clone is at d22004642aed0b1b37844c96203d07d93e5da71d and clean, an older 67-file snapshot.
- GitHub contains readiness source, templates, and the blocked readiness report, plus the Phase 7 release ZIP/PDF. The provider results and inventory result are local-only. The requested exact DesignLab_API_Access_Inventory(2).json name was not found; an unsuffixed inventory JSON is in Downloads.
- The exact recorded provider POST count is **6 engineering connectivity probes** (4 HTTP 200, 1 HTTP 400, 1 HTTP 404). Three provider catalog GETs are separately recorded, for **9 documented provider HTTP requests total**. No API ping output/call is evidenced, Pilot A = 0, Pilot B = 0, and confirmatory study runs = **0**.
- This count is an evidence-backed count from local records, not a claim about provider billing/account logs. No provider-side activity logs were queried, so unrecorded calls cannot be excluded.
- Audit operations did not read or log any API key and did not modify frozen v8.6.3 source files. The audit bundle itself is newly created at D:\Self_Referential_DesignLab_Audit_2026-11-26.

## Scope and method

Read-only review of the connected GitHub account, target repository main and its visible branches, local Downloads/Documents/Desktop/OneDrive search results, known D: DesignLab/umbrella checkouts, local repository status, result metadata, and archive member names/hashes. GitHub account scan: 19 default-branch trees, 2,881 blobs total; no tree truncation or errors. Target repo branch scan includes main (10edbe34...), rights-20261001-all-rights-reserved (b5de3ffe...), and v863-readiness-pause-20260927 (ccec5d88...). GitHub Actions are outside the requested definition of live run and are excluded.

No API scripts were run. Result JSONs were treated as evidence; only non-secret metadata, recorded timestamps, model identifiers, and HTTP status codes are summarized. Hashing does not expose file contents or keys.

## Exact provider request ledger

| UTC time | Request | Provider/model | Status | Classification |
| --- | --- | --- | ---: | --- |
| 2026-09-27 11:35:13 | POST | Together / Qwen/Qwen2.5-7B-Instruct | 400 | Engineering connectivity; non-study prompt |
| 2026-09-27 11:48:04 | POST | Groq / openai/gpt-oss-20b | 200 | Engineering connectivity; non-study prompt |
| 2026-09-27 11:48:29 | POST | Gemini / models/gemini-2.5-flash | 404 | Engineering connectivity; non-study prompt |
| 2026-09-27 11:56:03 | POST | Together / meta-llama/Llama-3.3-70B-Instruct-Turbo | 200 | Engineering Diagnostic V2; non-study prompt |
| 2026-09-27 11:56:22 | POST | Groq / openai/gpt-oss-20b | 200 | Engineering Diagnostic V2; non-study prompt |
| 2026-09-27 11:56:37 | POST | Gemini / models/gemini-3.5-flash-lite | 200 | Engineering Diagnostic V2; non-study prompt |

The inventory result records one catalog GET each for Together, Groq, and Gemini (three GETs, no per-request status retained). Therefore: 6 actual inference/connectivity POSTs + 3 metadata GETs = 9 documented external provider HTTP calls. pi_ping_check_safe.py is source code; the readiness report says 
etwork_calls=0 and ping result missing. No separate ping output was found. DesignLab_Engineering_Pilot_Result.json is explicitly an engineering/non-study artifact, not Pilot A/B. No Pilot A or Pilot B run outputs were found. Confirmatory study runs remain 0.

## GitHub versus local

GitHub target main currently has 67 files and includes Phase 7 release ZIP/PDF and the readiness area (pi_ping_check_safe.py, 8_6_3_offline_readiness.py, CURRENT_READINESS_REPORT.json, three templates, and open-weight guidance Markdown). It does not contain the local API access inventory result, Engineering Pilot result, Provider Diagnostic V2 result, readiness ZIP package, or open-weight resolution JSON output. The local readiness report is BLOCKED with six blockers, 
etwork_calls=0, and confirmatory_data_collected=false.

The two local open-weight ZIPs contain the JSON resolution. Its embedded SHA-256 is 15adb82dbb2c217d53cccacb44b27ec02ee385434add8d60fe7cf28a9db8a571. The standalone Downloads Phase 7 PDF is 191,896 bytes and SHA-256 7bfa9d9b3229ef23650269b7292a655048442ee14f033537d18e8f64512f29ee; it differs from both GitHub PDFs (target repo 166,919 bytes; umbrella repo 167,139 bytes). The local Phase 7 ZIP SHA-256 is 7ba361c7f2c84ea6bdfd77572bf99e025ae413b3fa4a1ea4bdf69efc59e6f09, matching the GitHub release ZIP's content (same Git blob SHA-1).

Downloads copies of the readiness script/report and open-weight Markdown differ from their GitHub versions; the target D: checkout and older Desktop checkout match their respective repository snapshots. Use the CSV hash inventory for the exact per-file SHA-256 and Git blob identifiers.

## Local state and accountability

- D: current DesignLab checkout: D:\Reggae-shark-universe-\public-repositories\self-referential-processing-designlab, HEAD 10edbe34f1df741cfb4e7f3a7bb0dff4073e6186, 67 tracked files, clean.
- Desktop older clone: C:\Users\Asus\Desktop\reggaeshark_all_repos\self-referential-processing-designlab, HEAD d22004642aed0b1b37844c96203d07d93e5da71d, clean.
- Umbrella/mirror checkouts: local_repo_status.csv records status and submodule pointers. The sync parent has 12 changed paths, all outside the DesignLab repository; they are listed verbatim in that CSV. Its DesignLab submodule pointer remains 10edbe34....
- Screenshots supplied for this audit are hash-indexed in ttached_screenshot_hashes.csv.

## Hashing and bundle files

SHA-256 values are in local_artifact_inventory.csv, local_tracked_repo_file_hashes.csv, rchive_member_hashes.csv, and ttached_screenshot_hashes.csv. GitHub's API returns Git blob SHA-1; those values are in github_relevant_tree_paths.csv. SHA256SUMS.txt validates every bundle file except itself.

Included files: account repository list; GitHub relevant-tree manifest; GitHub/local comparison; requested-artifact status; local artifact inventory; tracked local repository file hashes; local Git status; provider request ledger; run count JSON; archive member hashes; screenshot hashes; search coverage; and this report.

## Limitations

These totals answer what the preserved local evidence records. No remote provider usage/billing log was queried, so the audit cannot prove that no unrecorded HTTP call occurred. File search and SHA-256 do not establish authorship by themselves; Git commit metadata and the local file state are the attribution evidence available here. The screenshots show the Downloads folder context, not independent proof of provider activity.

