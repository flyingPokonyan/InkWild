# 思考态实时反馈 — 探索交接文档

> 状态:**探索阶段,方向未定**。本文沉淀事实基础 + 已探索方案的批评 + 开放问题,供接手者独立分析,不预设结论。
> 日期:2026-06-12 · 背景会话:TTFT/缓存/parse 优化收尾后

---

## 0. 一句话

玩家提交动作后,要等 **~20s** 才看到第一句叙事(TTFT)。这 20s 目前是个"黑盒"——只有几个离散文字里程碑。问题不是"20s 太长"(已论证压不动,见 §2),而是"这 20s 该不该、能不能变成有价值的反馈"。**这个问题的答案是产品判断,尚未拍板。**

---

## 1. 为什么会有这 20s(TTFT 构成)

关键路径(实测 stage.timing,红楼梦 60 轮基线 `hlm-free-20260612T064050Z`):

```
玩家提交 → moderation(关键词,<0.5s) → world_tick(~1s)
  → director 流式解码到 scene_direction:  ~11s   ← 第一大块
  → narrator 起笔(等 NPC block 5-11s + 首句解码): ~9s   ← 第二大块
  → 首字出现 = TTFT ~20-23s(稳态)
```

- director / narrator 都跑 **deepseek-v4-pro**,串行 decode 是地板。
- TTFT 稳态 R1-30 17.3s → R31-60 23.5s(context 累积);全程 p50 ~21s。

## 2. 为什么不走"压 TTFT"(已逐一排除)

| 路 | 结论 |
|---|---|
| 换 provider(切官方 DeepSeek) | ❌ 证伪。裸探测 OpenCode 网关首 token 仅 0.82s,真实 20s 全是 context prefill + decode 地板,与网关无关;官方账户还欠费(402)。 |
| director 切 flash | ❌ 决策大脑,结局判定(历史痛点)/NPC 调度/节奏质量风险大,不切。 |
| narrator 切 flash | ❌ 文学质量,刚优化的文风/voice 会倒退,不切。 |
| narrator 不等 NPC、纯环境开场 | ❌ **产品已否**:之前就因"环境描写很一般"去掉过纯环境开场。 |
| director 输出再瘦身(C-3) | 🟡 只能再抠几秒,收益递减。 |

**结论:不牺牲质量的前提下,TTFT ~20s 基本是物理地板。** 故转向"感知等待"。

## 3. 参照系:Claude Code / Codex 为什么不让人觉得在等

它们任务常跑几十秒~几分钟,比 20s 长得多,但不让人焦躁——因为**全程把过程实时流出来**(读文件、调工具、思考 token 滚动、逐行写代码)。等待 = 看它干活。核心:**真实延迟 vs 感知延迟**。它们展示的是**真有信息增量、且和最终结果强相关**的过程,不是装饰性进度条。

## 4. 现状:InkWild 已有的思考态反馈(别当成零起点)

- 后端 emit `processing` 事件,带 `stage`:`casting / received / reasoning(带玩家动作摘要) / npcsEntering(带真实 NPC 名) / writing`。
- 前端 `frontend/lib/processing-label.ts` 的 `resolveProcessingLabel` 映射成单行文字标签。
- `backend/engine/processing_hint.py` 已有 `build_processing_hint` / `build_phase_hint` / **`build_per_npc_focus_hint`(把 director 的 per_npc_focus 做成"黛玉思考如何回应…"的有信息提示,但主流程当前没调用它)**。

**痛点(用户原话):"仅有的几个提示,感觉没反馈"** —— 是 4-5 个离散文字标签 + 标签之间大段静止,对比 Claude Code 的连续流式,是"提示几下就不动了"。

## 5. ★ 能拿到什么 — 全信号清单(接手分析的硬基础)

那 20s 引擎实际产生、内存里已有的数据(`backend/engine/orchestrator.py:_on_partial_director` 行 1307 起 + world_tick 行 471):

| 时段 | 信号 | 数据形态 | 现状 | 剧透风险 |
|---|---|---|---|---|
| 0-1s | **world_tick** | `world_events[{event_type, description}]` + `current_time` 时辰推进 | 内存有,**未 emit** | 低(环境氛围) |
| ~9s | active_npcs | `[name]` | ✅ 已 emit(npcsEntering) | 无 |
| ~9s | **per_npc_focus** | `{npc: "在场感受到的客观刺激"}` | 内存有,**未 emit**(helper 现成) | 低-中(NPC 视角,需轻过滤) |
| ~9s | **dramatic_intensity** | `low/medium/high/climax` | 内存有,**未 emit** | **无(纯张力元信息)** |
| ~9s | scene_role | `{npc: primary/secondary}` | 内存有,未 emit | 无 |
| ~9s | scene_brief | 逐字文本(本回合客观发生) | 内存有 | **高(剧透本回合事件)** |
| ~11s | scene_direction | 逐字文本(给 narrator 指引) | 部分,触发 writing | 高 |
| 9-20s | NPC 并行 | 每个 `NPCAction{action_type, dialogue, physical, tone}` + 完成顺序 | 内部 | dialogue 高 / 完成态低 |
| 18s→ | narrator 正文 | `text_delta` 流式 | ✅ 已流式 | — (正文) |

