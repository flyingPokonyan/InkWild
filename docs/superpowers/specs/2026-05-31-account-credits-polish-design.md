# Account Credits Polish Design

Date: 2026-05-31

## Goal

Refine the `/me` and `/me/credits` account surfaces without changing the current information architecture. Keep the desktop pattern of a left account rail and right content area, and keep the mobile account hub/page model. The work is visual and interaction polish only.

## Scope

- Desktop `/me`: keep `AccountShell` and `AccountProfile` structure.
- Desktop `/me/credits`: keep account rail, polish the right-side credits content.
- Mobile `/me`: keep profile hub, adjust the credits entry only as needed for consistency.
- Mobile `/me/credits`: use the same balance/ledger hierarchy at mobile scale.
- Do not add payment or recharge functionality. Recharge remains unavailable.

## Visual Direction

- Remove decorative gold from credits surfaces. No gold vertical rule, no gold border, no gold button fill.
- Use the existing v2.3 neutral card language: dark card, subtle white border, restrained shadow.
- Balance number should be prominent but not KPI-like:
  - Desktop balance number: about 31-32px, medium weight, tabular numbers.
  - Mobile balance number: about 28px, medium weight, tabular numbers.
- Move lifetime granted/spent stats into the balance card footer so the card reads as one account asset module instead of a sparse metric tile.
- Keep page order simple: title row, balance asset card, ledger card.

## Recharge Button

Recharge is disabled and must visually read as disabled.

- Use a neutral ghost disabled style, not primary ivory and not gold.
- Apply native `disabled`.
- Use low-contrast gray-white text, subtle neutral border/background, `cursor: not-allowed`, and no hover lift.
- Label remains `充值` with a small `暂未开放` marker.
- Touch target on mobile must be at least 44px high.

## Ledger Display

The transaction ledger should handle both short and long histories.

- Empty state remains simple.
- Loading state remains simple.
- Non-empty state:
  - Group transactions by local date when practical.
  - Each row shows kind, category/context, timestamp, delta, and balance after.
  - Positive deltas use neutral high-contrast text, not decorative gold.
  - Negative deltas use secondary neutral text.
- For many records:
  - Desktop ledger can cap its own scroll area inside the right-side content.
  - Use a "load more" affordance when more pages are available.
  - Mobile can continue vertically with a load-more button rather than an inner tiny scroll area.

## Mobile Requirements

- Keep 375px as the first-class viewport.
- Balance card uses a single column; recharge button spans full width.
- Ledger rows fit in two compact columns without text overlap.
- Preserve bottom safe area for the global mobile tab bar.
- Touch targets are at least 44px where interactive.

## Implementation Notes

- Prefer reusing `CreditsPanel` and `CreditLedger` so desktop and mobile stay consistent.
- Convert `CreditWalletView` ledger inline styles into scoped class styles if the component needs shared polish.
- Keep changes limited to account/credits components and i18n text only if required.
- Follow existing tokens in `frontend/app/globals.css`; do not introduce page-local theme overrides.

## Verification

- Run targeted frontend tests if touched modules have tests.
- Run `npm run lint`.
- Run `npm run build` if feasible.
- Browser-check desktop `/me` and `/me/credits`.
- Browser-check mobile-width `/me` and `/me/credits`.
