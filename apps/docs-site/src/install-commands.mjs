// Site-rendered installation commands. The root README install blocks are the
// canon for these commands; test/install-commands.test.mjs enforces parity.
const STANDALONE_COMPONENTS = ["memomatic", "reviewmatic", "taskmatic"];

export function integrationInstallCommands(channel) {
  const source = `https://kisev.github.io/skills${channel === "dev" ? "/dev" : ""}`;
  const componentPackages = STANDALONE_COMPONENTS.map((name) => `@kisev/${name}`);
  return [
    "# Registry versions",
    "npm view --prefer-online skills@latest version",
    `npm view --prefer-online @kisev/agentomatic@${channel} version`,
    ...STANDALONE_COMPONENTS.map(
      (name) => `npm view --prefer-online @kisev/${name}@${channel} version`,
    ),
    "",
    "# Install and configure",
    `npx --yes skills@latest add ${source} --global`,
    "npx --yes skills@latest update --global",
    `npx --yes @kisev/agentomatic@${channel} install --global`,
    `npx --yes @kisev/agentomatic@${channel} configure integration --global`,
    ...componentPackages.map(
      (name) => `npm install --global ${name}${channel === "dev" ? "@dev" : ""}`,
    ),
    "",
    "# Local installation and active CLIs",
    'npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0',
    `npm list --global ${componentPackages.join(" ")} --depth=0`,
    ...STANDALONE_COMPONENTS.map((name) => `${name} --version`),
    "npx --yes skills@latest list --global",
  ].join("\n");
}

export function skillInstallCommands(name) {
  return [
    "# Registry version of the installer",
    "npm view --prefer-online skills@latest version",
    "",
    "# Install this skill in the current project",
    `npx --yes skills@latest add https://kisev.github.io/skills --skill ${name}`,
    "",
    "# Installed skills in this project",
    "npx --yes skills@latest list",
  ].join("\n");
}
