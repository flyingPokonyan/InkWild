# InkWild · 设计令牌参考 v2.3
*Frontend Spec — token values & class index*

> 这一份**取代** v2.2。设计哲学和规则全部迁到 `visual-principles.md` v2.3，本文档只剩 token 值、CSS 变量名、工具类索引。
>
> Source of truth：`frontend/app/globals.css` 中的 `.lv-theme` 块（line 1299+）。
> 哲学和原则：`docs/design/visual-principles.md` v2.3。
> 封面规范：`docs/design/cover-art-spec.md` v1.1。
> 字体样张：`/dev/type` 路由（开 dev server 后访问）。
>
> **v2.2 → v2.3 变更**：色板换皮 cinematic gold —— accent #c9b48a → **#dfc290** 香槟金、accent-2 苔绿 #7fb091 → **银雾 #aeb4b8**、danger #b85c5c → **暖珊瑚 #ef8276**、bg/ink 全档微调。typography 9 档 / clamp / 字体三套 / 圆角 / 间距 / z-index / 动效令牌全部不变。
>
> **v2.1 → v2.2 变更**（保留备查）：字号 7 档 → 9 档，全部 clamp 化，serif 字重 300/400 → 400/500，caps 字距 0.18 → 0.2em，叙事字体 serif → sans。

---

## 0. 怎么用

```tsx
// 容器加 .lv-theme（一般在最外层 layout）
<div className="lv-theme">

  {/* 排版用 .lv-t-* 工具类，不要写 inline font-size */}
  <h1 className="lv-t-display">InkWild</h1>
  <p className="lv-t-body-long">活成另一个自己</p>

  {/* 颜色 / 间距 / 圆角用 var() 引用 */}
  <div style={{
    background: 'var(--lv-bg-1)',
    padding: 'var(--lv-s-4)',
    borderRadius: 'var(--lv-r-card)',
  }}>...</div>

  {/* 表单用 .lv-input + .lv-form-* 类 */}
  <label className="lv-form-label lv-form-label--required">世界名</label>
  <input className="lv-input" />
  <span className="lv-form-help">2-20 字</span>

</div>
```

---

## 1. 颜色令牌

### 1.1 底色 / 文字 / 边线（v2.3 cinematic gold）

| Token | 值 | 用途 |
|---|---|---|
| `--lv-bg`         | `#08080a` | 页面主背景（暗影底色） |
| `--lv-bg-stage`   | `#050507` | 游戏页舞台背景（比 lv-bg 再深一档） |
| `--lv-bg-1`       | `#0d1014` | 卡片底 |
| `--lv-bg-2`       | `#15181c` | 微抬起表面 |
| `--lv-line`       | `rgba(255,255,255,0.06)` | 默认边线 |
| `--lv-line-2`     | `rgba(255,255,255,0.10)` | 强调边线 |
| `--lv-ink`        | `#f5f2eb` | 暖象牙 — 主文本 |
| `--lv-ink-2`      | `#c4bcae` | 砂色次级文本 |
| `--lv-ink-3`      | `#8c8273` | 烟青铜 — 辅助文本 / 时间戳 |
| `--lv-ink-4`      | `#4a4338` | 暗金炭 — 边框 / 占位 |
| `--lv-ink-5`      | `#1f1c18` | 深色块 / 卡片深描边 |

### 1.2 模式编码（双 accent，v2.3 cinematic gold）

| Token | 值 | 唯一用途 |
|---|---|---|
| `--lv-accent`      | `#dfc290` 香槟金 | 剧本模式 ◆ / hero italic 高亮（≤1 处/屏）/ 主 CTA hover |
| `--lv-accent-2`    | `#aeb4b8` 银雾 | 自由模式 ◇（**严禁**装饰用法） |
| `--lv-accent-soft` | `rgba(223,194,144,0.10)` | accent 柔光底（focus ring 等） |

> 见 `visual-principles.md` §2.1。**装饰性 accent 一屏 ≤ 1 处，且只许香槟金。**
>
> v2.3 起 `--lv-accent-2` 与 `--lv-success` 解绑：accent-2 是自由模式的视觉编码（银雾），success 是状态反馈（苔绿）。

