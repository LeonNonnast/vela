/**
 * Dialog step handling for multi-phase conversations.
 *
 * Manages multi-phase dialog conversations, tracking phase state
 * and assembling phase-specific prompts.
 */

import { DialogModeRegistry } from "./dialog-modes.js";
import { PromptBuilder, type ResourceResolver } from "./prompt-builder.js";
import type { AdvanceResult, WorkflowRunState, WorkflowRunStatus } from "./types.js";
import type {
  AnyStepDefinition,
  CaptureDefinition,
  DialogPhaseDefinition,
  WorkflowDefinition,
} from "../schemas/workflow.js";
import type { WorkflowStore } from "../storage/store.js";

// ---------------------------------------------------------------------------
// Callback types used by DialogHandler
// ---------------------------------------------------------------------------

export type ResolveNextFn = (
  step: AnyStepDefinition,
  output: string | null | undefined,
  workflowDef: WorkflowDefinition,
) => string | null;

export type GetStepFn = (
  workflowDef: WorkflowDefinition,
  stepId: string | null | undefined,
) => AnyStepDefinition | undefined;

export type ParseStepOutputFn = (
  stepOutput: string | null | undefined,
  captures: CaptureDefinition[],
) => Record<string, unknown>;

// ---------------------------------------------------------------------------
// DialogHandler
// ---------------------------------------------------------------------------

export class DialogHandler {
  constructor(
    private readonly store: WorkflowStore,
    private readonly promptBuilder: PromptBuilder,
  ) {}

  /** Return dialog phases: explicit phases override mode lookup. */
  static getDialogPhases(step: AnyStepDefinition): DialogPhaseDefinition[] {
    if (step.type === "dialog" && step.phases.length > 0) {
      return step.phases;
    }
    if (step.type === "dialog" && step.mode) {
      const phases = DialogModeRegistry.get(step.mode);
      if (phases !== undefined) {
        return phases;
      }
    }
    return [];
  }

  /** Handle dialog step advancement through phases. */
  async advanceDialog(
    run: WorkflowRunState,
    workflowDef: WorkflowDefinition,
    step: AnyStepDefinition,
    stepOutput: string | null | undefined,
    notes: string | null | undefined,
    resolveNextFn: ResolveNextFn,
    getStepFn: GetStepFn,
    parseStepOutputFn: ParseStepOutputFn,
    resourceResolver?: ResourceResolver,
  ): Promise<AdvanceResult> {
    const state = run.stateData;
    const phases = DialogHandler.getDialogPhases(step);

    const currentPhaseId = state["_dialog_phase"] as string | undefined;
    const phasesOutput: Record<string, string> = (state["_dialog_phases_output"] as Record<string, string>) ?? {};

    if (phases.length === 0) {
      // Freeform mode or no phases: behave like single-phase
      const stateUpdates: Record<string, unknown> = {};
      if (stepOutput) {
        stateUpdates["_dialog_result"] = stepOutput;
        if (step.capture.length > 0) {
          const outputCaptures = step.capture.filter((c) => c.source === "output");
          Object.assign(stateUpdates, parseStepOutputFn(stepOutput, outputCaptures));
        }
      }

      if (notes) {
        stateUpdates["_notes"] = notes;
      }

      // Clean up dialog state
      delete stateUpdates["_dialog_phase"];
      delete stateUpdates["_dialog_phases_output"];

      const nextStepId = resolveNextFn(step, stepOutput, workflowDef);
      if (nextStepId) {
        run = await this.store.updateStep(run.id, nextStepId, { stateData: stateUpdates });
        const nextStep = getStepFn(workflowDef, nextStepId);
        if (nextStep) {
          const prompt = this.promptBuilder.assemblePrompt(workflowDef, run, nextStep, resourceResolver);
          return { run, prompt, completed: false };
        }
      }

      run = await this.store.updateStep(run.id, run.currentStep ?? null, {
        stateData: stateUpdates,
        status: "completed" as WorkflowRunStatus,
      });
      return { run, completed: true };
    }

    if (currentPhaseId === undefined) {
      // First call: initialize to first phase
      const firstPhase = phases[0];
      state["_dialog_phase"] = firstPhase.id;
      state["_dialog_phases_output"] = {};
      run = await this.store.updateStep(run.id, run.currentStep ?? null, { stateData: state });
      const prompt = this.assembleDialogPrompt(
        workflowDef,
        run,
        step,
        firstPhase,
        phases,
        {},
        resourceResolver,
      );
      return { run, prompt, completed: false };
    }

    // Store current phase output
    if (stepOutput) {
      phasesOutput[currentPhaseId] = stepOutput;
    }

    // Find current phase index
    const phaseIds = phases.map((p) => p.id);
    let currentIdx = phaseIds.indexOf(currentPhaseId);
    if (currentIdx === -1) {
      currentIdx = phaseIds.length - 1;
    }

    if (currentIdx + 1 < phases.length) {
      // More phases remain -- advance to next phase
      const nextPhase = phases[currentIdx + 1];
      state["_dialog_phase"] = nextPhase.id;
      state["_dialog_phases_output"] = phasesOutput;
      run = await this.store.updateStep(run.id, run.currentStep ?? null, { stateData: state });
      const prompt = this.assembleDialogPrompt(
        workflowDef,
        run,
        step,
        nextPhase,
        phases,
        phasesOutput,
        resourceResolver,
      );
      return { run, prompt, completed: false };
    }

    // All phases complete -- merge outputs, process captures, move to next step
    const mergedOutput = phases
      .map((p) => `### ${p.name ?? p.id}\n${phasesOutput[p.id] ?? ""}`)
      .join("\n\n");

    const stateUpdates: Record<string, unknown> = {};
    if (step.capture.length > 0) {
      const outputCaptures = step.capture.filter((c) => c.source === "output");
      if (outputCaptures.length > 0) {
        Object.assign(stateUpdates, parseStepOutputFn(mergedOutput, outputCaptures));
      }
    }

    stateUpdates["_dialog_result"] = mergedOutput;
    if (notes) {
      stateUpdates["_notes"] = notes;
    }

    // Clean up dialog tracking keys
    delete state["_dialog_phase"];
    delete state["_dialog_phases_output"];
    delete stateUpdates["_dialog_phase"];
    delete stateUpdates["_dialog_phases_output"];

    const nextStepId = resolveNextFn(step, stepOutput, workflowDef);
    if (nextStepId) {
      run = await this.store.updateStep(run.id, nextStepId, { stateData: stateUpdates });
      const nextStep = getStepFn(workflowDef, nextStepId);
      if (nextStep) {
        const prompt = this.promptBuilder.assemblePrompt(workflowDef, run, nextStep, resourceResolver);
        return { run, prompt, completed: false };
      }
    }

    run = await this.store.updateStep(run.id, run.currentStep ?? null, {
      stateData: stateUpdates,
      status: "completed" as WorkflowRunStatus,
    });
    return { run, completed: true };
  }

