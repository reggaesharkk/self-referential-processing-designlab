# Self-Referential Processing Design Lab

I’m Prince Upadhyay. I study a question about how language models judge answers: **does a model evaluate an answer differently when it wrote that answer itself?** Recognizable wording can complicate that comparison. A model might respond to a familiar writing style even when two answers convey the same information.

## How I study the question

I separate three questions that are easy to confuse. Can I measure a difference reliably? Can I change an answer’s style while keeping it useful? And does authorship affect the model’s judgment?

I used simulations to tackle the first question. In Phase 7, I set the size of the authorship effect myself, including a condition with zero effect, then checked how well two statistical models recovered it. I locked the comparison before running 4,000 fits. One model met my criteria for further study. [Phase 7 design lock](research/phase7/phase7_design_lock.md) · [Technical report](research/phase7/final_release/DesignLab_Phase7_Final_Technical_Report_v1.0.md)

My current v9 experiment tackles the second question. I collect an answer, make a small wording change, and give it to a **different model family** to rewrite in a neutral style. The original model then makes two yes/no judgments: is the rewrite still useful, and did it remove noticeable style while preserving utility? I keep the original item, the roles of the models, and the outcome of each stage linked in the run record. These checks tell me how well the procedure works before I draw conclusions about authorship. [v9 method and analysis rules](research/v9_0_prospective/README.md)

## My master lock and research record

**My frozen protocol is recorded in `MASTER_LOCK_v8_6_3.md`.** It is the reference for what I specified in advance. My readiness audit records the recovered lock’s SHA-256 as `b3394f637a73ffe835866862d4781cb8928e137c586bd8d79241d9c3713ccbbf`. I keep the consolidated research record on OSF alongside the earlier foundation. [Consolidated OSF record](https://osf.io/nv7dz/) · [Original foundation](https://osf.io/37h2y/) · [Master-lock verification record](research/v8_6_3_readiness/README.md)

Collection under v8.6.3 is paused. I pinned all 12 open-weight model sources, but the audit still required final model deployments, closed-provider snapshot evidence, endpoint checks, and a locked runtime. I track the later v9 work under its own model and analysis rules.

## My live v9 work

I recorded five Pilot B runs, one 50-item Pilot A run, and one partial OpenRouter confirmatory run. Pilot B passed all four model slots on its five-item slice. The OpenRouter run stopped making successful requests after a credit error. I keep the per-run counts, costs, and receipts in the [accountability ledger](research/v9_0_prospective/provenance_2026_11_26/run_count_summary.json).

### Local GPU checkpoints · 28 November 2026

I plan to process the same 260 items with each of four model families. So far I have processed **420 of 1,040 model/item pairs**. Of those, 374 completed all five stages and 46 were skipped after the neutral rewrite missed the 45–55 word window. I recorded 2,804 local generations and USD 0.00 in external inference spend.

| Tested family | Processed | Complete | Skipped | Remaining | Generations |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen 7B | 260 | 246 | 14 | 0 | 1,726 |
| Gemma 9B | 160 | 128 | 32 | 100 | 1,078 |
| Llama 8B | 0 | 0 | 0 | 260 | 0 |
| Mistral 7B | 0 | 0 | 0 | 260 | 0 |

I archive successive checkpoints so readers can trace each run as it progresses. [Checkpoint archive](research/v9_0_prospective/confirmatory_receipts/)

**Rights boundary — effective 1 October 2026:** I reserve new author-owned original material first published here from this date. Earlier express licenses remain in force for the material they cover. I follow [my rights policy](RIGHTS_POLICY_2026_10_01.md) and [my portfolio evidence standard](https://github.com/reggaesharkk/Reggae-shark-universe-/blob/main/PORTFOLIO_EVIDENCE_AND_RIGHTS_STANDARD_2026_10_01.md).
