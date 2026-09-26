const TEAM_CITABLE_SOURCES = ["gitlab", "spec-manage"];

export type EntryVisibility = "team" | "personal";

/**
 * Usage-level visibility derived from the entry source. Team-prefixed skills,
 * the GitLab collector, and spec-manage produce entries citable in
 * team-facing artifacts; every other source stays personal-only.
 */
export function visibilityForSource(source: string | null | undefined): EntryVisibility {
  if (!source) return "personal";
  if (TEAM_CITABLE_SOURCES.includes(source) || source.startsWith("team-")) return "team";
  return "personal";
}
