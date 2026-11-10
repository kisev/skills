# Merge request !42: bound retry writes

## Discussion 1 (open)

**alice (reviewer), 3 days ago:** The retry path calls the provider twice on timeout.

**you (author), 2 days ago:** I reserved an operation id before the first provider call.

**bob (reviewer), 2 days ago:** Please add a metric that counts duplicate-charge attempts.

**you (author), 1 day ago:** Good idea. I will add that metric in a follow-up.

**alice (reviewer), 1 hour ago:** Before merge: does the second attempt reuse the
operation id, and is the duplicate-charge metric in this MR?

## Discussion 2 (closed)

**alice (reviewer), 5 days ago:** The retry helper drops the original exception
when the provider times out; the cause is lost.

**you (author), 4 days ago:** I plan to chain the cause when I touch that helper.

**alice (reviewer), 3 days ago:** Closing this for now so the MR can move. The
exception is still swallowed on head `ca2fe509`.
