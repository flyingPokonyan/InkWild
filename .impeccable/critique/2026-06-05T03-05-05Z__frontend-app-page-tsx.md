---
target: frontend/app/page.tsx
total_score: 33
p0_count: 0
p1_count: 3
timestamp: 2026-06-05T03-05-05Z
slug: frontend-app-page-tsx
---
# Critique — frontend/app/page.tsx (InkWild landing)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Hover/scroll-cue/live-demo status present; landing has little async to report |
| 2 | Match System / Real World | 4 | Plain, vivid Chinese; "世界/剧本/自由" metaphors land. "产品" is a touch flat |
| 3 | User Control and Freedom | 4 | Nav, lang chip, anchored scroll, no traps |
| 4 | Consistency and Standards | 3 | Token system consistent; card body drops to meta size, eyebrow pattern repeats |
| 5 | Error Prevention | 3 | n/a — no forms on the landing |
| 6 | Recognition Rather Than Recall | 4 | Labeled CTAs + nav, no icon-only nav |
| 7 | Flexibility and Efficiency | 3 | Direct CTAs + scroll anchor; nothing to accelerate |
| 8 | Aesthetic and Minimalist Design | 3 | Clean and restrained, but generic stock hero + eyebrow-on-every-section dilute it |
| 9 | Error Recovery | 3 | n/a — no error surfaces |
| 10 | Help and Documentation | 3 | The 3-step "how it works" doubles as inline explanation |
| **Total** | | **33/40** | **Good** |

Caveat: Nielsen scores usability, and the page is genuinely usable. It under-weights **brand distinctiveness**, which is where the real work is — see the anti-patterns verdict and P1s.

## Anti-Patterns Verdict

**Does this look AI-generated?** Partly. It dodges the worst SaaS tells (no fake metrics, restrained gold, a real product demo), but it sits in a recognizable saturated lane: **cinematic-dark + serif headline over a stock nature photo + mono-caps eyebrows + feature cards.** A savvy visitor wouldn't say "which AI made this" outright, but the generic hero and the eyebrow-on-every-section push it toward "templated."

