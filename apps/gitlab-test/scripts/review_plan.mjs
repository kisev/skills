// Deterministic review decisions are fixture inputs, not observed agent/critic behavior.
import { readFileSync, writeFileSync } from "node:fs";
import { startReview, checkReview, finishReview } from "../../reviewmatic/dist/draft.js";
import { readJson, writeJson } from "../../reviewmatic/dist/contract.js";
import { completeDraft } from "../../reviewmatic/test/helpers/review-fixture.mjs";

const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const result = await startReview({ url: input.url, repoRoot: input.repo, locale: "en" });
if (result.status !== "ok") throw new Error(JSON.stringify(result));
const draft = completeDraft(readJson(result.draft_path), result);
draft.run_id = input.run;
draft.session_id = "deterministic-harness-" + input.run;
draft.critics[0].run_id = "deterministic-fixture-critic";
draft.critics[0].session_id = "deterministic-fixture-session";
for (const thread of draft.content.thread_decisions) {
  thread.assessment = "neutral";
  thread.rationale = "Synthetic placement probe, not a claimed code defect.";
  thread.outcome = thread.state === "open" ? "reply" : "no_publication";
  thread.proposed_response =
    thread.state === "open" ? "Harness reviewmatic reply; correction is still pending." : null;
}
for (const job of draft.ci_job_assessments) {
  job.classification = "process_gate";
  job.rationale =
    "The fixture explicitly executes exit 1 with allow_failure to exercise real failing traces.";
  job.trace_evidence = "HARNESS_FAILURE";
}
writeJson(result.draft_path, draft);
const checked = await checkReview(result.draft_path);
if (checked.status !== "ok") throw new Error(JSON.stringify(checked));
const finished = await finishReview(result.draft_path);
if (finished.status !== "ok") throw new Error(JSON.stringify(finished));
const receipts = readJson(result.draft_path).critics;
writeFileSync(input.output, JSON.stringify({ started: result, finished, receipts }, null, 2));
console.log(JSON.stringify({ started: result, finished, receipts }));