### 1.3 状态色（仅状态反馈，不参与装饰）

| Token | 值 | 用途 |
|---|---|---|
| `--lv-danger`  | `#ef8276` | 暖珊瑚红 — 错误信息、删除确认 |
| `--lv-warn`    | `#c9a36a` | 警告 |
| `--lv-success` | `#7fb091` | 苔绿 — 仅成功态反馈（v2.3 起独立 token） |

---

## 2. 排版令牌

### 2.1 字体栈

| Token | 值 |
|---|---|
| `--lv-font-serif` | `Cormorant Garamond, Noto Serif SC, Source Han Serif SC, Songti SC, ui-serif, serif` |
| `--lv-font-sans`  | `Inter, PingFang SC, Noto Sans SC, system-ui, sans-serif` |
| `--lv-font-mono`  | `JetBrains Mono, SF Mono, ui-monospace, monospace` |

### 2.2 字号阶梯（钉死 9 档，clamp 平滑）

| Token | clamp 实现 | 移动 | 桌面 | 工具类 | 用途 | 字体 |
|---|---|---|---|---|---|---|
| `--lv-t-display`   | `clamp(48px, 9vw, 112px)`  | 48 | 112 | `.lv-t-display`   | Hero 大标题（每页 ≤1） | serif |
| `--lv-t-h1`        | `clamp(28px, 4vw, 48px)`   | 28 | 48  | `.lv-t-h1`        | 页面主标题 | serif |
| `--lv-t-h2`        | `clamp(20px, 2.4vw, 28px)` | 20 | 28  | `.lv-t-h2`        | 区块/section 标题 | serif |
| `--lv-t-h3`        | `clamp(16px, 1.4vw, 18px)` | 16 | 18  | `.lv-t-h3`        | 卡片/小区块标题 | sans |
| `--lv-t-narrative` | `clamp(15px, 1vw, 17px)`   | 15 | 17  | `.lv-t-narrative` | 叙事正文（play / world detail） | sans |
| `--lv-t-body`      | 15px 固定                  | 15 | 15  | `.lv-t-body` / `.lv-t-body-long` | UI 正文 | sans |
| `--lv-t-meta`      | 12px 固定                  | 12 | 12  | `.lv-t-meta`      | 副信息、tag、帮助 | sans |
| `--lv-t-caps`      | 11px 固定                  | 11 | 11  | `.lv-t-caps`      | 大写小标签（已配 uppercase） | mono |
| `--lv-t-micro`     | 10px 固定                  | 10 | 10  | `.lv-t-micro`     | 极小标记（每页 ≤3） | mono |

### 2.3 行高（已嵌入工具类）

| 工具类 | line-height |
|---|---|
| `.lv-t-display`   | 1.05 |
| `.lv-t-h1`        | 1.1 |
| `.lv-t-h2`        | 1.2 |
| `.lv-t-h3`        | 1.35 |
| `.lv-t-narrative` | **1.85**（不可改） |
| `.lv-t-body`      | 1.6 |
| `.lv-t-body-long` | 1.7 |
| `.lv-t-meta`      | 1.5 |
| `.lv-t-caps` / `.lv-t-micro` | 1.4 |

### 2.4 字间距

| 场景 | 值 |
|---|---|
| `.lv-t-display` (serif) | `-0.02em` |
| `.lv-t-h1` (serif) | `-0.015em` |
| `.lv-t-h2` (serif) | `-0.01em` |
| `.lv-t-h3` (sans) | 0 |
| `.lv-t-narrative` (sans CJK) | `0.005em` |
| sans 正文 | 0 (默认) |
| `.lv-t-caps` (mono ALL CAPS) | `0.2em` |
| `.lv-t-micro` (mono ALL CAPS) | `0.15em` |

### 2.5 字重

| 字体 | 允许字重 |
|---|---|
| serif (Cormorant + 思源宋体) | **400 / 500**（300 禁用，对中文 serif 太细） |
| sans (Inter + 苹方) | 400 / 500 / 600（**禁止 700+**） |
| mono (JetBrains Mono) | 500 单一字重 |

### 2.6 旧 alias（已废）

