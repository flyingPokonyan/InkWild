# 通用选择交互（ChoiceScene）设计

> 状态：design draft
> 范围：worlds/[id]/start 的 mode / script / character 选择 + IPRecognitionCard 的 IP 决策 + 三屏 aura 色相统一

---

## 1. 为什么做

现在"让玩家做选择"在站内有两套独立实现：

- `worlds/[id]/start` 走 step-based 翻页，里面三种自定义卡（ModeChoice / ScriptSelectionCard / CharacterCard）
- `IPRecognitionCard` 走 GenerationLoadingScreen.centerSlot，800 行自定义 CSS

视觉语言不一致、选中态用了暖金（违反 v2.2 §2.2）、剧本卡无图、aura 用了 v2.2 之前的暖金（违反 §2.1）。

这次重构合到一套组件，配色按 v2.2 严格修，剧本卡补图。

## 2. 设计决策

**外壳统一**：5 层背景堆叠 = 世界封面虚化（可选）+ 暗化遮罩 + 月光白 aura（7s 呼吸）+ edge vignette + 内容透明层。`GameLoadingScreen` / `GenerationLoadingScreen` / 新建的 `ChoiceScene` 三屏共用，aura 从暖金 `rgba(201,180,138,...)` 改月光白 `rgba(232,227,216,...)`。

**两种 variant，按选项是否有图分**：

- **MediaChoiceCard**（角色 / 剧本）：3:4 卡片，图片背景铺满，底部 gradient + 文字浮层。剧本走 `script.cover_image`。
- **ListChoiceOption**（mode / IP 决策）：紧凑横条，编号 + 标题 + 描述 + 箭头。

**选中态严格走 ink 灰阶**（v2.2 §2.2）：背景 `rgba(255,255,255,0.06)` + border `--lv-ink-2` + 微位移。**暖金只允许出现在剧本 ◆ / 自由 ◇ 模式编码徽章**（v2.2 §2.1 法定用途）。

**动效全部走 v2.2 §6**：入场用 `lvStaggerContainer/Item`（500ms + 70ms stagger）、hover / 选中 200ms、aura 7s ease-in-out 循环、prefers-reduced-motion 命中时 aura 停 + stagger 退化。

## 3. 组件拆分

新建 `frontend/components/choice/`：

- **ChoiceScene** — 外壳容器。props 包括标题 / eyebrow / step 进度 / 返回回调 / 倒计时 / 封面图。支持 `embedded` 模式跳过外壳渲染（IPRecognitionCard 嵌入 GenerationLoadingScreen 时用）。
- **AmbientAura** — aura + vignette 双层，三屏共用。
- **MediaChoiceCard / ListChoiceOption** — 两种 variant，独立可测。
- **useChoiceCountdown** — 倒计时 hook（仅 IP 决策用）。

## 4. 数据层

`ScriptDTO` 加 `cover_image: str | None`（后端 model 已有，schema 透传，无 migration）。前端 `ScriptDTO` 同步加字段，`ScriptCardModel` 加 `coverImage`，implicit 剧本用 `world.cover_image` 兜底。

## 5. 落点

| 改 | 怎么改 |
|---|---|
| `worlds/[id]/start/page.tsx` | step 控制流（reducer）保留；渲染层全部走 ChoiceScene + MediaChoiceCard / ListChoiceOption；删内联 InlineLoadingScreen / ModeChoice |
| `IPRecognitionCard.tsx` | 重写为 ChoiceScene embedded + ListChoiceOption + useChoiceCountdown，删 800 行自定义 CSS |
| `GameLoadingScreen` / `GenerationLoadingScreen` | 替换内联 aura `<style>` 为 `<AmbientAura />` 引用 |
| `CharacterCard.tsx` / `ScriptSelectionCard.tsx` | 删除，调用方改用 MediaChoiceCard |

## 6. 不做

- 不动 SessionLock、startGame 业务逻辑、step 控制流 reducer
- 不动 GenerationLoadingScreen 的 12 阶段进度面板
- 不引入新色 / 新动效库

## 7. 验收口径

- 三屏 aura 色相一致、无暖金 wash
- worlds/[id]/start 4 步 + IPRecognitionCard 共用 ChoiceScene
- 剧本卡带图（cover_image 或 fallback 渐变）
- 选中态 0 处暖金；accent 仅在 ◆ / ◇ 徽章
- PR 自检表（`.github/pull_request_template.md`）全过

---

> 维护：jie / Claude Code · 2026-05-18 · 落地见 implementation plan
