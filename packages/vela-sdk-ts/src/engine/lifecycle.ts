/**
 * Lifecycle checking for workflow runs.
 *
 * Checks auto_cancel_after rules and determines if a run's status should change.
 */

import { WorkflowRunStatus } from "./types.js";
import type { WorkflowRunState } from "./types.js";
import type { LifecycleDefinition } from "../schemas/workflow.js";

// ---------------------------------------------------------------------------
// Duration parsing
// ---------------------------------------------------------------------------

/**
 * Parse a duration string like "48h", "30d", "90d" into hours.
 *
 * Returns the number of hours, or null if the format is unrecognized.
 */
export function parseDuration(durationStr: string): number | null {
  const match = durationStr.trim().match(/^(\d+(?:\.\d+)?)\s*(h|d)$/);
  if (!match) {
    return null;
  }
  const value = parseFloat(match[1]);
  const unit = match[2];
  if (unit === "d") {
    return value * 24;
  }
  return value;
}

// ---------------------------------------------------------------------------
// LifecycleChecker
// ---------------------------------------------------------------------------

export class LifecycleChecker {
  /**
   * Check if lifecycle rules require a status change.
   *
   * Returns the new status, or null if no change is needed.
   */
  static checkLifecycle(
    run: WorkflowRunState,
    lifecycle?: LifecycleDefinition | null,
  ): WorkflowRunStatus | null {
    if (!lifecycle) {
      return null;
    }

    const now = new Date();
    const updated = run.updatedAt ? new Date(run.updatedAt) : null;

    if (!updated) {
      return null;
    }

    const hoursSinceUpdate =
      (now.getTime() - updated.getTime()) / (1000 * 60 * 60);

    if (lifecycle.auto_cancel_after) {
      const cancelHours = parseDuration(lifecycle.auto_cancel_after);
      if (
        cancelHours !== null &&
        hoursSinceUpdate > cancelHours &&
        run.status === WorkflowRunStatus.ACTIVE
      ) {
        return WorkflowRunStatus.CANCELLED;
      }
    }

    return null;
  }
}
