# Facts you established

- You (the merge request author) reserved an operation id before the first
  provider call.
- The second attempt reuses that same operation id.
- The duplicate-charge metric is not in this merge request. You only planned it
  for a follow-up and have not added it.
- You did not run the timeout test; the CI pipeline is the only evidence.
- The retry helper still drops the original exception on the current head
  `ca2fe509`. You have not fixed it.
