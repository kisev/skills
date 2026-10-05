import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro:schema";

/**
 * One worked interaction example per document. The file name must match the
 * skill name (`commit-msg.md`), the first path segment is the locale, and a
 * schema violation fails the site build.
 */
const examples = defineCollection({
  loader: glob({ pattern: ["en/*.md", "ru/*.md"], base: "./src/content/examples" }),
  schema: z.object({
    skill: z.string(),
    title: z.string().min(1),
    order: z.number().int(),
    prompt: z.string().min(1),
    steps: z
      .array(
        z.object({
          title: z.string().min(1),
          detail: z.string().optional(),
        }),
      )
      .min(1),
    artifacts: z
      .array(
        z.object({
          label: z.string().min(1),
          language: z.string().default("text"),
          content: z.string().min(1),
        }),
      )
      .min(1),
    limitations: z.string().optional(),
  }),
});

export const collections = { examples };
