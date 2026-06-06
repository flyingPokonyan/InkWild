import assert from "node:assert/strict";

import {
  LOW_BALANCE_THRESHOLD,
  buildCreditTransactionsPath,
  creditLevel,
  creditTxnsKey,
  creditTxnsSummaryKey,
} from "./credits.ts";

test("creditLevel: undefined (loading) is normal, not a warning flash", () => {
  assert.equal(creditLevel(undefined), "normal");
});

test("creditLevel: comfortable balance is normal", () => {
  assert.equal(creditLevel(LOW_BALANCE_THRESHOLD + 1), "normal");
  assert.equal(creditLevel(1000), "normal");
});

test("creditLevel: at-or-below threshold (but positive) is low", () => {
  assert.equal(creditLevel(LOW_BALANCE_THRESHOLD), "low");
  assert.equal(creditLevel(1), "low");
});

test("creditLevel: zero or negative is empty", () => {
  assert.equal(creditLevel(0), "empty");
  assert.equal(creditLevel(-5), "empty");
});

test("creditTxnsKey: separates filtered ledger caches", () => {
  assert.deepEqual(creditTxnsKey("all", undefined, "play"), [
    "credits",
    "transactions",
    "list",
    "all",
    null,
    "play",
  ]);
});

test("creditTxnsSummaryKey: does not collide with infinite ledger cache", () => {
  assert.deepEqual(creditTxnsSummaryKey("session", "s1"), [
    "credits",
    "transactions",
    "summary",
    "session",
    "s1",
  ]);
});

test("buildCreditTransactionsPath: includes grouped category filters", () => {
  assert.equal(
    buildCreditTransactionsPath({ category: "creation,image" }),
    "/api/credits/transactions?category=creation%2Cimage",
  );
  assert.equal(
    buildCreditTransactionsPath({
      before: "2026-05-31T10:00:00",
      session: "s1",
      category: "grant,adjust",
    }),
    "/api/credits/transactions?before=2026-05-31T10%3A00%3A00&session=s1&category=grant%2Cadjust",
  );
});
