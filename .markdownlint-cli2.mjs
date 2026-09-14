export default {
  config: {
    default: true,
    MD001: false,
    MD013: false,
    MD024: false,
    MD025: false,
    MD033: false,
    MD041: false,
    MD060: false,
  },
  globs: [
    "**/*.md",
    "!.build/**",
    "!.venv/**",
    "!packages/opencode/dist/**",
    "!**/node_modules/**",
    "!RESEARCH*.md",
    "!TODO*.md",
  ],
};
