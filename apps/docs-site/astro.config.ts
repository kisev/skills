import { defineConfig } from "astro/config";

// The site deploys to the GitHub Pages project URL https://kisev.github.io/skills
// next to the installer distribution endpoints, so every URL is base-prefixed.
export default defineConfig({
  site: "https://kisev.github.io",
  base: "/skills",
  i18n: {
    locales: ["en", "ru"],
    defaultLocale: "en",
    routing: { prefixDefaultLocale: false },
  },
  build: { format: "directory" },
});
