# ACA Dataset and DataPackage Design

[English](dataset-and-datapackage-design.md) | [简体中文](dataset-and-datapackage-design.zh-CN.md)

## Objective

Build a dataset for training, evaluation, and research on personalized code repair and counterexample generation. Every submission must be a real, replayable incorrect program: it must receive both AC and non-AC verdicts on the same frozen testcase set while retaining the code, inputs, outputs, verdicts, and line-coverage evidence. Problem assets and submission assets are managed separately so that sampling the same problem again does not require replenishing assets or repeating API calls.

The first experimental release is named **v0.2**: 1,000 training submissions and 100 test submissions, with a Python:C++ ratio of 4:6. The training and test splits must have no overlap in problems, users, source hashes, or canonical code IDs.

## Raw Data Requirements

### Submission-level hard constraints

- The submission comes from the consumable mixed submissions in Step7: correctness is complete, coverage is available and consistent with correctness replay, Step6 succeeded, and both candidate covered lines and effective uncovered lines are non-empty.
- There are at least 16 frozen cases, including at least 2 AC and at least 2 non-AC cases.
- Preserve the original code, language, user, problem, canonical code ID/source hash, and each case's input, expected output, actual output, final verdict, coverage bitmap, candidate lines, and effective uncovered lines.
- Duplicate source hashes or canonical code IDs are not retained within a split, and they must not overlap between training and test splits.
- When the original C++ stdout is missing, replay may fill it in, but must not overwrite the original Step4 verdict or per-case verdict. Replay fields must remain separate.

### Split and distribution hard constraints

- `problem_id` has zero overlap between train and test.
- `user_id` has zero overlap between train and test.
- Source identifiers have zero overlap between train and test.
- Singleton users and singleton problems are not allowed. Real short submission trajectories from a user on the same problem are retained without artificial duplication.
- The language ratio is fixed at Python:C++ = 4:6.

### Distribution soft targets

- Submission counts by user and problem must not be extremely concentrated or mechanically uniform.
- Difficulty, incorrect behavior, and problem type should be smooth and diverse where possible. Incorrect submissions for the same problem should also remain distinct.
- If the soft targets cannot all be met, preserve every hard constraint and document the reason in the manifest or report.

## Data Foundation from Steps 4-7

Step4 runs frozen cases and records correctness and per-case coverage. Submissions that are entirely AC or entirely non-AC do not receive coverage; mixed submissions proceed to coverage. Without deleting the original uncovered lines, Step6 produces `effective_uncovered_lines` by excluding cross-language-alignable unused top-level functions/classes, meaningless constant initialization, I/O, debug output, and control-flow boilerplate. Parse failures fall back to the original uncovered lines and are marked. Step7 does not rewrite the original records; it outputs the submissions that pass the quality gate.

The DataPackage therefore does not re-decide the primary conclusions from Steps 4-7. It only completes the replayable evidence and problem assets needed by downstream consumers.

## DataPackage

The DataPackage is a reusable release pipeline, not a one-off script. It has two logical steps.

### Step 1: Complete submission replay

Step1 completes only submission assets. It neither changes problem assets nor filters the data again.

- Python/C: the original stdout is complete and is parsed directly into the unified consumer field `actual_stdout_resolved`.
- C++: if original stdout is missing, replay **all frozen cases** for that submission in separate processes; compile once, but run every case in its own directory and process.
- Write `replay_stdout`, `replay_verdict`, and `replay_verdict_drift`; do not overwrite `final_verdict`, original stdout, or original per-case verdicts.
- Lock and record the replay environment: compiler/version, compile flags, timeout, memory limit, sandbox version, judge mode, and output-comparison rules.

Step1 acceptance criteria: for every C++ submission requiring replay, the replay case count equals the frozen case count; each replay case has stdout or an explicit timeout/runtime/no-output state; the drift count is recorded; and user/problem/hash isolation and deduplication still hold.

### Step 2: Reusable problem asset library

Step2 builds a problem asset library indexed by `problem_id`. Assets are reused across languages and produced lazily: existing assets are reused first and missing assets are completed only when required. Each problem fixes the following evaluation definition:

`problem_id -> validator_hash, fixed_ref_hash, judge_rule, frozen testcase set`

These definitions must not change online after an experiment begins. If a problem is found to be invalid, remove it from the certified set instead of replacing its reference or validator online.

#### Validator / judge

Prefer the testlib validator source provided in the CodeContests+ parquet rather than asking an LLM to infer one from the statement. The validator defines valid input, and every frozen case must pass it. Only when an official validator is unavailable should a strong model generate a candidate validator from the statement, followed by malformed, boundary, and structural fuzz QA.

Check enforceable structural constraints such as trees, connectivity, permutations, uniqueness, and totals across multiple tests. If a statement's “a solution is guaranteed to exist” condition is itself close to solving the problem, mark it as `semantic_unchecked/high_risk` instead of presenting an incomplete validator as complete. The small number of affected problems may be excluded from the certified set.

