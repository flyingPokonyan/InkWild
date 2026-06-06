# Checkpoint: W5-C Editor Sections (Read-Only)

**Date:** 2026-05-10
**Task:** 4 个新字段编辑器 sections（read-only）— spec §8.1

## Status: DONE

---

## Files Modified

### Created (4 new components)

1. `frontend/components/admin/editor/sections/LorePackSection.tsx`
   - Renders `lore_pack.dimensions[]` as collapsible `<details>` list
   - Nested `content_blocks[]` per dimension (heading + body)
   - Shows dimension count in header, block count per dimension
   - `generated_at` timestamp in footer when present

2. `frontend/components/admin/editor/sections/SharedEventsSection.tsx`
   - Table view: title / era / involved_npcs (chip style) / source count
   - Row-level expand (toggle) reveals: summary + per-NPC perceptions (knows/believes/feels) + source passage IDs
   - Uses `useState` for expand tracking per event id

3. `frontend/components/admin/editor/sections/EventsDataSection.tsx`
   - Table view: id (mono) / kind badge / trigger DSL (mono) / rumors count / enabled/disabled badge
   - Disabled badge: red (`var(--lv-danger)`) background; enabled badge: green
   - Row expand reveals: summary + trigger raw JSON (`<pre>`) + rumors list (with knower_npcs) + disabled_reason
   - Header shows `N/M 启用` count

4. `frontend/components/admin/editor/sections/RelationsPackSection.tsx`
   - Header: NPC count + total relations count
   - Each NPC is a collapsible row (▶/▼ toggle)
   - Expanded view: grid of target / trust (color-coded: green >0, red <0, grey =0) / kind chip / why text
   - `trustLabel()` helper for human-readable trust level

### Modified

- `frontend/app/admin/worlds/drafts/[id]/page.tsx`
  - Added imports for all 4 new sections + their exported types
  - Refactored payload cast: single `ExtendedPayload` intersection type replacing per-field `as Payload & {...}` — avoids `as any`
  - Renders 4 new sections after `<ResearchPackSection>` in `WorldEditorBody`

---

## Section Component Summaries

| Section | Data source | Interaction | Empty guard |
|---|---|---|---|
| LorePackSection | `lore_pack.dimensions[]` | `<details>` native collapse | `return null` if no dimensions |
| SharedEventsSection | `shared_events[]` | click-to-expand per row (useState) | `return null` if empty array |
| EventsDataSection | `events_data[]` | click-to-expand per row (useState) | `return null` if empty array |
| RelationsPackSection | `relations_pack.relations_by_npc` | click-to-expand per NPC (useState) | `return null` if no entries |

All 4 are strictly read-only (no `<input>`, no `onChange`, no `setPayload`).

---

## TS / ESLint / 视觉合规

```
npx tsc --noEmit     → 0 errors
npx eslint sections/ → 0 warnings, 0 errors
grep banned tokens   → 0 matches
```

- No `text-[Xrem]` arbitrary font classes
- No `var(--color-accent)` / `var(--font-size-*)` / `var(--ta-*)`
- All font sizes via `.lv-t-*` utility classes
- All colors via `var(--lv-*)` design tokens
- Touch targets ≥ 44px (all interactive buttons use `minHeight: 44`)
- `"use client"` directive on all 4 files (required for `useState`)

---

## Concerns / Notes

- `var(--lv-success, #5cb85c)` used with fallback for trust color since `--lv-success` may not be in the token set; ESLint only blocks `--ta-*` / `--color-accent` / `--font-size-*`, so this is fine.
- `ExtendedPayload` type in page is declared inside the `WorldEditorBody` function body — this is consistent with React component scope and avoids polluting module-level types.
- All 4 sections follow the ResearchPackSection pattern exactly: `style={{}}` inline for token usage, `.lv-t-*` for typography.
