/**
 * YAML loader for workflow, agent, and resource definitions.
 *
 * String-based — no filesystem access. Accepts YAML strings and returns
 * validated, typed objects.
 */

import yaml from "yaml";

// TODO: These imports will resolve once the schemas package is created by the
// parallel agent. For now they reference the expected module paths.
import {
  type WorkflowDefinition,
  workflowDefinitionSchema,
} from "../schemas/workflow.js";
import {
  type AgentDefinition,
  agentDefinitionSchema,
} from "../schemas/agent.js";
import {
  type ResourceDefinition,
  resourceDefinitionSchema,
} from "../schemas/resource.js";

export type { WorkflowDefinition, AgentDefinition, ResourceDefinition };

/**
 * Parse a YAML string into a validated WorkflowDefinition.
 *
 * @throws {Error} If the YAML is invalid or fails schema validation.
 */
export function parseWorkflowYaml(yamlString: string): WorkflowDefinition {
  const raw = yaml.parse(yamlString);
  if (!raw || typeof raw !== "object") {
    throw new Error("Invalid YAML: expected an object");
  }
  return workflowDefinitionSchema.parse(raw);
}

/**
 * Parse a YAML string into a validated AgentDefinition.
 *
 * @throws {Error} If the YAML is invalid or fails schema validation.
 */
export function parseAgentYaml(yamlString: string): AgentDefinition {
  const raw = yaml.parse(yamlString);
  if (!raw || typeof raw !== "object") {
    throw new Error("Invalid YAML: expected an object");
  }
  return agentDefinitionSchema.parse(raw);
}

/**
 * Parse a YAML string into a validated ResourceDefinition.
 *
 * @throws {Error} If the YAML is invalid or fails schema validation.
 */
export function parseResourceYaml(yamlString: string): ResourceDefinition {
  const raw = yaml.parse(yamlString);
  if (!raw || typeof raw !== "object") {
    throw new Error("Invalid YAML: expected an object");
  }
  return resourceDefinitionSchema.parse(raw);
}

/**
 * Parse a workflow filename into [id, version].
 *
 * Supports:
 * - `feature-planning@1.0.0.yaml` -> `["feature-planning", "1.0.0"]`
 * - `simple-workflow.yaml` -> `["simple-workflow", "1.0.0"]`
 */
export function parseWorkflowFilename(
  filename: string,
): [id: string, version: string] {
  const versionPattern = /^(.+?)@(\d+\.\d+\.\d+)\.ya?ml$/;
  const match = versionPattern.exec(filename);
  if (match) {
    return [match[1], match[2]];
  }
  // No version in filename — default to 1.0.0
  const stem = filename.replace(/\.ya?ml$/, "");
  return [stem, "1.0.0"];
}
