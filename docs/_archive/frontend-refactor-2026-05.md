# 前端重构计划 · 2026-05（已完成 · 归档）

> 状态：**已完成**（2026-05-08 启动 → 2026-05-23 收尾，v2.3 cinematic gold 上线后整体落地）
> 负责：jie + Claude Code
> 实际用时：约 2 周

> **归档说明**：本文档保留用于追溯重构决策与阶段产物，不再更新。后续视觉规范以
> [`docs/design/visual-principles.md`](../design/visual-principles.md) v2.3 + [`frontend-spec.md`](../design/frontend-spec.md) v2.3 为准。

## 0. 为什么要做

用户感受三件事不对：

1. **页面东拼西凑**：从 / 走到 /play 经过四种视觉年代（V2 cinematic 金/绿、V1 旧 teal、`--ta-*` 灰、各种 inline 写死），不像同一个产品
2. **字号忽大忽小**：163 处 `text-[Xrem]` 破例值散在 30+ 文件，三套 token 系统并存，没有 ESLint 锁
3. **移动端粗糙**：桌面优先布局硬挤进 375px，play 页双栏挤成一坨，不是真正 mobile-first

**这次重构的本质**：把已经存在的产品做一次"统一+正规化"，从"功能能跑的原型"变成"看起来像正经产品"。

## 产品视觉哲学（必读 — 2026-05-08 加入）

这一节比所有阶段任务都重要。前两版登录页失败的根因都是违反了这条：

### 极简优先 — 装饰堆叠 = 廉价

**高级感来自"什么都没有"**，不是来自"加了什么"。

具体反面教材（来自 2026-05-08 登录页迭代）：
- ❌ 毛玻璃 backdrop-filter + 暖金角光 + 苔绿微光 + 颗粒 SVG noise = 装饰堆叠 → 廉价
- ❌ 装饰线 eyebrow `──── SIGN IN ────` = 2010 PSD 模板审美
- ❌ "继续你的故事" + "那些没结束的世界还在等你" = 中二脑补文案
- ❌ modal 入场动画 600ms + 背景 30s drift + 按钮 hover 暖金光晕 + 上抬 1px = 过度交互
- ❌ 按钮文字加 "→" 箭头 = 多余装饰

**正面参照**：ChatGPT / Linear / Vercel / Apple 登录页都不做以上任何一件事。

### 不要中二

文案克制，不脑补诗意。**Letterboxd 调性 ≠ 写歌词**。

| ❌ 中二 | ✅ 克制 |
|---|---|
| 继续你的故事 | 登录 / 欢迎回来 |
| 那些没结束的世界还在等你 | 登录以继续 TaleAlive |
| 探索者通道 | （删掉） |
| 回到你的世界 | 欢迎回来 |
| 进入 → | 继续 |
| 雨夜霓虹中的位面坐标 | （删掉） |

**判别方法**：把文案读给一个第一次看产品的朋友听，他笑了 → 中二。

### 1:1 还原参考产品，不要"借鉴 + 自由发挥"

页面定调时**指定具体参考产品**，1:1 还原，不要"参考精神 + 自由发挥"。

理由：自由发挥 = 加自己审美 = 加装饰 = 廉价。1:1 还原是最可靠的避坑方式。

具体页面参考已写到 §5 阶段 5 页面表。

### 颜色克制 — accent 是稀缺资源

`--lv-accent` 暖金一屏 ≤ 1 处，且只用于"主 CTA hover"或"模式编码"或"hero italic 高亮"。装饰用法**禁止**。

苔绿 `--lv-accent-2` 严格保留给"自由模式"语义编码，**装饰用法禁止**。

违反这条，每多用一处 accent 都让产品掉一档。

### 动效克制

- 一切常规交互 ≤ 200ms
- 页面进入 ≤ 400ms
- 长动效（cinematic 例外）只准在：landing hero / 游戏页结局 / 加载脉冲。**登录、列表、表单页一律不做**。
- 不要"为了显得高级"加 hover 上抬 / 光晕 / 微动 — 这些组合起来 = 廉价。

---

## 1. 不做的事（边界）

避免误解，列死：

- ❌ 不换技术栈（Next 16 / React 19 / Tailwind v4 / Zustand 全留）
- ❌ 不重排目录（`app/components/lib/stores` 不动）
- ❌ 不重做信息架构（页面流程、跳转关系不动）
- ❌ 不加新功能、新页面
- ❌ 不改后端 API
- ❌ 不做 app、不做小程序、不做英文版、不做浅色主题（i18n 基础设施做但只填中文）
- ❌ 不做主题切换（dark only）

## 2. 目标产物

完成后用户得到：

