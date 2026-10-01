export function integrationInstallCommands(channel) {
  const source = `https://kisev.github.io/skills${channel === "dev" ? "/dev" : ""}`;
  return [
    "# Registry versions",
    "npm view --prefer-online skills@latest version",
    `npm view --prefer-online @kisev/agentomatic@${channel} version`,
    "",
    "# Install and confirm the OpenCode setup",
    `npx --yes skills@latest add ${source} --global`,
    `npx --yes @kisev/agentomatic@${channel} install --global`,
    "",
    "# Installed dependency and skills",
    'npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0',
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
