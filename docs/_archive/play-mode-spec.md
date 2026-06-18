# Play Mode Spec — 游戏页特殊规范

> 配套：`docs/design/visual-principles.md` v2.3 §12（总规）
> 本文档：play 页相对总规的**例外清单 + 实现细节**
> 起草：2026-05-09（基于 stage 5d 实施总结）；2026-05-23 同步 v2.3 accent-2 (苔绿 → 银雾)
>
> 注：spec 是参考，不是律法。实战中觉得不对就调，调完更新这里。

---

## 1. 为什么 play 页要有专属 spec

play 是用户停留最久的页面，沉浸优先于"内容墙"密度。视觉上跟 landing / discover / admin 节奏不同：
- 不展示信息密度，展示"故事正在发生"
- 不强调 navigation，nav 折叠
- 容器宽度收窄（760 阅读宽 vs 全站 1320 主容器）
- 长动效允许（结局 cinematic）

但仍然受总规约束。下面列**例外**和**保留**两类。

---

## 2. play 相对总规的例外（允许做的事）

| 例外 | 范围 | 理由 |
|---|---|---|
| `max-width: 760px` 而非全站 1320 | play stage 阅读区 | 长文阅读舒适宽度（visual-principles §8.3） |
| nav 折叠为右上角图标 | 桌面 + 移动 | 沉浸态，nav 不常驻 |
| 移动端**隐藏** BottomTabBar | 移动 < 768 | nav 折叠后 tab bar 也碍眼 |
| backdrop-filter 毛玻璃 | header 浮层 / drawer / case-hologram modal | 沉浸态需要前后景分离感 |
| 结局动画 1200ms fade-in + 段间 600ms | 仅 EndingCinematic / EndingScreen | cinematic 例外 B（visual-principles §6） |
| 案件板 modal `backdrop-filter: blur(40px)` | 仅 case-hologram | 全屏覆盖前后景需明显隔离 |

---

## 3. play 不豁免的（仍受总规约束）

- 字号档位：仍走 `.lv-t-*` 工具类（display/h1/h2/h3/narrative/body/meta/caps/micro）
- 颜色 token：仍用 `--lv-*`（香槟金 accent for ◆ 剧本，银雾 accent-2 for ◇ 自由 —— v2.3 起 accent-2 由苔绿改为银雾）
- 一屏字号 ≤ 4 档（micro 不计）
- z-index 6 档体系（base/sticky/drawer/modal/toast/overlay）
- 触摸目标 ≥ 44px
- 焦点环 + prefers-reduced-motion 降级
- 文案克制（不写"那些没结束的世界还在等你"类中二）

---

## 4. 实施细节

### 4.1 叙事段落（play-message-narrator）

```
font:        sans (`--lv-font-sans`，v2.2 改 sans，原 serif 已废)
font-size:   `.lv-t-narrative` (clamp 15→17px)
line-height: 1.85（不可改 — 叙事感来源）
letter-spacing: 0.005em（轻微正字距帮 CJK 散开）
段落间距: var(--lv-s-6) (24px)
玩家动作: italic + 缩进 1em
系统提示: 居中、`.lv-t-meta`、--lv-ink-3
```

### 4.2 消息呈现（不做 IM）

- **不**用 IM 式气泡（带 background + border 的 bubble）
- 玩家消息：右对齐 + italic + 左侧暖金 border 2px（剧本模式）/ 苔绿 border 2px（自由模式）
- NPC / 旁白：左对齐，无 border，仅角色名 caps（mono uppercase ls 0.2em）
- 角色名与叙述间留 8px 垂直间距

### 4.3 思考态进度轨道（StreamingStatusRail）

提交动作后、首包前的"思考态"展示（`streamPhase==="processing"`）。**2026-05-30 重设**（旧版是底部 6px 金点 + "演化中…"）：

```
位置:   时间线底部（最后一条消息下方），左对齐
内容:   小号 Branch logo（持续 Grow 动画，§10.1）+ 演进式过程反馈文案
文案:   按真实里程碑 stage 切换（next-intl play.processing.*）：
        接收你的行动 → 推演『{你的输入}』 → {NPC} 进入这一幕 → 落笔成文
样式:   小字非斜体 var(--lv-ink-3)，比 narrative 小一档，与正文区分
转场:   首包到达（→streaming）时整体 300ms 淡出/上移（AnimatePresence），不硬切
```

- 文案由后端蹭 director 流式**真实里程碑**驱动（见 `../modules/sse-protocol.md` 的 `processing(kind=progress)` + `../modules/orchestrator.md §2.7`），**真实、每回合不同、零额外 LLM**；无 stage（首事件前）= 呼吸态只显 logo。
- 组件 `<LoadingPulse variant="branch" />`；§10.1 合规（Branch 主视觉 + 文案辅助，非纯文字/非"正在加载…"）。
- streaming 时段落末尾**不做** typewriter 逐字（性能差 + 分散注意力），用 8px 闪烁光标即可。

### 4.4 输入框（ActionInput）

```
位置:        底部固定（不浮动跟随滚动，避免抖动）
高度:        56px（比常规 input 略大，是主要交互目标）
圆角:        var(--lv-r-pill)（按胶囊处理，行动入口非 form input）
placeholder: 具体动作示例「查看房间 / 推开门 / 询问她的来历」，**不**写"请输入"
反馈:        提交后输入框 200ms 微下沉再恢复
```

移动端：`100dvh` + `safe-area-inset-bottom` 避免被 iOS Safari 工具栏遮挡。

### 4.5 案件板（CaseHologramPanel）

```
触发:   GameHeader 案件板按钮（可在 IdentityPanel 切换）
开法:   全屏 modal
背景:   backdrop-filter: blur(40px) brightness(0.4)
卡片:   var(--lv-r-card)（16px）
```