| 维度 | 改完之后 |
|---|---|
| **视觉一致性** | landing → play 一路下去，同一套金/绿、同一套字体、同一套节奏 |
| **字号秩序** | 9 档钉死，由 PR 走查 + 设计师眼睛把关；ESLint 仅锁旧 token 漂移 |
| **动效一致** | Framer Motion 统一 motion graph：页面切换、卡片悬浮、抽屉打开 |
| **移动端可用** | 375px 单手玩 play 页（单栏 + 抽屉）、navbar 改底部 tab |
| **数据状态规范** | 骨架屏 / 重试按钮 / 表单错误清晰显示 |
| **可加桌面图标** | PWA manifest + service worker，"加到主屏" 像 app |

## 3. 阶段划分

每阶段产出物清晰，可独立合入。

### 阶段 0：Type System Spec（已完成）

- [x] 定 9 档字号（display/h1/h2/h3/narrative/body/meta/caps/micro）
- [x] 全部 clamp() 化，移动→桌面平滑过渡
- [x] 字体三套搭配（serif/sans/mono）法定用途定死
- [x] 字重 400/500（serif）、400/500/600（sans）
- [x] 样张页 `/dev/type` 上线，作为 single source of truth
- [x] `<body>` 挂 `lv-theme` class，`.lv-t-*` 工具类全部生效（2026-05-08）

**产物**：`globals.css` 含完整 `.lv-theme` 块 + 9 档 `.lv-t-*` 工具类（line 1190+）。`<body>` 已挂 `lv-theme` class（layout.tsx），viewport meta 加 `viewport-fit=cover` + `theme-color #0a0a0c`。`/dev/type` 桌面 + 移动双断点 HTML/CSS 验证通过（9 档工具类全部出现在 DOM，CSS 6562 行含 `.lv-theme` 51 处）。老页面 `/` `/login` `/discover` `/history` `/admin` 冒烟无回归。

### 阶段 1：文档统一（已完成）

- [x] `docs/design/visual-principles.md` 升 v2.2（9 档 + clamp）
- [x] `docs/design/frontend-spec.md` 升 v2.2（token 值表更新）
- [x] `CLAUDE.md` + `frontend/AGENTS.md` 对齐新版本
- [x] 本计划文档进入 `docs/plans/`
- [x] `globals.css` 注释从 v2.1 校准到 v2.2（2026-05-08）

**产物**：所有文档指向同一个 v2.2 规范，新加入者只读 v2.2 不会看到过期信息。

### 阶段 2：工程约束（已完成 — 2026-05-09 决策最小约束）

- [x] ESLint：**仅锁旧 token**（`--font-size-*` / `--ta-*` / `--color-accent`），CI 卡死
- [x] CI 跑 lint，旧 token 引用 = PR 拒绝
- [~] 字号 / 间距 / 圆角 / inline `fontSize` / 任意 z-index 等破例值**不上 lint**——v2.2 早期锁过一轮，实战发现机器拦不出审美且误伤 `text-[var(--lv-ink-3)]` 这种合理颜色 token 写法，改为约定级 + 走查（见 visual-principles §14.5、§14.3）

**产物**：旧 token 漂移由机器把守；视觉一致性由 PR 走查 + 设计师眼睛把关。详见 `frontend/eslint.config.mjs` 头注释。

### 阶段 3：基础设施（已完成）

按"立刻有产品感"排序：

- [x] **TanStack Query**：装好（`@tanstack/react-query` ^5.100，含 devtools）+ `components/QueryProvider.tsx`
- [x] **React Hook Form + Zod**：装好（react-hook-form ^7.75 + zod ^4.4 + `@hookform/resolvers` ^5.2）
- [x] **Framer Motion**：`motion` ^12.38，`motion/react` 子包；预设见 `frontend/lib/motion.ts`（`lvStaggerContainer` / `lvStaggerItem` 等）
- [x] **next-intl**：`^4.11`，挂载在 `app/layout.tsx`，文案在 `i18n/zh.json` + `i18n/en.json`
- [x] **Radix + Vaul + cmdk**：选择性接入了 `@radix-ui/react-dialog`、`react-popover`、`react-toast`、`vaul`（Drawer）、`cmdk`（Command Menu），未引入 shadcn 整套
- [~] **Storybook**：未装，决策保留 — 用 `app/dev/*` 路由 + `/dev/type` 字体样张代替（实战发现 dev 路由对设计走查足够）

**产物**：基础设施全部就位。新页面有数据 / 表单 / 动效 / i18n / 复杂交互组件现成方案。

### 阶段 4：移动端布局重做（已完成）

真正 mobile-first：

