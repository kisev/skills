// Site-rendered installation commands. The root README install blocks are the
// canon for these commands; test/install-commands.test.mjs enforces parity.
const PAGES = "https://kisev.github.io/skills";
const REVIEWMATIC_SOURCE =
  '"git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic"';

export function integrationInstallCommands(channel) {
  if (channel === "dev") {
    return [
      "# Published prereleases and unpublished checkout content",
      "uvx --prerelease skillmate --version",
      "skillmate install --from-checkout /path/to/skills --yes   # unpublished working-tree content",
      "",
      "# Reviewmatic from the moving dev branch",
      "REVIEWMATIC_REF=dev # moving development branch, matching the dev skills channel",
      `uvx --refresh-package reviewmatic --from ${REVIEWMATIC_SOURCE} reviewmatic --version`,
    ].join("\n");
  }
  return [
    "# Distribution version",
    "uvx skillmate status",
    "",
    "# Install into the project for all three hosts",
    "uvx skillmate install --yes",
    "",
    "# Or globally, or for selected hosts and skills",
    "uvx skillmate install --scope global --hosts claude,opencode --yes",
    "uvx skillmate doctor",
    "",
    "npm view --prefer-online skills@latest version",
    `npx --yes skills@latest add ${PAGES} --global`,
    "npx --yes skills@latest update --global",
    "npx --yes skills@latest list --global",
    "",
    "REVIEWMATIC_REF='<ref>' # use the exact release tag for the stable skills channel",
    `uvx --from ${REVIEWMATIC_SOURCE} reviewmatic --version`,
  ].join("\n");
}

export function skillInstallCommands(name) {
  return [
    "# Registry version of the installer",
    "npm view --prefer-online skills@latest version",
    "",
    "# Install this skill in the current project",
    `npx --yes skills@latest add ${PAGES} --skill ${name}`,
    "",
    "# Installed skills in this project",
    "npx --yes skills@latest list",
  ].join("\n");
}
