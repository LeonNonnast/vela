/**
 * Registry tests — register / resolve / duplicate-throws / clear.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { registerSource, resolveSource, clearSources } from "./registry.js";
import type { SourceHandler } from "./types.js";

const noopHandler: SourceHandler = async () => null;

describe("source registry", () => {
  beforeEach(() => {
    clearSources();
  });

  it("registers and resolves a handler", () => {
    registerSource("devops", noopHandler);
    const resolved = resolveSource("devops");
    expect(resolved).toBe(noopHandler);
  });

  it("returns undefined for unregistered names", () => {
    expect(resolveSource("missing")).toBeUndefined();
  });

  it("throws when registering the same name twice", () => {
    registerSource("devops", noopHandler);
    expect(() => registerSource("devops", noopHandler)).toThrow(
      /already registered/,
    );
  });

  it("clearSources wipes the registry", () => {
    registerSource("devops", noopHandler);
    clearSources();
    expect(resolveSource("devops")).toBeUndefined();
  });

  it("supports multiple distinct sources side-by-side", () => {
    const a: SourceHandler = async () => "a";
    const b: SourceHandler = async () => "b";
    registerSource("a", a);
    registerSource("b", b);
    expect(resolveSource("a")).toBe(a);
    expect(resolveSource("b")).toBe(b);
  });
});
