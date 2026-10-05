// Site-rendered installation commands. The root README install blocks are the
// canon for these commands; test/install-commands.test.mjs enforces parity.
const STANDALONE_COMPONENTS = ["memomatic", "taskmatic"];

export function integrationInstallCommands(channel) {
  const source = `https://kisev.github.io/skills${channel === "dev" ? "/dev" : ""}`;
  const componentPackages = STANDALONE_COMPONENTS.map((name) => `@kisev/${name}`);
  const reviewmaticSource =
    '"git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic"';
  const reviewmaticRef =
    channel === "dev"
      ? "dev # moving development branch, matching the dev skills channel"
      : "'<ref>' # use the exact release tag for the stable skills channel";
  const reviewmaticInstallCommand =
    channel === "dev" ? "uvx --refresh-package reviewmatic --from" : "uvx --from";
  const reviewmaticInstall = `REVIEWMATIC_REF=${reviewmaticRef}\n${reviewmaticInstallCommand} ${reviewmaticSource} reviewmatic --version`;
  const reviewmaticVerify = `uvx --from ${reviewmaticSource} reviewmatic --version`;
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
    reviewmaticInstall,
    "",
    "# Local installation and active CLIs",
    'npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0',
    `npm list --global ${componentPackages.join(" ")} --depth=0`,
    ...STANDALONE_COMPONENTS.map((name) => `${name} --version`),
    reviewmaticVerify,
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