**剧透边界**:
- ✅ 直接可展示:`active_npcs`、`dramatic_intensity`、`current_time`、`scene_role`、NPC 完成态
- 🟡 轻过滤可展示:`per_npc_focus`(NPC 感受,比结果安全,但可能带本回合事件)、`world_events`(环境类可、剧情类不可)
- ❌ 绝不提前:`scene_brief`、`scene_direction`、NPC `dialogue`、`ending_triggered`、`new_clues`

原则:展示"谁在场 / 什么氛围 / 各自在留意什么 / 世界在怎么动"(过程·状态·张力),不展示"发生了什么 / 谁说了什么 / 答案"(结果)。

> 注:线索侧边栏/案件板当前全模式关闭(`frontend/app/play/[id]/page.tsx` `PLAY_SIDE_PANEL_ENABLED=false`),线索系统产品上已放弃,**不要往这个方向设计反馈**。

## 6. 已探索的方案 + 为什么它不够好(避免重蹈覆辙)

探索过一套"四幕幕后"设计:world_tick 氛围条 → 在场角色头像逐个亮 + dramatic_intensity 氛围层 → per_npc_focus 思考气泡 + NPC 逐个就绪 → narrator 正文。

**自我批评(用户当场否掉,判断成立)**:
- 本质是给现有 `processing` 里程碑**套视觉糖**(头像/气泡/氛围层),信息内核没变 = "换皮"。
- "头像逐个亮"这类**加载装饰会腻**——形式仪式化,看三次就是另一种等待。
- 展示内容(per_npc_focus 等)作为"等待预告"**价值存疑**:和马上到来的正文重叠则冗余,不重叠则可能无关,形式每回合一个样。
- **堆信息 ≠ 有价值;半吊子的信息展示比克制留白更廉价。**

教训:能"不腻"的只有两类——要么**真有持续信息增量**(像 Claude Code,但 InkWild 这 20s 的预告达不到那个强度),要么**克制到不打扰**(高级留白)。卡在中间的"信息仪表盘"是最差位置。

## 7. 三种哲学取向(待拍板)

| 取向 | 做法 | 投入 | 风险/判断 |
|---|---|---|---|
| **A. 克制留白** | 承认填不出高价值内容,做安静、高级、有呼吸感的极简态(可留一句会变的氛围/张力暗示),不堆信息、不打扰 | 小 | 不会腻(不假装有信息);最契合 cinematic/高级定位。本文作者倾向此或 C。 |
| **B. 电影运镜过场** | 把这段叙事化成镜头语言(场景游走→掠过在场人物→定格起笔),用真实信号(在场/张力/per_npc_focus)当镜头内容,是叙事节奏不是加载态 | 大(后端补 emit + 前端动效) | 执行好则惊艳、不好仍会腻;ROI 不确定。唯一可能"不腻又有内容"的路,但重。 |
| **C. 先不动,投别处** | 现有里程碑够用,精力放叙事质量/内容/玩法 | 0 | 这 20s 对留存的杠杆,可能远小于内容本身。 |

## 8. 开放问题(给接手者)

1. 这 20s 到底有没有玩家"愿意反复看、且有增量"的内容?如果没有,A 或 C 比 B 诚实。
2. 若做 B,如何让"运镜"每回合不雷同到腻?per_npc_focus / dramatic_intensity 的变化够不够撑起镜头差异?
3. dramatic_intensity 驱动氛围层(色调/张力)——这是 InkWild 多 agent 独有、单模型产品给不了的素材,值不值得单独做(即使其余克制)?
4. 衡量标准是什么?(感知等待的主观测试?留存?还是只是"不掉档次")

## 9. 关键代码位置

- `backend/engine/orchestrator.py:1307` `_on_partial_director` — director 流式各字段到达点(active_npcs/per_npc_focus/scene_direction…),emit `processing` 进度的源头
- `backend/engine/orchestrator.py:~471` world_tick(TickResult.world_events / current_time)
- `backend/engine/processing_hint.py` — 现有 hint 构造(含未接线的 `build_per_npc_focus_hint`)
- `frontend/lib/processing-label.ts` — 前端里程碑→文案映射
- `frontend/app/play/[id]/page.tsx` — play 页;`PLAY_SIDE_PANEL_ENABLED=false`
- TTFT/延迟全量数据 + 优化史:`docs/operations/latency-ttft.md`