`globals.css` 中 `--lv-h1 / h2 / h3 / lead / body` 与 class `.lv-h1 / h2 / lead / caps` 保留为兜底定义。**实际消费 0 处**（2026-05-09 grep 验证），下次 `globals.css` 清理 PR 一并删除。新代码统一用 `.lv-t-*` / `--lv-t-*`，不要新增 alias 引用。

---

## 3. 圆角令牌（钉死 3 档）

| Token | 值 | 唯一用途 |
|---|---|---|
| `--lv-r-card`  | 16px   | 卡片、面板、modal、徽章、角标 |
| `--lv-r-input` | 10px   | **仅** input / select / textarea |
| `--lv-r-pill`  | 9999px | 按钮、chip、tag、nav 胶囊 |

> **不要**再写 `rounded-[1.25rem]` `rounded-3xl` 等任意值。

---

## 4. 间距令牌（钉死 9 档）

| Token | 值 | Tailwind 等价 |
|---|---|---|
| `--lv-s-1`  | 4px  | `gap-1` `p-1` |
| `--lv-s-2`  | 8px  | `gap-2` `p-2` |
| `--lv-s-3`  | 12px | `gap-3` `p-3` |
| `--lv-s-4`  | 16px | `gap-4` `p-4` |
| `--lv-s-6`  | 24px | `gap-6` `p-6` |
| `--lv-s-8`  | 32px | `gap-8` `p-8` |
| `--lv-s-12` | 48px | `gap-12` `p-12` |
| `--lv-s-16` | 64px | `gap-16` `p-16` |
| `--lv-s-24` | 96px (移动端 64px) | `gap-24` `p-24` |

> 禁用 `gap-5` `gap-7` `gap-9` `gap-10` `gap-11`、`p-5` `p-7` 等中间档。

---

## 5. 图层令牌（钉死 6 档）

| Token | 值 | 用途 |
|---|---|---|
| `--lv-z-base`    | 1   | 默认堆叠 |
| `--lv-z-sticky`  | 50  | sticky header / sticky CTA |
| `--lv-z-drawer`  | 100 | 侧抽屉、底部抽屉 |
| `--lv-z-modal`   | 200 | modal 对话框 |
| `--lv-z-toast`   | 300 | toast、流式状态浮层 |
| `--lv-z-overlay` | 400 | 全屏覆盖（暂停、ending、加载） |

> 不要再写 `z-[99]` `z-[999]` `z-[9999]`。

---

## 6. 布局令牌

| Token | 值 | 用途 |
|---|---|---|
| `--lv-pad-x` | 48px (移动端 16px，s-4) | section 横向内边距 |
| `--lv-pad-y` | 96px (移动端 64px) | section 纵向内边距 |
| `--lv-max-w` | 1320px | 主内容容器最大宽 |
| `--lv-max-w-read` | 760px | 长文阅读 / 游戏页阅读区 |

> 移动端断点 `@media (max-width: 768px)` 内 `--lv-s-24` 折叠到 64px（避免章节间距过大）；其余字号 / 间距 / 圆角不再 media query 跳变。

---

## 7. 动效令牌

### 7.1 CSS 时长 / 缓动

| Token | 值 | 用途 |
|---|---|---|
| `--lv-ease`              | `cubic-bezier(0.2, 0.7, 0.2, 1)` | 全站统一缓动 |
| `--lv-dur-fast`          | 200ms  | 一切常规交互（hover、按钮、modal、抽屉） |
| `--lv-dur-page`          | 400ms  | 页面进入 / 单项 fade-up（旧；列表/scroll reveal 走 §7.2） |
| `--lv-dur-cinematic-a`   | 1800ms | 例外 A：hero crossfade / Ken Burns |
| `--lv-dur-cinematic-b`   | 1200ms | 例外 B：游戏页结局 fade-in |

> `prefers-reduced-motion: reduce` 命中时，cinematic A/B 自动降到 200ms（已在 globals.css 实现）。

### 7.2 Framer Motion 预设（`frontend/lib/motion.ts`）

整站 Scroll Reveal / 列表入场 stagger **只用** 这些预设（详见 visual-principles §6 Scroll Reveal & 列表入场 stagger）：

