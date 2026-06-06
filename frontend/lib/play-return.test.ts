import { describe, expect, it } from "vitest";

import { resolveExitHref, sanitizeReturn, withReturn } from "./play-return";

describe("sanitizeReturn", () => {
  it("accepts whitelisted internal paths", () => {
    expect(sanitizeReturn("/workshop")).toBe("/workshop");
    expect(sanitizeReturn("/workshop?tab=scripts")).toBe("/workshop?tab=scripts");
    expect(sanitizeReturn("/discover")).toBe("/discover");
    expect(sanitizeReturn("/worlds/abc")).toBe("/worlds/abc");
  });

  it("decodes encoded values", () => {
    expect(sanitizeReturn(encodeURIComponent("/workshop?tab=scripts"))).toBe("/workshop?tab=scripts");
  });

  it("rejects open-redirect / off-whitelist targets", () => {
    expect(sanitizeReturn("https://evil.com")).toBeNull();
    expect(sanitizeReturn("//evil.com")).toBeNull();
    expect(sanitizeReturn("/admin/models")).toBeNull();
    expect(sanitizeReturn("workshop")).toBeNull();
    expect(sanitizeReturn(null)).toBeNull();
    expect(sanitizeReturn("")).toBeNull();
  });
});

describe("resolveExitHref", () => {
  it("uses sanitized return when valid, else fallback", () => {
    expect(resolveExitHref("/workshop")).toBe("/workshop");
    expect(resolveExitHref("https://evil.com")).toBe("/");
    expect(resolveExitHref("https://evil.com", "/discover")).toBe("/discover");
    expect(resolveExitHref(null)).toBe("/");
  });
});

describe("withReturn", () => {
  it("appends encoded return with correct separator", () => {
    expect(withReturn("/worlds/abc", "/workshop")).toBe("/worlds/abc?return=%2Fworkshop");
    expect(withReturn("/worlds/abc?x=1", "/workshop")).toBe("/worlds/abc?x=1&return=%2Fworkshop");
  });

  it("passes href through untouched when return is invalid", () => {
    expect(withReturn("/worlds/abc", null)).toBe("/worlds/abc");
    expect(withReturn("/worlds/abc", "https://evil.com")).toBe("/worlds/abc");
  });
});
