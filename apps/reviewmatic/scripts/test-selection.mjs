// The experimental interface is excluded explicitly, not by a backend module path.
export const experimentalTests = new Set([
  "tui-app.test.mjs",
  "tui-pty.test.mjs",
  "tui-support.test.mjs",
]);

export function backendTests(names) {
  return names.filter((name) => name.endsWith(".test.mjs") && !experimentalTests.has(name)).sort();
}
