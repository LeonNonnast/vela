/**
 * Core types for the workflow engine.
 *
 * These are internal runtime types — camelCase conventions apply.
 */

// ---------------------------------------------------------------------------
// WorkflowRunStatus
// ---------------------------------------------------------------------------

export enum WorkflowRunStatus {
  ACTIVE = "active",
  PAUSED = "paused",
  COMPLETED = "completed",
  CANCELLED = "cancelled",
}

// ---------------------------------------------------------------------------
// WorkflowRunState
// ---------------------------------------------------------------------------

/**
 * Framework-agnostic representation of a workflow run.
 *
 * The engine works with this interface instead of ORM objects.
 * Storage implementations convert between their native format and this type.
 */
export interface WorkflowRunState {
  id: string;
  workflowId: string;
  workflowVersion: string;
  currentStep?: string | null;
  status: WorkflowRunStatus;
  params: Record<string, unknown>;
  stateData: Record<string, unknown>;
  projectId?: string | null;
  parentRunId?: string | null;
  parentStepId?: string | null;
  startedAt?: string | null;
  updatedAt?: string | null;
  completedAt?: string | null;
}

// ---------------------------------------------------------------------------
// AdvanceResult
// ---------------------------------------------------------------------------

/** Result of advancing a workflow. */
export interface AdvanceResult {
  run: WorkflowRunState;
  prompt?: string | null;
  completed: boolean;
  subWorkflowRef?: string | null;
  subWorkflowParams?: Record<string, unknown> | null;
  /** When set, the current execute step should be delegated (e.g. "subagent"). */
  delegate?: string | null;
  /** Optional instructions for the delegate (from step.instructions). */
  delegateInstructions?: string | null;
  /** Tool names the delegate should use. */
  delegateTools?: string[] | null;
  /** When true, the next step's depends_on constraints are not yet satisfied. */
  blocked?: boolean;
  /** State fields that are missing (unsatisfied dependencies). */
  blockedBy?: string[];
}

// ---------------------------------------------------------------------------
// ErrorAction
// ---------------------------------------------------------------------------

/** Result of error handling. */
export interface ErrorAction {
  /** retry | fallback | abort */
  action: string;
  fallbackStep?: string | null;
  message?: string | null;
}
