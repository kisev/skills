# Draft Notes

Publication goes through GitLab draft notes. The runbook ends with one
non-interactive `sh` block that creates drafts; the human opens the merge
request in the GitLab UI, edits the drafts, and submits the review there. No
publish command exists, and the skill performs no GitLab mutation.

## Input

Author the draft input as JSON and let the runtime generate the block:

```shell
reviewmatic drafts --input .reviewmatic/drafts.json --output .reviewmatic/drafts.sh
```

The input carries the target and the reviewed head:

```json
{
  "hostname": "gitlab.example.com",
  "project_id": 123,
  "mr_iid": 45,
  "head_sha": "<exact reviewed head>",
  "findings": [
    {
      "old_path": "src/a.py",
      "new_path": "src/a.py",
      "new_line": 12,
      "base_sha": "<base>",
      "start_sha": "<start>",
      "body": "The finding's essence and the minimum fix."
    }
  ],
  "general_notes": ["A note that has no diff position."],
  "discussion_replies": [
    {"discussion_id": "<id>", "body": "The first-person reply."}
  ]
}
```

A finding with `old_line`, `new_line`, `old_path`, or `new_path` becomes a
positioned diff draft; a finding without them becomes a general merge request
draft. A `discussion_replies` entry uses `in_reply_to_discussion_id`; set
`"draft_reply_support": false` only when the target GitLab does not support
draft replies, and the runtime then emits a general draft instead of losing the
reply.

The block starts with one head check against `head_sha` and exits before
creating any draft when the head moved. Run it once, then edit and publish in
the UI. Never edit the generated commands by hand.

## Replies

Prepare a reply for every open discussion where one is needed, and for a
closed discussion only when the problem is still present on the current head;
pair that reply with a reopen request. A closed discussion whose problem is
resolved gets no reply. Write every reply under `discussion-replies.md` and
`clarity-rules.md`; the optional final editing pass reads
`humanize-patterns.md`.

Replies are published as drafts, never directly. The subject discussion's id
comes from the collected discussions; preserve it exactly.
