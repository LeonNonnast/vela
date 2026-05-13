/**
 * Registry tests — register / resolve / duplicate-throws / clear.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { registerDelegate, resolveDelegate, clearDelegates } from "./registry.js";
import type { DelegateHandler } from "./types.js";

const noopHandler: DelegateHandler = async () => null;

describe("delegate registry", () => {
  beforeEach(() => {
    clearDelegates();
  });

  it("registers and resolves a handler", () => {
    registerDelegate("echo", noopHandler);
    const resolved = resolveDelegate("echo");
    expect(resolved).toBe(noopHandler);
  });

  it("returns undefined for unregistered names", () => {
    expect(resolveDelegate("missing")).toBeUndefined();
  });

  it("throws when registering the same name twice", () => {
    registerDelegate("echo", noopHandler);
    expect(() => registerDelegate("echo", noopHandler)).toThrow(
      /already registered/,
    );
  });

  it("clearDelegates wipes the registry", () => {
    registerDelegate("echo", noopHandler);
    clearDelegates();
    expect(resolveDelegate("echo")).toBeUndefined();
  });

  it("supports multiple distinct delegates side-by-side", () => {
    const a: DelegateHandler = async () => "a";
    const b: DelegateHandler = async () => "b";
    registerDelegate("a", a);
    registerDelegate("b", b);
    expect(resolveDelegate("a")).toBe(a);
    expect(resolveDelegate("b")).toBe(b);
  });
});
