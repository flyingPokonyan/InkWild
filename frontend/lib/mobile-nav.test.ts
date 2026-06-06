import assert from "node:assert/strict";

import { MOBILE_BOTTOM_TABS, getActiveMobileTab } from "./mobile-nav.ts";

test("mobile bottom navigation uses home, discover, create, me", () => {
  assert.deepEqual(
    MOBILE_BOTTOM_TABS.map((tab) => tab.key),
    ["home", "discover", "create", "me"],
  );
  assert.equal(MOBILE_BOTTOM_TABS.some((tab) => tab.key === "history"), false);
});

test("me tab is active for profile and credits pages", () => {
  assert.equal(getActiveMobileTab("/me"), "me");
  assert.equal(getActiveMobileTab("/me/credits"), "me");
});

test("discover tab owns world detail routes", () => {
  assert.equal(getActiveMobileTab("/worlds/demo"), "discover");
});