**LLM assessment:**
- **Editorial-typographic fingerprint** (brand.md's saturated lane #1): display serif (Cormorant/Source Han Serif) + small JetBrains-Mono uppercase labels + monochromatic restraint. The hero kicker + 「两种模式」+「游玩方式」+ two card eyebrows = uppercase tracked eyebrows on essentially every block. That cadence is AI grammar.
- **Generic stock hero** is the single biggest tell: a product whose whole pitch is "real cinematic worlds with their own cover art" leads with an Unsplash forest. It says nothing about interactive stories.
- **Identical mode cards**: icon-chip + eyebrow + title + bullet list + CTA, mirrored 1:1. Two is milder than endless, but it's the generic feature-card move.

**Deterministic scan** (`detect.mjs`, 3 warnings):
- `overused-font` ×2 (Inter, lines 303/329) — true, but Inter is the project's committed body face (identity-preservation applies; not a swap-on-sight).
- `bounce-easing` ×1 (`lv-live-bounce`, line 791) — true; the thinking-dots bounce. Minor, real, easy fix.

**Visual overlays:** Not available this run — no browser injection was performed (no browser-automation tool wired; app runs in Docker). Findings are source + detector based. A live `/impeccable audit` or `live` pass would add rendered-contrast evidence.

## Overall Impression

A clean, confident, on-brand-restrained landing that **tells** well but **shows** too little. The LivePlayDemo is the star — it's the one place the product becomes legible and distinctive. The biggest opportunity: the page never shows a single real world from the catalog, and the hero is a stock photo instead of the product's own (genuinely strong) cover art. Fix the hero and add real worlds and the page jumps from "competent dark SaaS-y landing" to "this is clearly InkWild."

## What's Working

1. **LivePlayDemo** (the 3-turn typed input → milestones → streaming narration loop). It dramatizes "实时推演" instead of describing it — the most distinctive, most on-brand element on the page. Keep and feature it.
2. **Gold discipline.** Champagne gold appears only on step numbers, demo accents, status, and focus rings — the whitelist is honored. "金色越省越贵" is actually practiced.
3. **No fake metrics.** The PRODUCT.md anti-reference (SaaS hero-metric numbers) is genuinely avoided; the page sells story and atmosphere, not a feature count.

## Priority Issues

- **[P1] Hero leads with generic stock, not the product's own worlds.**
  - **Why it matters:** InkWild's strongest asset is its cinematic world art (甄嬛传/紫禁深宫, 大唐狄公案, 东方快车, 莲花楼). Leading with an Unsplash forest under-sells the product and reads as a template; it violates PRODUCT.md principle #3 (给真东西) and the brand register's imagery guidance.
  - **Fix:** Replace the hero background with the product's real art — one stunning real cover, or a slow cross-fade / collage montage of 3–4 actual world covers. Let the photograph(s) be the design.
  - **Suggested command:** `/impeccable shape` (re-plan the hero), then build.

- **[P1] No real worlds shown anywhere on the page.**
  - **Why it matters:** The landing explains modes and steps but never shows the catalog — the best conversion lever and the clearest answer to "what will I actually play?" Goal in PRODUCT.md is "陌生人落地首页后愿意开一局"; a worlds spotlight is the most direct path there.
  - **Fix:** Add a "精选世界" section pulling 3–4 real worlds (covers + title + one line) from the live API — `discover` already has this data and a PosterCard. Tease, then link into `/discover`.
  - **Suggested command:** `/impeccable shape` → `/impeccable craft`.

- **[P1] Hero text legibility over a full-brightness photo.**
  - **Why it matters:** You emphasized WCAG AA. Hero lead is `rgba(245,242,235,0.82)` and the kicker `0.74`, over a bright image with only a faint radial scrim (`rgba(5,5,7,0.32)`), relying on `text-shadow`. Over the photo's sunlit areas this likely drops below 4.5:1 — and worse on a phone outdoors.
  - **Fix:** Anchor the text in a contained gradient/vignette (or darken the image only in the text zone) so contrast holds regardless of the photo; don't lean on text-shadow alone. Verify ≥4.5:1 at the brightest pixels behind text.
  - **Suggested command:** `/impeccable audit` (contrast/responsive) then `/impeccable polish`.

- **[P2] Eyebrow-on-every-section (editorial-typographic AI tell).**
  - **Why it matters:** Hero kicker + two section eyebrows + two card eyebrows is the reflexive uppercase-tracked kicker the bans call out; it's what makes the page guessable as AI/templated.
  - **Fix:** Keep at most one named kicker as a deliberate brand device; drop the reflexive caps eyebrow on the other sections and let the serif h2 carry them.
  - **Suggested command:** `/impeccable typeset` or `/impeccable quieter`.

- **[P2] Mode cards: identical pattern + sub-AA bullet contrast + body too small.**
  - **Why it matters:** Card description is `--lv-t-meta` (12px) and bullets are `--lv-ink-3` (#8c8273) on near-black ≈ 4.0:1 — below AA at that size. The mirrored icon+eyebrow+title+bullets+CTA cards are also the generic feature-card move.
  - **Fix:** Bump card body to `--lv-t-body` (15px), move bullets to `--lv-ink-2` for ≥4.5:1, and consider art-directing the two modes as two different visual worlds (剧本 = case-board/cold; 自由 = open/warm) instead of mirror cards.
  - **Suggested command:** `/impeccable layout` + `/impeccable audit` (contrast).

## Persona Red Flags

**Jordan (首次访客):** First fold = a forest photo + "走进未写完的世界" + "AI 互动叙事产品." At 5 seconds it's still ambiguous — game? novel? tool? Nothing real anchors "what will I play." The "aha" only arrives at the third fold (LivePlayDemo). High first-fold drop risk.

**Casey (移动端单手):** Thumb zone is handled well (left-aligned hero text, full-width stacked CTAs, BottomTabBar). But hero copy sits on a full-bright photo with only text-shadow — likely unreadable in outdoor light. Also the primary "开始探索" and the bottom-tab "发现" point to nearly the same place — two adjacent entries to the same destination.

**Riley (压力测试 / i18n):** Switching to English (LangChip) translates the whole page — **except the centerpiece LivePlayDemo, which is hard-coded Chinese** (皮帽客/酒馆). English visitors see a Chinese demo: trust hit. Separately, an entire `landing.demo.*` copy set (王福/外来调查员) exists in `zh.json` but is **never used** — dead copy that drifted from the hard-coded `DEMO_TURNS`.

**创作者 (project persona):** The page has a "创建世界" CTA and a "去创作工坊生成" line, but never shows the workshop or what it produces. A creator can't see "how good will my world look." PRODUCT.md's "两类用户一条动线" currently tilts almost entirely to players.

## Minor Observations

- **i18n centerpiece breaks in English** (see Riley) — borderline P2: wire `DEMO_TURNS` to `landing.demo.*` (and translate), or accept Chinese-only and delete the dead keys.
- **Dead/Drifted copy:** `landing.demo.*` and `landing.footer.copyright` ("© InkWild") are unused; the footer hard-codes `© {year} InkWild Studio`. Pick one source.
- **Bounce easing** (`lv-live-bounce`, line 791) — swap to ease-out-quart for the thinking dots (P3).
- **Comment drift:** `HERO_IMG` comment says "西部荒原" but the Unsplash id is a misty forest. Trivial, but a tell that the hero image isn't a deliberate art choice.
- **Section titles are quiet:** serif h2 capped at `clamp(20px,2vw,26px)` weight 500, then 12px body — the lower folds whisper. For a brand that wants "大气," the content sections could commit to a bolder type step.

## Questions to Consider

- 首屏该不该直接是真实世界的封面（甄嬛传/狄公案/东方快车），而不是一张中立风景照？产品最强的资产为什么不在第一眼？
- Hero 的情绪是不是该由「你扮演谁、在哪个世界」来承载，而不是一张谁都能用的自然照？
- 两个模式卡能不能 art-direct 成两种不同的视觉世界（剧本＝案件板冷峻 / 自由＝开放暖），而不是一对镜像卡？
- 创作者在这一页能看到什么？「两类用户一条动线」现在是不是其实只服务了玩家？
