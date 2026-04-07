/**
 * Zod schema for agent definitions.
 *
 * Field names use snake_case to match YAML format.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// AgentDefinition
// ---------------------------------------------------------------------------

export const agentDefinitionSchema = z.object({
  id: z.string(),
  name: z.string(),
  persona: z.string().default(""),
  greeting: z.string().default(""),
  workflows: z.array(z.string()).default([]),
  tools: z.array(z.string()).default([]),
});

export type AgentDefinition = z.infer<typeof agentDefinitionSchema>;
