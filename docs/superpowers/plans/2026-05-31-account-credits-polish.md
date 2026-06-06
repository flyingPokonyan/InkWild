# Account Credits Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the account credits UI on desktop and mobile while keeping the current navigation structure.

**Architecture:** Keep `AccountShell` as the desktop shell and keep `CreditsPanel` as the shared credits page content. Move the balance stats into one neutral asset card, restyle the disabled recharge button as a ghost disabled control, and update `CreditLedger` to use class-based styling with date grouping and load-more support.

**Tech Stack:** Next.js 16, React 19, TypeScript, TanStack Query, Tailwind/global CSS tokens, next-intl.

---

### Task 1: Shared Credits Asset Card

**Files:**
- Modify: `frontend/components/account/CreditsPanel.tsx`

- [ ] Update the balance card markup so the card contains balance, disabled recharge button, and lifetime stats footer.
- [ ] Remove gold card border/background usage from the credits card.
- [ ] Set desktop balance typography to a smaller medium-weight tabular number.
- [ ] Style `.crp-topup` as a neutral disabled ghost button: low-contrast border/background, gray-white text, `cursor: not-allowed`, no hover.
- [ ] Ensure mobile stacks the card content and makes the disabled button at least 44px high and full width.

### Task 2: Ledger Polish And Pagination

**Files:**
- Modify: `frontend/components/CreditWalletView.tsx`

- [ ] Replace inline ledger row styles with scoped class names and a `<style jsx global>` block.
- [ ] Group ledger rows by local date.
- [ ] Use neutral colors for deltas: positive neutral high contrast, negative secondary neutral.
- [ ] Add a load-more button when `next_cursor` exists, using existing `fetchCreditTransactions({ before })`.
- [ ] Keep mobile ledger as normal page flow; use a capped internal scroll only for the desktop full credits page context if needed by parent layout.

### Task 3: Mobile Account Credits Entry Consistency

**Files:**
- Modify: `frontend/app/me/page.tsx`

- [ ] Remove gold border/background from the mobile credits entry card.
- [ ] Keep the entry compact and link-like because `/me/credits` holds the full ledger.
- [ ] Keep tap target height at least 44px when the card stacks on narrow screens.

### Task 4: Verification

**Commands:**
- `cd frontend && npm run lint`
- `cd frontend && npm run build`

- [ ] Browser-check `/me/credits` at desktop width.
- [ ] Browser-check `/me/credits` at 375px mobile width.
- [ ] Browser-check `/me` mobile credits entry.
- [ ] Confirm recharge is visibly disabled and not styled like primary ivory CTA.