| 预设 | 类型 | 用途 |
|---|---|---|
| `LV_EASE` | `[0.2, 0.7, 0.2, 1]` | 缓动（同 `--lv-ease`） |
| `lvFastEase` | `{duration: 0.2, ease: LV_EASE}` | hover / 按钮等常规 transition |
| `lvPageEase` | `{duration: 0.4, ease: LV_EASE}` | 单 hero / single fade-up（不带 stagger） |
| `lvFadeUp` | variants `{hidden, show}` | 单元素从下方浮起 |
| `lvFadeIn` | variants | 单元素纯 opacity 淡入 |
| `lvCinematicFadeIn` | variants | 例外 B：游戏页结局长 fade |
| **`lvStaggerContainer`** | variants | **列表 / 网格父容器**，控 stagger 70ms + delayChildren 40ms |
| **`lvStaggerItem`** | variants | **列表子项**，500ms fade-up + y:12px lift |

---

## 8. 表单类（§11 实现）

| Class | 用途 |
|---|---|
| `.lv-input`             | input / select / textarea 基线（44px 高，10px 圆角） |
| `.lv-input--textarea`   | textarea 变体（高度自动，min-height 96px） |
| `.lv-input--readonly`   | readonly 变体（深背景、不可点） |
| `.lv-form-label`        | label 文字（`t-meta` / `--lv-ink-2`） |
| `.lv-form-label--required` | 必填变体（label 后加 4px 暖金小点） |
| `.lv-form-help`         | 帮助文字（`t-meta` / `--lv-ink-3`，input 下方） |
| `.lv-form-error`        | 错误文字（`t-meta` / `--lv-danger`，前置 6px 红点） |

---

## 9. 其他工具类

| Class | 用途 |
|---|---|
| `.lv-loading-pulse` | 8px 暖金圆，1800ms 脉冲（§10.1 全屏加载） |
| **`.lv-skel`** | **Skeleton 骨架屏统一类**：linear-gradient 柔光扫过 2s 周期。形状由 caller 用 `borderRadius` + `aspectRatio`/`height`/`width` 控制。详见 visual-principles §10.1 Skeleton Screen 骨架屏 |
| `.lv-btn` `.lv-btn-primary` `.lv-btn-lg` `.lv-btn-sm` | 按钮（pill 形） |
| `.lv-section` `.lv-inner` | section padding + max-w 容器 |
| `.lv-frame` `.lv-grain` | hero 帧 / SVG 颗粒叠层 |

`.lv-theme :focus-visible` 已配置 2px 暖金焦点环（§13）。

---

## 10. 不要再用的旧令牌

以下系统在 globals.css 顶部标记为 deprecated，仅作向后兼容，新代码不要消费：

- `@theme inline` 块的 `--font-size-*` / `--radius-*` / `--color-*` / `--duration-*`（teal accent 系统，play page / admin 用）
- `:root` 块的 `--ta-*`（创作工坊系统，teal accent）

新代码全部从 `.lv-theme` 走。旧 token 块在 v2.3 落地后保留为兜底，待下一次 `globals.css` 清理 PR 时整组删除。归档版重构计划见 `docs/_archive/frontend-refactor-2026-05.md`。

ESLint（v2.2 末期决策，2026-05-09）：**只锁一条** —— 禁止 `var(--font-size-*)` / `var(--ta-*)` / `var(--color-accent)` 引用。字号 / 间距 / 圆角 / inline `fontSize` 不上 lint，由 §14 走查 + 设计师眼睛把关。详见 visual-principles §14.5、`frontend/eslint.config.mjs`。

---

## 11. 字体样张

`/dev/type` 路由（开 dev server 后访问）—— 9 档字号 × 真实文案 + 字体三套样例 + 真实页面组合示例。所有 PR 提交前对照此页验证。

---

> 维护人：jie / Claude Code
> 最后更新：2026-05-23（v2.3 cinematic gold：色板换皮，accent / accent-2 / danger / bg / ink 全档更新；其余 token 不变）
> 配套文档：`visual-principles.md` v2.3（原则）、`cover-art-spec.md` v1.1（封面）、`play-mode-spec.md`（play 例外）。重构计划 `docs/_archive/frontend-refactor-2026-05.md` 已归档
