/**
 * Delegate step-schema helper.
 *
 * The actual step zod schema lives in `../schemas/workflow.ts` (so it can
 * participate in the discriminated union with the other step types). This
 * file re-exports the schema + inferred type and provides a small typed
 * helper for callers that build delegate steps programmatically.
 */

export {
  delegateStepSchema,
  type DelegateStepDefinition,
} from "../schemas/workflow.js";

import type { DelegateStepDefinition } from "../schemas/workflow.js";

/**
 * Convenience builder for a delegate step definition. Useful for
 * `registerDynamicWorkflow(...)` callers that want type-safety without
 * importing zod themselves.
 */
export function makeDelegateStep(
  init: Pick<DelegateStepDefinition, "id" | "delegate"> &
    Partial<Omit<DelegateStepDefinition, "type" | "id" | "delegate">>,
): DelegateStepDefinition {
  return {
    type: "delegate",
    id: init.id,
    delegate: init.delegate,
    task: init.task,
    name: init.name ?? null,
    prompt: init.prompt ?? "",
    depends_on: init.depends_on ?? [],
    fetch: init.fetch ?? [],
    tools: init.tools ?? [],
    capture: init.capture ?? [],
    next: init.next ?? null,
    notes: init.notes ?? true,
    on_error: init.on_error ?? null,
    resources: init.resources ?? [],
  } as DelegateStepDefinition;
}