  /** Assemble prompt for a dialog phase. */
  private assembleDialogPrompt(
    workflowDef: WorkflowDefinition,
    run: WorkflowRunState,
    step: AnyStepDefinition,
    phase: DialogPhaseDefinition,
    allPhases: DialogPhaseDefinition[],
    phasesOutput: Record<string, string>,
    resourceResolver?: ResourceResolver,
  ): string {
    const phaseIdx = allPhases.findIndex((p) => p.id === phase.id);
    const total = allPhases.length;

    const parts: string[] = [];

    const stepName = step.name ?? step.id;
    const phaseName = phase.name ?? phase.id;
    parts.push(`## ${workflowDef.name} — ${stepName}`);
    parts.push(`### Phase: ${phaseName} (${phaseIdx + 1}/${total})`);
    parts.push("");

    if (step.type === "dialog" && step.goal) {
      parts.push(`**Ziel:** ${step.goal}`);
      parts.push("");
    }

    if (step.type === "dialog" && step.guidelines.length > 0) {
      parts.push("**Guidelines:**");
      for (const gl of step.guidelines) {
        parts.push(`- ${gl}`);
      }
      parts.push("");
    }

    parts.push(`**Phase-Anweisung:** ${phase.guideline}`);
    parts.push("");

    // Dialog instructions
    parts.push("### Anweisungen");
    parts.push(
      "- Führe ein **Gespräch** mit dem User gemäß der Phase-Anweisung oben.",
    );
    parts.push(
      "- Stelle Rückfragen, mache Vorschläge, iteriere — bis das Phasenziel erreicht ist.",
    );
    parts.push(
      "- Wenn die Phase abgeschlossen ist, fasse das Ergebnis **stichpunktartig** zusammen.",
    );
    parts.push(
      `- Rufe dann \`workflow_advance(run_id="${run.id}", output="<Zusammenfassung>")\` auf.`,
    );
    parts.push(
      "- Gib die Zusammenfassung als `output` mit — sie wird für spätere Phasen gespeichert.",
    );
    parts.push("");

    // Resources
    if (resourceResolver) {
      const resourceParts = PromptBuilder.assembleResources(
        workflowDef,
        step,
        resourceResolver,
      );
      if (resourceParts.length > 0) {
        parts.push(...resourceParts);
        parts.push("");
      }
    }

    // Step prompt (with template resolution)
    if (step.prompt) {
      const context = PromptBuilder.buildTemplateContext(workflowDef, run);
      const prompt = PromptBuilder.resolveTemplates(step.prompt, context);
      parts.push(prompt);
      parts.push("");
    }

    // Previous phase results
    if (Object.keys(phasesOutput).length > 0) {
      parts.push("### Bisherige Ergebnisse");
      for (const p of allPhases) {
        if (p.id in phasesOutput) {
          const pName = p.name ?? p.id;
          parts.push(`- **${pName}:** ${phasesOutput[p.id]}`);
        }
      }
      parts.push("");
    }

    return parts.join("\n");
  }
}
