/**
 * Elicitation Service — maps CaptureDefinition to MCP elicit JSON Schema calls.
 *
 * Uses raw JSON Schema (not Zod) since MCP protocol expects JSON Schema objects.
 */

import type { CaptureDefinition } from "../schemas/workflow.js";
import type { ElicitResult } from "./mcp-server.js";

// ---------------------------------------------------------------------------
// ElicitationService
// ---------------------------------------------------------------------------

export class ElicitationService {
  /**
   * Filter captures that still need elicitation.
   *
   * - `elicit="always"` -> always
   * - `elicit="if_missing"` -> only if key not in stateData
   * - `elicit="never"` -> skip
   */
  static needsElicitation(
    captures: CaptureDefinition[],
    stateData: Record<string, unknown>,
  ): CaptureDefinition[] {
    const result: CaptureDefinition[] = [];
    for (const cap of captures) {
      if (cap.elicit === "always") {
        result.push(cap);
      } else if (cap.elicit === "if_missing" && !(cap.key in stateData)) {
        result.push(cap);
      }
      // elicit="never" -> skip
    }
    return result;
  }

  /**
   * Build a JSON Schema object for the MCP elicit call based on the capture's
   * input type.
   *
   * Mapping:
   * - text / null / unknown -> `{ type: "string" }`
   * - number -> `{ type: "number" }`
   * - boolean / confirm -> `{ type: "boolean" }`
   * - select -> `{ type: "string", enum: [...] }`
   * - multi-select -> `{ type: "array", items: { type: "string", enum: [...] } }`
   */
  static buildRequestedSchema(
    capture: CaptureDefinition,
  ): Record<string, unknown> {
    const title = capture.label ?? capture.key;
    const inputType = capture.input;

    if (inputType === "confirm" || inputType === "boolean") {
      return {
        type: "object",
        properties: {
          value: { type: "boolean", title },
        },
        required: ["value"],
      };
    }

    if (inputType === "number") {
      return {
        type: "object",
        properties: {
          value: { type: "number", title },
        },
        required: ["value"],
      };
    }

    if (inputType === "select") {
      if (capture.options && capture.options.length > 0) {
        const enumValues = capture.options.map((o) => o.key);
        const hasLabels = capture.options.some((o) => o.label !== o.key);
        const prop: Record<string, unknown> = {
          type: "string",
          title,
          enum: enumValues,
        };
        if (hasLabels) {
          const descriptions: Record<string, string> = {};
          for (const o of capture.options) {
            descriptions[o.key] = o.label;
          }
          prop["x-enum-descriptions"] = descriptions;
        }
        return {
          type: "object",
          properties: { value: prop },
          required: ["value"],
        };
      }
      return {
        type: "object",
        properties: { value: { type: "string", title } },
        required: ["value"],
      };
    }

    if (inputType === "multi-select") {
      if (capture.options && capture.options.length > 0) {
        const enumValues = capture.options.map((o) => o.key);
        const hasLabels = capture.options.some((o) => o.label !== o.key);
        const itemSchema: Record<string, unknown> = {
          type: "string",
          enum: enumValues,
        };
        if (hasLabels) {
          const descriptions: Record<string, string> = {};
          for (const o of capture.options) {
            descriptions[o.key] = o.label;
          }
          itemSchema["x-enum-descriptions"] = descriptions;
        }
        return {
          type: "object",
          properties: {
            value: { type: "array", title, items: itemSchema },
          },
          required: ["value"],
        };
      }
      return {
        type: "object",
        properties: { value: { type: "string", title } },
        required: ["value"],
      };
    }

    // text, null, or unknown -> string
    return {
      type: "object",
      properties: {
        value: { type: "string", title },
      },
      required: ["value"],
    };
  }

  /**
   * Build a human-readable elicit message from a capture definition.
   */
  static buildMessage(capture: CaptureDefinition): string {
    const label = capture.label ?? capture.key;
    const parts: string[] = [label];

    if (capture.placeholder) {
      parts.push(`(e.g. ${capture.placeholder})`);
    }

    if (capture.default !== undefined && capture.default !== null) {
      parts.push(`[default: ${capture.default}]`);
    }

    return parts.join(" ");
  }

  /**
   * Process an ElicitResult.
   *
   * - `action === "accept"` -> `[capture.key, extractedValue]`
   * - `action === "decline" | "cancel"` -> `null`
   */
  static processResult(
    capture: CaptureDefinition,
    result: ElicitResult,
  ): [string, unknown] | null {
    if (result.action === "accept" && result.content) {
      // Extract value from the wrapper object
      const data = result.content;
      if ("value" in data) {
        return [capture.key, data["value"]];
      }
      // Fallback: return entire content
      return [capture.key, data];
    }
    return null;
  }
}
