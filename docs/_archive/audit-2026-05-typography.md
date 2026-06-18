# Typography 微决策审查附录

> 审查日期：2026-05-10
> 范围：`visual-principles.md` v2.2 §1 + `frontend-spec.md` v2.2 §2 五个具体数值/决策
> 配套主审查：`audit-2026-05.md`（v2.2 整体）
> 审查者：资深产品设计师视角

---

## 暗线

v2.2 在多个数值上向"装饰感 / 海报感 / 影视感"借力（display 112 / 行高 1.85 / caps 0.2em / cinematic 1800ms），但**借的是装饰场景的数值，用在 UI 场景的位置**。修法不是逐项调小，而是拆 UI preset 与 Cinematic preset 两层。

---

## 5 条审查结论

| # | 决策 | 判断 | 推荐 | 信心 |
|---|---|---|---|---|
| 1 | 9 档字号 | **narrative 不是字号档，是 prose preset**；h3 (18) ↔ narrative (17) 仅差 1px；caps/micro 真正差异在字距 | 把 narrative 挪出阶梯改 `.lv-prose-narrative`，9 档收回 8 档 | 🟡 高置信主观 |
| 2 | narrative = sans | 决策已封（保留 sans），但论据"中文长段 sans 更耐读"被过度推广。play 页是**高频交互形态**，不是沉浸长读 | 改写理由为"交互节奏匹配 sans"；world detail >500 字静态文案保留 serif；v2.3 评估 narrator/玩家动作字体分层 | 🟡 主观 |
| 3 | 行高 1.85 | **偏松**。中文 sans 长文舒适区 1.7-1.8（微信读书默认 1.75）。1.85 + 760 maxW + ls 0.005em 叠加 = 内容稀，移动端尤甚。"不可改"是口号 | 改 1.75；italic 高亮短语局部 2.0；`/dev/type` 加 4 栏对比 | 🟡 可机检 |
| 4 | display clamp(48, 9vw, 112) | 1440 屏实际 **112px**（撞 max）。clamp 中段在 1280-1920 永远撞 max = 形式响应式 / 实际两段死值。112 是 Netflix billboard 上限，不是 Apple TV+ / Letterboxd 的中段 | max 改 88-96；或 `clamp(48, 12vw, 96)` 让中段真正生效 | ✅ 客观 |
| 5 | caps 0.2em | **偏宽**。Apple/Stripe/Linear 同类 UI caps 0.06-0.1em；0.15-0.25em 是电影海报装饰区。caps 在 InkWild 是 UI 标签（模式徽章/章节号），功能错位 | caps 0.12em；micro 0.1em；装饰场景另起 `.lv-display-caps` token | ✅ 对比可量化 |

---

## 优先级

| 项 | 优先级 | 验证成本 |
|---|---|---|
| #3 行高 1.85 → 1.75 | **P0** | `/dev/type` 4 栏对比，1h |
| #4 display max 112 → 88-96 | **P0** | landing 截图 3 档对比，30min |
| #5 caps 0.2em → 0.12em | **P1** | PosterCard / 模式徽章 / play 角色名三处对比 |
| #1 narrative 挪出字号阶梯 | **P1** | 文档语义重构，留 v2.3 |
| #2 sans 论据修正 + 声音分层评估 | **P2** | 不再翻案，补充论据档案 |

---

## 落地路径

1. frontend-design skill 出 #3 + #4 demo（同一个 dev 路由，2 小时内）
2. 桌面 + 375 双视图人眼对比，决策记录写进 `play-mode-spec.md` §8
3. 落 token + ESLint，bump v2.3
4. #1 / #5 排进 v2.3 文档重构 PR
5. #2 仅修文档论据，不改字体

---

> 维护人：jie / Claude Code
> 总条目：5 条 typography 微决策
> 与主审查 `audit-2026-05.md` 关系：补充而非取代；主审 P0-1 (sans/serif) 已封，本附录 #2 仅修论据
