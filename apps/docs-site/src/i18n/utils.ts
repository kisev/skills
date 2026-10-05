import type { Locale } from "./ui";

export function basePath(): string {
  return import.meta.env.BASE_URL.replace(/\/+$/, "");
}

export function withBase(path: string): string {
  const base = basePath();
  if (path === "/") {
    return `${base}/`;
  }
  return `${base}${path}`;
}

/**
 * Returns the locale-aware href for a locale-neutral site route such as
 * `/skills/`. Every internal link in templates must go through this builder
 * (or `alternateLocalePath`); the contract test fails on hand-built hrefs.
 */
export function localizedPath(path: string, locale: Locale): string {
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new Error(`localizedPath expects a site route starting with "/": ${path}`);
  }
  const route = path === "/" ? "/" : path;
  return withBase(locale === "en" ? route : `/ru${route}`);
}

/** Returns the same page in the other locale, keeping base and subpaths. */
export function alternateLocalePath(pathname: string, locale: Locale): string {
  const base = basePath();
  const withoutBase = pathname.startsWith(base) ? pathname.slice(base.length) : pathname;
  const route = withoutBase === "" || withoutBase === "/" ? "/" : withoutBase;
  const other: Locale = locale === "en" ? "ru" : "en";
  const stripped =
    other === "en" ? (route.startsWith("/ru/") ? route.slice(3) : route) : `/ru${route}`;
  const normalized = stripped === "" ? "/" : stripped;
  return withBase(normalized);
}

export function exampleAnchor(skill: string, order: number): string {
  return `example-${skill}-${order}`;
}
