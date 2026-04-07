/**
 * Session elicitation helpers — param collection and resume-or-new flows.
 *
 * Provides functions for eliciting required workflow params, choosing
 * between active sessions, and handling the full missing-params flow.
 */

import type { WorkflowRunState } from "../engine/types.js";
import type { Locale } from "../locale/locale.js";
import { getLocale } from "../locale/locale.js";
import type {
  ParamDefinition,
  WorkflowDefinition,
} from "../schemas/workflow.js";
import type { McpContext } from "./mcp-server.js";
import { buildRunOptions } from "./response-builder.js";

// ---------------------------------------------------------------------------
// elicitRequiredParams
// ---------------------------------------------------------------------------

/**
 * Elicit values for required params.
 *
 * Returns a dict of param values, or `null` if the user cancels.
 * Returns `{}` if elicitation is not supported.
 */
export async function elicitRequiredParams(
  ctx: McpContext,
  paramDefs: ParamDefinition[],
  locale?: Locale,
): Promise<Record<string, unknown> | null> {
  const result: Record<string, unknown> = {};

  for (const pDef of paramDefs) {
    const label = pDef.label ?? pDef.name;
    const description = pDef.description ? ` \u2014 ${pDef.description}` : "";
    let message = `${label}${description}`;
    if (pDef.default !== undefined && pDef.default !== null) {
      message += ` [default: ${pDef.default}]`;
    }

    const schema: Record<string, unknown> = {
      type: "object",
      properties: {
        value: { type: "string", title: label },
      },
      required: ["value"],
    };

    let elicitResult;
    try {
      elicitResult = await ctx.elicit(message, schema);
    } catch {
      ctx.log.debug("elicitation.not_supported", { key: pDef.name });
      return {};
    }

    if (
      elicitResult.action === "accept" &&
      elicitResult.content &&
      "value" in elicitResult.content &&
      elicitResult.content["value"]
    ) {
      result[pDef.name] = elicitResult.content["value"];
    } else if (pDef.default !== undefined && pDef.default !== null) {
      result[pDef.name] = pDef.default;
    } else {
      return null;
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// elicitSessionChoice
// ---------------------------------------------------------------------------

/**
 * Elicit a resume-or-new choice from the user.
 *
 * Returns `[chosenRun, null]` if an existing run was selected,
 * `[null, "__new__"]` if the user chose to start new, or
 * `[null, null]` if elicitation was cancelled or not supported.
 */
export async function elicitSessionChoice(
  ctx: McpContext,
  wfDef: WorkflowDefinition,
  activeRuns: WorkflowRunState[],
  locale?: Locale,
): Promise<[WorkflowRunState | null, string | null]> {
  const loc = locale ?? getLocale();

  const options = buildRunOptions(wfDef, activeRuns, loc);

  const schema: Record<string, unknown> = {
    type: "object",
    properties: {
      value: {
        type: "string",
        title: loc.sessionChoiceMessage.replace("{wf_name}", wfDef.name),
        enum: Object.keys(options),
        "x-enum-descriptions": Object.fromEntries(
          Object.entries(options).map(([k, v]) => [k, v.title]),
        ),
      },
    },
    required: ["value"],
  };

  let result;
  try {
    result = await ctx.elicit(
      loc.sessionChoiceMessage.replace("{wf_name}", wfDef.name),
      schema,
    );
  } catch {
    ctx.log.debug("elicitation.not_supported", {
      workflow_id: wfDef.id,
    });
    return [null, null];
  }

  if (result.action !== "accept" || !result.content) {
    return [null, null];
  }

  const chosen = result.content["value"] as string | undefined;
  if (chosen === "__new__") {
    return [null, "__new__"];
  }

  const chosenRun = activeRuns.find((r) => r.id === chosen) ?? null;
  return [chosenRun, null];
}

// ---------------------------------------------------------------------------
// elicitPromptSession
// ---------------------------------------------------------------------------

/**
 * Elicit session choice in prompt handler.
 *
 * Returns `[existingRun, {}]` if resuming, or `[null, params]` for new.
 */
export async function elicitPromptSession(
  ctx: McpContext,
  wfDef: WorkflowDefinition,
  activeRuns: WorkflowRunState[],
  locale?: Locale,
): Promise<[WorkflowRunState | null, Record<string, unknown>]> {
  if (activeRuns.length > 0) {
    const [chosenRun, choice] = await elicitSessionChoice(
      ctx,
      wfDef,
      activeRuns,
      locale,
    );
    if (chosenRun) {
      return [chosenRun, {}];
    }
    if (choice !== "__new__") {
      return [null, {}];
    }
  }

  const requiredParams = wfDef.params.filter((p) => p.required);
  const newParams = await elicitRequiredParams(ctx, requiredParams, locale);
  return [null, newParams ?? {}];
}

// ---------------------------------------------------------------------------
// elicitMissingParams
// ---------------------------------------------------------------------------

/**
 * Elicit missing required/identity params via resume-or-new flow.
 *
 * Returns a dict of param values, or `null` if cancelled.
 */
export async function elicitMissingParams(
  ctx: McpContext,
  wfDef: WorkflowDefinition,
  missingParams: ParamDefinition[],
  activeRuns: WorkflowRunState[],
  existingParams: Record<string, unknown>,
  locale?: Locale,
): Promise<Record<string, unknown> | null> {
  if (activeRuns.length > 0) {
    const [chosenRun, choice] = await elicitSessionChoice(
      ctx,
      wfDef,
      activeRuns,
      locale,
    );
    if (chosenRun) {
      const runParams = chosenRun.params;
      const result: Record<string, unknown> = {};
      for (const pDef of missingParams) {
        if (pDef.name in runParams) {
          result[pDef.name] = runParams[pDef.name];
        }
      }
      return result;
    }
    if (choice === null) {
      return null;
    }
  }

  const stillMissing = missingParams.filter(
    (p) => !(p.name in existingParams),
  );
  return elicitRequiredParams(ctx, stillMissing, locale);
}
