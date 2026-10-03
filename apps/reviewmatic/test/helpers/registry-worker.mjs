// Regression helper for the shared review-worktree registry: one writer
// process holds the registry lock while reading, waits past any unlocked
// reader, and then saves. Without the lock a parallel writer loses one record.
const record = JSON.parse(process.argv[2]);
const { loadReviewRegistry, saveReviewRegistry, withReviewRegistryLock } = await import(
  new URL("../../dist/review-worktree.js", import.meta.url)
);

withReviewRegistryLock(() => {
  const registry = loadReviewRegistry();
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500);
  saveReviewRegistry({ schema: registry.schema, items: [...registry.items, record] });
});
