import assert from "node:assert/strict";

import { getAccountMenuItems } from "./account-menu.ts";

test("PC account menu stays in account scope and does not repeat top navigation", () => {
  const items = getAccountMenuItems();
  assert.deepEqual(
    items.map((item) => item.key),
    ["profile", "credits", "settings", "logout"],
  );
  assert.equal(items.some((item) => item.href === "/history"), false);
  assert.equal(items.some((item) => item.href === "/workshop"), false);
});

test("credits menu item links to the full credits page", () => {
  const credits = getAccountMenuItems().find((item) => item.key === "credits");
  assert.equal(credits?.href, "/me/credits");
});