**禁堆叠特效**：脉冲、扫光、扫描线、霓虹辉光——案件板是清单看板不是科幻片道具。

子区块清单：
- MissionBriefing（任务简报）
- SuspectProfiles（嫌疑人 + 嫌疑度高/中/低 + 信任 + 情绪）
- EvidenceChain（证据链：物证/证词/推理/其他，含发现位置 + 关联）
- FieldIntel（现场情报：位置 / 时间 / 回合 / 物品 / 已访问地点）

### 4.6 结局动画（EndingCinematic / EndingScreen）

cinematic 例外 B 应用：
- Curtain phase: 4s 黑屏 + 一根 192px 1px 暖金细线 pulse
- Narrative phase: 每段叙述 3.5s 自动推进，800ms fade-in
- 标题揭示: TypeBadge + h1 一起 fadeIn
- Credits phase: 标题 + 证据回顾 + 旅程时间线 + 游戏统计
- Actions phase: 返回首页 + 历史

```
结局标题:  .lv-t-h1 serif（不要 display，display 太重）
正文:     .lv-t-narrative sans
背景图（如有）: Ken Burns，缩放幅度 ≤ 1.05（hero 1.1 太大显廉价）
"点击任意处跳过": .lv-t-micro var(--lv-ink-4)
```

### 4.7 移动端布局（< 768px）

- nav 隐：BottomTabBar 不显（沉浸态例外）；GameHeader 改右上角"≡"图标
- 案件板：从右侧滑入 → 改**底部上推抽屉**
- 双栏（chat + 案件板）→ 单栏 + 抽屉

---

## 5. 移动端单栏 + 抽屉的实现要点

```css
/* play-drawer-modal — 移动端从底部弹出 */
.play-drawer-modal {
  left: 0;
  right: 0;
  bottom: 0;
  max-height: 70dvh;
  border-radius: var(--lv-r-card) var(--lv-r-card) 0 0;
  padding: var(--lv-s-4) var(--lv-s-4) calc(env(safe-area-inset-bottom) + var(--lv-s-4));
  animation: play-drawer-up var(--lv-dur-fast) var(--lv-ease) both;
}
@keyframes play-drawer-up {
  from { opacity: 0; transform: translateY(100%); }
  to   { opacity: 1; transform: translateY(0); }
}
```

桌面端用 `play-drawer-floating`（右侧浮窗），移动端用 `play-drawer-modal`。

---

## 6. 颜色编码（剧本 vs 自由模式）

| 元素 | 剧本 ◆ | 自由 ◇ |
|---|---|---|
| 玩家消息左 border | `--lv-accent` 暖金 | `--lv-accent-2` 苔绿 |
| 模式角标 | `--lv-accent` ◆ | `--lv-accent-2` ◇ |
| 输入框 focus ring | `--lv-accent-soft` | `--lv-accent-2` 14% alpha |
| 主 CTA hover | `--lv-accent` | `--lv-accent-2`（自由模式 stage 启动 CTA） |

模式判断：`gameSession.script_id != null` → 剧本模式。

---

## 7. 跟 visual-principles 总规的关系

| 总规 §X | play 是否豁免 | 备注 |
|---|---|---|
| §1 字号 9 档 | ❌ 不豁免 | 仍走 .lv-t-* |
| §2 颜色 token | ❌ 不豁免 | 仍用 --lv-* |
| §3 圆角 3 档 | ❌ 不豁免 | 16/10/9999 |
| §4 间距 9 档 | ❌ 不豁免 | 1/2/3/4/6/8/12/16/24 |
| §5 z-index 6 档 | ❌ 不豁免 | base/sticky/drawer/modal/toast/overlay |
| §6 动效时长 ≤ 200ms | 🟡 cinematic B 例外 | 仅 EndingCinematic |
| §7 卡片字段 ≤ 5 | n/a | play 不展示卡片 |
| §8 容器宽 1320 | 🟡 760 | play 阅读区收窄 |
| §10 三态 | ❌ 不豁免 | loading / empty / error |
| §11 表单 | ❌ 不豁免 | ActionInput 仍走 .lv-input 体系 |
| §13 a11y | ❌ 不豁免 | focus / 触摸 / reduced-motion 全要 |
| §14 PR 自检表 | ❌ 不豁免 | play PR 同样过自检 |

---

## 8. 实施过的几个判断点（stage 5d 决策记录）

1. **叙事字体改 sans（v2.2 §1.1）**：原 serif 在中文长段不耐读，改 `--lv-font-sans` (Inter + PingFang SC)，line-height 1.85 保留。
2. **不写 typewriter 流式效果**：streaming 时只在段落末尾 8px 暖金光标 pulse。性能更好且不分散注意力。
3. **结局 Cinematic 4 phase**：curtain → narrative → credits → actions，可点击任意处跳过。
4. **状态色复用**：positive impact = `--lv-accent` 暖金，negative = `--lv-danger`，neutral = `--lv-ink-3`（不是引入第三个 accent）。
5. **叙事字体复审：保留 sans（2026-05-09）**：`docs/design/audit-2026-05.md` P0-1 质疑 "serif → sans 是产品调性降级"，建议回滚到 v2.1 serif。出对比 demo `/dev/play-typeface-demo`（同一段中文叙事 + italic 暖金高亮 + 玩家动作 + 系统提示，唯一变量字体族），桌面 + 手机各看一遍后决策：**保留 v2.2 sans**。第 1 条"中文长段 sans 更耐读"的判断在实测中得到验证。后续 spec 不再为这条改动留撤销窗口。

---

> 维护：jie / Claude Code
> 最后更新：2026-05-09
> 配套：`visual-principles.md` v2.2、`frontend-spec.md` v2.2
