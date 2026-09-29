import type { Observe } from "./generated/cli.js";
export type OperationOptions = { signal?: AbortSignal; observe?: Observe; force?: boolean };
export function check(options: OperationOptions): void {
  options.signal?.throwIfAborted();
}
