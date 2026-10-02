import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { startReview } from "../../../../apps/reviewmatic/dist/draft.js";
import { artifactPayload } from "../../../../apps/reviewmatic/dist/contract.js";

const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const started = await startReview({ url: input.url, repoRoot: input.repo, locale: "en" });
assert.equal(started.status, "ok");
assert.equal(started.role, "author");
const [, evidence] = artifactPayload(started.evidence_path, "evidence_snapshot");
assert.equal(evidence.head_sha, input.head);
assert.equal(evidence.retrieval_complete, true);
assert.ok(evidence.labels.pages >= 2);
assert.equal(started.external_mutations, false);
console.log(
  JSON.stringify({ started, head: evidence.head_sha, labels_pages: evidence.labels.pages }),
);
