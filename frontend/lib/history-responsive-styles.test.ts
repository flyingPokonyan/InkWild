import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(process.cwd(), "app/globals.css"), "utf8");

describe("history responsive layout styles", () => {
  it("keeps desktop and mobile history views mutually exclusive in global css", () => {
    expect(css).toMatch(/@media\s*\(max-width:\s*768px\)[\s\S]*\.lv-history-desktop\s*\{\s*display:\s*none\s*!important;\s*\}/);
    expect(css).toMatch(/@media\s*\(min-width:\s*769px\)[\s\S]*\.lv-history-mobile\s*\{\s*display:\s*none\s*!important;\s*\}/);
  });
});
