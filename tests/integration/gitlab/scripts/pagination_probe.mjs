import { readFileSync } from "node:fs";
import { paginated } from "../../../../apps/reviewmatic/dist/contract.js";

const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
console.log(
  JSON.stringify(
    Object.fromEntries(
      Object.entries(input.endpoints).map(([name, endpoint]) => [
        name,
        paginated("localhost", endpoint),
      ]),
    ),
  ),
);
