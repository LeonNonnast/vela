/**
 * Delegate feature — generic step handler registry.
 *
 * Consumers register named handlers (`engine`, `shell`, `webhook`, ...) at
 * app start. YAML workflows then reference these via `delegate: <name>` on
 * a `delegate` step. The handler receives the step's `task` payload (after
 * variable resolution) plus a context with capture/log/signal helpers.
 *
 * Mini-spec: see ai-engine-refactoring-plan.md, Anhang F.
 */

/** Context passed to a delegate handler when its step executes. */
export interface DelegateContext {
  /**
   * Resolve `${var}` templates inside arbitrary structures (objects, arrays,
   * strings) against the current workflow run params + stateData. Handlers
   * call this on `step.task` before forwarding to the underlying engine.
   */
  resolveVars: (v: unknown) => unknown;

  /**
   * Write a capture value back into the run state. Most handlers don't need
   * this — the engine automatically applies `step.capture` to the handler's
   * returned result. Use this only for ad-hoc captures that don't fit the
   * declarative `capture:` mapping.
   */
  setCapture: (key: string, value: unknown) => void;

  /** Cancellation signal propagated from the workflow run. */
  signal?: AbortSignal;

  /** Structured log hook (forwarded to the MCP context if available). */
  log: (msg: string, meta?: unknown) => void;
}

/**
 * Delegate-handler signature. Handlers receive the raw step (with the
 * already-decoded `task` payload — the caller is responsible for
 * `ctx.resolveVars` when needed) and must return a JSON-serialisable
 * result. The engine writes that result into the workflow's stateData
 * via the step's `capture:` definitions.
 */
export type DelegateHandler = (
  step: { id: string; delegate: string; task: unknown },
  ctx: DelegateContext,
) => Promise<unknown>;
