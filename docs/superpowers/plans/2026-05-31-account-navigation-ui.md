# Account Navigation UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the credits drawer/account entry model with page-based credits, a lightweight PC avatar menu, and a mobile "Me" hub with a single-row history module.

**Architecture:** Keep `/workshop` content untouched. Add small pure helper modules for account menu and mobile navigation definitions so key IA changes are testable. Update `ProductNav`, `BottomTabBar`, `/me`, and `/me/credits` using existing v2.3 cinematic gold tokens and components.

**Tech Stack:** Next.js 16, React 19, TypeScript, Zustand, TanStack Query, Tailwind/CSS tokens, vitest.

---

### Task 1: Testable Navigation Definitions

**Files:**
- Create: `frontend/lib/account-menu.ts`
- Create: `frontend/lib/account-menu.test.ts`
- Create: `frontend/lib/mobile-nav.ts`
- Create: `frontend/lib/mobile-nav.test.ts`

- [ ] Write failing tests proving PC account menu excludes history/workshop and mobile tabs are home/discover/create/me.
- [ ] Run targeted vitest tests and confirm they fail because modules do not exist.
- [ ] Implement minimal helper modules.
- [ ] Re-run targeted tests and confirm they pass.

### Task 2: PC ProductNav

**Files:**
- Modify: `frontend/components/ProductNav.tsx`

- [ ] Replace credits drawer state/action with page links.
- [ ] Remove `Explorer` text and history/workshop rows from avatar menu.
- [ ] Make the account dropdown lightweight: identity row, "我的积分" with normal-sized balance, settings placeholder, logout.
- [ ] Ensure "我的积分" links to `/me/credits`; identity/personal info links to `/me`.

### Task 3: Mobile Bottom Nav

**Files:**
- Modify: `frontend/components/BottomTabBar.tsx`
- Modify: `frontend/i18n/zh.json`
- Modify: `frontend/i18n/en.json`

- [ ] Change mobile bottom tabs to 首页 / 发现 / 创作 / 我.
- [ ] Route unauthenticated 创作 and 我 taps through login modal.
- [ ] Mark `/me` and `/me/credits` active under 我.

### Task 4: Mobile Me Page

**Files:**
- Modify: `frontend/app/me/page.tsx`

- [ ] Remove `Explorer` label.
- [ ] Remove mobile avatar-right credit chip pattern.
- [ ] Redesign `/me` as a platform-style account hub: profile, normal-sized credits card, one-row history module, assets grid.
- [ ] History module shows up to three recent sessions plus an "全部历史" tile/link.
- [ ] Keep desktop `/me` visually consistent with the same hierarchy.

### Task 5: Credits Page

**Files:**
- Modify: `frontend/app/me/credits/page.tsx`
- Modify: `frontend/components/CreditWalletView.tsx`

- [ ] Keep credits as a full page, not drawer.
- [ ] Normalize number typography so digits use one consistent scale within each surface.
- [ ] Remove exaggerated mixed-size number treatment.
- [ ] Preserve transaction list and stats behavior.

### Task 6: Verification

**Commands:**
- `cd frontend && npm run test -- lib/account-menu.test.ts lib/mobile-nav.test.ts`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`

- [ ] Verify desktop `/me` and `/me/credits` in browser.
- [ ] Verify mobile-width `/me`, `/me/credits`, and bottom nav in browser.