- [x] 所有组件先 375px，桌面是放大版
- [x] 触控目标 ≥ 44px
- [x] `100dvh` + safe-area-inset 处理刘海屏（layout.tsx `viewportFit: cover`）
- [x] **`<BottomTabBar />`**（首页 / 发现 / 历史 / 我），挂在 `app/layout.tsx`，play 页自动隐藏
- [x] **Play 页移动端**：单栏 + 底部抽屉（`ContextDrawer`、`UnifiedSidePanel`、vaul）
- [x] **World detail / History 移动端**：纵向卡片排列，hero 在 375px 保留震撼

**产物**：375px 设备打开任意页面单手能玩。

### 阶段 5：视觉迁移 page train（已完成 + v2.3 换皮）

| 顺序 | 页面 | 状态 |
|---|---|---|
| 1 | **登录** `/login` | ✅ v2.3 落地（含 V2 极简登录） |
| 2 | **创作工坊** `/workshop/*` | ✅ v2.3 落地（原 `app/admin/*` 已迁，admin 控制台拆到独立项目 `admin-frontend/`） |
| 3 | **世界详情** `/worlds/[id]` | ✅ v2.3 落地 |
| 4 | **游戏页** `/play/[id]` | ✅ v2.3 落地（旧 teal 全部清除；play 专属 spec 见 `docs/design/play-mode-spec.md`） |
| 5 | **删除旧 token** | ✅ ESLint 锁 `--font-size-*` / `--ta-*` / `--color-accent`；`@theme inline` 块 deprecated 保留作为兜底 |

**产物**：所有主入口页统一在 `.lv-theme` v2.3 下；admin 控制台已独立为 `admin-frontend/` 项目（不复用主站视觉系统，桌面优先）。

### 阶段 6：play 沉浸表面专属规范（已完成）

play 是整站最复杂、停留最久的页面，沉浸优先于内容墙密度：

- [x] 写明豁免边界：豁免 max-width / nav / padding / backdrop-filter，不豁免 type scale / accent / motion
- [x] play 局部 token map（继承 lv 但允许 cinematic 例外）
- [x] 案件板规范：清单看板，禁止全息特效堆叠

**产物**：`docs/design/play-mode-spec.md` 已独立成 spec，列明 6 条例外 + 不豁免清单。

### 阶段 7：PWA + 收尾（已完成）

- [x] `manifest.webmanifest` + `icon.svg` / `icon-maskable.svg`
- [x] service worker 由 **serwist** (`@serwist/next` ^9.5) 生成；源 `app/sw.ts`，产物 `public/sw.js`
- [x] safe-area + 主屏图标体验（`layout.tsx` 配 `viewportFit: cover` + `appleWebApp`）
- [x] memory / docs 同步更新（含本归档）

**产物**：用户能"加到主屏"，打开像 app。

---

## v2.3 cinematic gold 收尾（2026-05-23）

阶段 5 收尾后，2026-05 又叠加了一次色板换皮 (v2.3)：
- accent `#c9b48a` → 香槟金 `#dfc290`（更亮、更暖）
- accent-2 苔绿 → 银雾（避免与 success 绿色语义冲突）
- danger `#b85c5c` → 暖珊瑚 `#ef8276`
- bg / ink 全档微调

详见 `docs/design/visual-principles.md` v2.3 头部 changelog。本计划至此完整收口。

## 4. 验收标准

每个阶段合入前必须通过：

- [ ] 视觉对照 `/dev/type` 样张页，9 档使用正确
- [ ] ESLint 无破例值告警
- [ ] 桌面（1280px）+ 移动（375px）两个断点截图对照
- [ ] PR 模板自检表（`.github/pull_request_template.md`）全打勾
- [ ] 涉及数据接口的页面：loading / empty / error 三态都要做

## 5. 风险与回退

| 风险 | 应对 |
|---|---|
| Type scale 落地后某档"感觉不对" | 改 `globals.css` 一处即可全站生效，不用回退页面 |
| Framer Motion 与 Next 16 RSC 兼容问题 | 用 `motion/react` 子包，标 `"use client"` 即可 |
| shadcn 组件视觉与 cinematic 冲突 | 不用整套，只挑交互复杂的（Dialog/Drawer 等），retheme 后纳入 |
| 移动端布局影响桌面体验 | 每次改动桌面（1280）+ 移动（375）双断点验证 |
| 工期超出 4–5 周 | 阶段独立可合入，超期则砍阶段 6/7 优先稳基线 |

## 6. 不在本计划内

以下属未来工作，本次不做：

- 服务端组件（RSC）化：13 个页面 100% `"use client"`，未来可按页面收益评估迁移
- 桌面 app（Electron / Tauri）+ 移动 app（Capacitor / RN）
- 浅色主题 / 双 dark 皮肤差异化
- 英文版（i18n 产品层）
- 后端 API 重构 / 性能优化

---

> 维护：jie / Claude Code
> 最后更新：2026-05-23（v2.3 cinematic gold 收尾，全部阶段标完成，整体归档）
> 状态：**已完成 · 归档**
