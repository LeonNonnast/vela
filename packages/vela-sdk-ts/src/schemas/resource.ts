/**
 * Zod schemas for resource definitions.
 *
 * Schema version: 0.1.0
 * Field names use snake_case to match YAML format.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// ResourceType
// ---------------------------------------------------------------------------

export const resourceTypeSchema = z.enum([
  "schema",
  "example",
  "scaffold",
  "skill",
  "convention",
  "reference",
]);

export type ResourceType = z.infer<typeof resourceTypeSchema>;

// ---------------------------------------------------------------------------
// ResourceDefinition
// ---------------------------------------------------------------------------

/**
 * Resource definition loaded from YAML.
 *
 * Resources are registered as MCP Resources. They provide reference material
 * (schemas, examples, conventions) that workflows and agents can inline or
 * reference on-demand.
 */
export const resourceDefinitionSchema = z.object({
  id: z.string(),
  name: z.string(),
  type: resourceTypeSchema,
  description: z.string().default(""),
  content: z.string().default(""),
  mime_type: z.string().default("text/plain"),
  tags: z.array(z.string()).default([]),
  uri_pattern: z.string().nullish(),
});

export type ResourceDefinition = z.infer<typeof resourceDefinitionSchema>;

// ---------------------------------------------------------------------------
// ResourceReference
// ---------------------------------------------------------------------------

/**
 * Reference to a resource, used in workflow/step definitions.
 *
 * Controls whether the resource content is inlined into the prompt
 * or provided as a URI reference for on-demand loading.
 */
export const resourceReferenceSchema = z.object({
  ref: z.string(),
  inline: z.boolean().nullish(),
});

export type ResourceReference = z.infer<typeof resourceReferenceSchema>;