#### Fixed reference

Existing frozen cases do not require a reference to obtain answers; the reference is used for newly generated valid inputs. Candidates may come from old ACA references, multiple AC submissions, strong-model code, or manual repairs, but disagreements must be resolved during construction. Each problem ultimately locks one `fixed_ref`: it passes every frozen case and boundary/stress case, and agrees with other high-confidence candidates on stress cases. It is a peer/constructed reference and must not be described as an official reference.

#### Blind probes

A blind probe is a construction-time difficulty probe, not an official testcase, and is not written directly into the certified frozen testcase set. The flow is:

`Qwen blind generator -> validator -> fixed ref -> target submission replay`

Only candidates accepted by the validator and successfully executed by the fixed reference participate in submission-level evaluation. Run all valid probes for each target submission independently, with isolated case directories and processes. Blind output records the probe count, valid probe count, countercase count, first evidence, and generation provenance.

Probes generated in the same model round are correlated, so a submission is not removed after a single hit. One to three hits become a difficulty label; persistent hits in 4/5 rounds mark it `easily_hacked` and exclude it from final selection. The small number of problems for which the model repeatedly fails to produce valid formatting are discarded from the candidate problem pool instead of being mixed into unscreened data.

## Output Package

The v0.2 release directory must contain at least:

- `train/submissions.jsonl.zst` and `test/submissions.jsonl.zst`: the final, Step1-complete submission sets.
- `train/problems.jsonl.zst` and `test/problems.jsonl.zst`: the corresponding complete problem assets, including statements, frozen cases, validators, fixed references, and judge definitions.
- Blind-gate metadata: generation model/prompt version, per-submission probe statistics, countercase statistics, and exclusion status.
- `manifest.json`: version, random seed, language and count quotas, quality gates, environment versions, and asset hashes.
- `audit/report.json`: split isolation, singletons, source hashes, replay drift, validator/reference certification, and blind-screening statistics.

The problem assets in the package must be closed: every submission's referenced problem, frozen inputs, expected outputs, validator, fixed reference, and judge rules must be available in the same package version.

## Confidence Boundaries

The original frozen cases and their Step4 execution records are the strongest evidence. A testlib validator is an executable input-domain definition. A fixed reference is a construction-time peer/constructed reference, not a purported official solution. Blind probes label difficulty and filter anomalous submissions; they do not change the original benchmark verdict. These layers must remain explicit in both fields and documentation.

## Dataset Production SOP

1. **Freeze inputs.** Specify the Step7 submission source, problem source, target language ratio, train/test counts, random seed, and quality gates in versioned configuration. Do not change quotas during execution or introduce undeclared data sources.
2. **Build an oversampled candidate pool.** Stream approximately 120% of the target count from Step7. Apply correctness, coverage, Step6, and code-hash quality gates first, then enforce candidate-level user/problem/code isolation and the absence of singletons. Fail if the pool is insufficient; do not fill it by copying or synthesizing submissions.
3. **Complete and certify problem assets.** Look up candidate problems in the asset library, preferring CodeContests+ testlib validators and verified references. Confirm that the validator accepts every frozen case and that the fixed reference passes every frozen case. Mark and remove failures from the candidate pool. Record validator/reference hashes and the execution environment.
4. **Generate and validate blind probes.** Generate candidate inputs for each problem using a fixed model, prompt version, and generation parameters. Retry formatting failures a limited number of times and remove persistent failures. Pass every input through the validator and fixed reference; only inputs for which both succeed become valid probes.
5. **Run the submission-level blind gate.** Execute every valid probe against every candidate submission in its own process. Save the hit count, first countercase, and stderr. Apply the release's explicit threshold to mark `easily_hacked`, without overwriting the original Step4 verdict.
6. **Perform the final sample once.** Select the target 1,000/100 only from certified problems that completed the blind gate and are not marked `easily_hacked`. Re-enforce zero overlap of users, problems, and code hashes between train and test, along with language quotas. If hard constraints cannot be met, report the shortfall and expand the candidate pool in the next version; never silently relax constraints or add samples online.
7. **Run Step1 replay.** Compile once and replay missing-stdout C++ submissions in isolated per-case processes. Write replay fields and drift without changing original records. Do not needlessly rerun Python/C.
8. **Assemble the release package.** Write train/test submissions, closed problem sets, blind metadata, validators/references, locked environment information, manifest, and audit report. Record SHA-256 for every compressed streaming file.
9. **Final acceptance.** Check counts and language ratio, all three isolation constraints, absence of singletons, source-hash deduplication, complete problem assets for every submission, replay completeness/drift, validator/reference certification, blind-screening coverage, and archive hashes. Manually review a sample of submissions for consistency among code, cases, stdout, verdicts, coverage, and uncovered lines.
10. **Freeze after release.** Treat the version directory as a read-only source of truth. Fixes or expansions create a new version and manifest; never rewrite an old version.
