// Module-resolution hook for running the unbuilt TypeScript CLI sources under
// Node type stripping: relative `./x.js` specifiers inside `src/` resolve to
// their `.ts` files, so the generator executes the real reviewmatic sources.
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

export function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith(".") && specifier.endsWith(".js") && context.parentURL) {
    const candidate = new URL(`${specifier.slice(0, -3)}.ts`, context.parentURL);
    if (existsSync(fileURLToPath(candidate))) return nextResolve(candidate.href, context);
  }
  return nextResolve(specifier, context);
}
