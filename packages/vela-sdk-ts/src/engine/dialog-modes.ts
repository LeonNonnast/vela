/**
 * Registry for dialog mode phase definitions.
 *
 * Built-in modes are embedded as TypeScript objects (ported from dialog_modes.yaml).
 * Custom modes can be registered at runtime.
 */

import type { DialogPhaseDefinition } from "../schemas/workflow.js";

// ---------------------------------------------------------------------------
// Built-in modes (from dialog_modes.yaml)
// ---------------------------------------------------------------------------

const BUILTIN_MODES: Record<string, DialogPhaseDefinition[]> = {
  brainstorming: [
    {
      id: "diverge",
      name: "Divergieren",
      guideline:
        "Sammle möglichst viele Ideen ohne Bewertung. Quantität vor Qualität.",
    },
    {
      id: "converge",
      name: "Konvergieren",
      guideline:
        "Bewerte und filtere die Ideen. Welche sind realistisch und wertvoll?",
    },
    {
      id: "synthesize",
      name: "Synthese",
      guideline:
        "Fasse die besten Ideen zu einem kohärenten Ergebnis zusammen.",
    },
  ],

  requirements: [
    {
      id: "context",
      name: "Kontext",
      guideline:
        "Kläre den Hintergrund: Wer sind die Stakeholder? Was ist der Auslöser?",
    },
    {
      id: "questions",
      name: "Fragen",
      guideline:
        "Stelle gezielte Fragen um Anforderungen zu identifizieren und Lücken aufzudecken.",
    },
    {
      id: "prioritize",
      name: "Priorisieren",
      guideline:
        "Ordne die Anforderungen nach Wichtigkeit und Dringlichkeit.",
    },
    {
      id: "specify",
      name: "Spezifizieren",
      guideline:
        "Formuliere die priorisierten Anforderungen als klare, testbare Aussagen.",
    },
  ],

  planning: [
    {
      id: "goals",
      name: "Ziele",
      guideline: "Definiere klare, messbare Ziele für den Plan.",
    },
    {
      id: "breakdown",
      name: "Aufteilen",
      guideline:
        "Zerlege die Ziele in konkrete, umsetzbare Aufgaben.",
    },
    {
      id: "dependencies",
      name: "Abhängigkeiten",
      guideline:
        "Identifiziere Abhängigkeiten zwischen Aufgaben und definiere die Reihenfolge.",
    },
    {
      id: "approval",
      name: "Freigabe",
      guideline:
        "Überprüfe den Plan und bestätige oder korrigiere ihn.",
    },
  ],

  review: [
    {
      id: "understand",
      name: "Verstehen",
      guideline:
        "Stelle sicher, dass der Gegenstand der Review vollständig verstanden ist.",
    },
    {
      id: "evaluate",
      name: "Bewerten",
      guideline:
        "Bewerte systematisch nach den relevanten Kriterien.",
    },
    {
      id: "decide",
      name: "Entscheiden",
      guideline: "Triff eine klare Entscheidung mit Begründung.",
    },
  ],

  freeform: [],
};

// ---------------------------------------------------------------------------
// DialogModeRegistry
// ---------------------------------------------------------------------------

export class DialogModeRegistry {
  private static modes: Record<string, DialogPhaseDefinition[]> = {
    ...BUILTIN_MODES,
  };

  /** Return phases for a mode, or undefined if not registered. */
  static get(modeId: string): DialogPhaseDefinition[] | undefined {
    return this.modes[modeId];
  }

  /** Register or override a dialog mode. */
  static register(modeId: string, phases: DialogPhaseDefinition[]): void {
    this.modes[modeId] = phases;
  }

  /** Return all registered modes. */
  static allModes(): Record<string, DialogPhaseDefinition[]> {
    return { ...this.modes };
  }

  /** Reset to built-in modes only (for testing). */
  static _reset(): void {
    this.modes = { ...BUILTIN_MODES };
  }
}
