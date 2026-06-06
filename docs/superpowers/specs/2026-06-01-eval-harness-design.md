# InkWild 评测 Harness 设计

状态：设计（2026-06-01），待 review → 实现
作者上下文：源于"我不知道现在质量到底怎样"——临时跑播放 + 人肉读转录，差强人意。根因是四缺失：①没 rubric（评判维度）②没冻结评测集 ③判官是人（主观/不 scale）④没 baseline 对比。本 harness 把这四样补齐，让"质量"从"读完觉得一般"变成**会动的数字 + flag 出来的烂片段告诉你为什么烂**。bug、导演质量、NPC 质量、优化方向——同一套跑出来。

## 核心架构：引擎（代码）+ 判断（可换镜头 rubric）分层

两种活按性质分开，不是二选一：

- **引擎 = 代码**（repo 内，VPS `git pull` 跑，可 cron）：跑播放 / 抓痕 / 硬故障检测 / 调判官 / 聚合 / 出报告。确定性、可复现、便宜可靠。
- **判断 = rubric（markdown，可换镜头）**：定义"好导演=哪几维、1分vs5分长啥样、flag 什么"。是判官的脑子，也是"我们对质量的定义"文档。

**通用性放在 rubric 层**：改评判标准 = 改 markdown，不动引擎。
**聚焦单维度 = 换镜头**：这次 `--rubric director` 只判导演；下次 `--rubric npc`，引擎同一套。直接解决"LLM 上下文有限、一次只想攻一个维度"。

## 目录结构

```
eval/                          代码引擎（通用，git 管理）
  run.py            CLI 入口: --scenarios <set> --rubric <name> --granularity turn|session --repeats K --out <dir>
  driver.py         驱动播放（复用 zh_play.py / auto_play.py 的 SSE 逻辑）
  capture.py        抓痕：SSE 转录 + 跑完从 DB 拉结构化数据
  hardchecks.py     规则故障检测（确定性）
  judge.py          调强模型判官，喂 rubric + 转录切片，收结构化 JSON 分
  aggregate.py      聚合 + worst-N + 对比上版趋势
  report.py         出 jsonl（累积趋势）+ md/HTML（人读）
  personas/         模拟玩家人格（system prompt 文件）
    curious.md  aggressive.md  lazy.md  boundary_pusher.md  goal_driven.md
  scenarios/        冻结评测集（世界×模式×玩家人格）
    core.yaml
  rubrics/          判断层（可换镜头）
    director.md     ← 首张，本 spec 给出草案
    npc.md  narrator.md  system.md   ← 后续
  runs/             历次结果（jsonl + md），趋势靠这个攒
```

## 组件

### 1. 冻结评测集 `scenarios/core.yaml`
每个 case 固定不变（改了就不可比）。字段：
```yaml
- id: zhenhuan-script-huafei
  world_id: e9c87a8e-...
  mode: script
  script_id: 51855afa-...        # 华妃争锋篇
  character_id: 3c2d99db-...     # 甄嬛
  persona: curious
  turns: 8
  tags: [ip, 宫斗, 大roster]
- id: yexingguan-free-adversarial
  world_id: 783ee03a-...
  mode: free
  persona: boundary_pusher
  turns: 10
  tags: [原创, 沙盒, 边界测试]
```
种子：复用已发布世界（甄嬛传 / 夜行馆 / 记忆典当行）。覆盖：script+free、mystery+emotional、IP+原创、大/小 roster、边界 case（弱输入/挑衅/越狱）。

### 2. 模拟玩家人格 `personas/*.md`
每个是一段 system prompt，驱动"下一句玩家说什么"。最少 5 种：
- **curious**：好奇追问、探索、做选择（默认主力）
- **aggressive**：质问、对峙、施压
- **lazy**：最小输入（"嗯""看看周围"）——测引擎能不能扛住低能动输入
- **boundary_pusher**：试图越狱 / 让 NPC 破第四面墙 / 套剧透 / 元提问——测护栏 & 信息隔离
- **goal_driven**：盯着一个目标推进——测剧情是否真能被推动
（复用 auto_play 的 `simulate_player_input`，把 persona 抽成参数。）

### 3. 驱动 `driver.py`
复用 `zh_play.py` 的 `/game/start` + N 回合 SSE 逻辑。无人值守、一坏回合不杀全局。每回合：persona LLM 产玩家输入 → 发 action → 抓 SSE。

### 4. 抓痕 `capture.py`
**SSE 实时** + **跑完 DB 拉**（P0 不改后端）。已核实数据底座（2026-06-01 查证）：
- `messages.npc_dialogues`：**逐 NPC 分开存**的对话 dict（`{"浣碧":"长姐？…","崔槿汐":"…"}`）→ NPC 镜头能逐角色评（voice 区分度/信息隔离/反应性）。
- `messages.state_snapshot`：每回合一份，**含** `narrative_arc`/`rounds_in_climax`/`discovered_clues`/`info_items`/`triggered_events`/`npc_intents`/`npc_relations`/`last_active_round`/`npc_locations`/`world_conflicts` 等 → 导演**决策效果**全在状态 delta 里。
- `messages.content`：旁白成品；`token_usage`：phase/cache/cost；`case_board_history`、`memory_entries` 可拉。
- meta：scenario id、persona、槽位绑定快照、时间戳、**代码版本(git sha)**。
- 落 `runs/<ts>/<scenario>.jsonl`。（可选：判官结果/flag 写进现成的空表 `experiment_turn_tags(issues_noted)`。）

**⚠ 重要限制（red-team 查出）**：**导演的"原始决策"（scene_beat 文本、npc_instructions、为何这么判）不落库**（只在 structlog，易失）。所以判官评导演时是**从效果反推**（state delta + npc_dialogues + 旁白），而非看决策本身。对"场景推进/弧线连贯/NPC激活/信息门控/结局触发"这些**看得见效果**的维度，反推够用（P0 可行、不改后端）；对"导演当下这个判断好不好（vs 其它选项）"这种**要看决策理由**的，需要一个小后端 hook：每回合把 director 决策 JSON 落到 `experiment_turn_tags` 或 message 字段 → 列为 **P1**，非 P0 阻塞。

### 5. 硬故障检测 `hardchecks.py`（规则、确定性，独立于判官打分）
- SSE error / RemoteProtocolError / 截断（finish_reason=length）
- `llm_parse` 错误（导演/NPC JSON 解析失败）
- 延迟/成本离群（超阈值）
- 状态不变量：case_board op 引用了不存在的 clue；ending_triggered 一致性；孤儿引用
- **秘密泄漏检测**：把 `npc_dialogues` 各 NPC 台词，比对其 `world_characters.secret`，且该秘密尚未进入本回合 `state_snapshot.discovered_clues`/`info_items` → 命中即泄漏（底座已具备，可做；细腻语义版再交判官）
- 重复：相邻回合叙事近重复（ngram/embedding）

### 6. 判官 `judge.py`（LLM-as-judge）
- 输入：**一张 rubric**（单维度族）+ 转录切片
- **强模型**（必须强于被测；可配 slot；不能用被测的 flash）
- **分块 + map-reduce 解上下文限制**：
  - 细维度（导演场景推进、NPC 是否在人设）→ **逐回合**判
  - 弧线维度（结局连贯、节奏全局）→ 对"逐回合分数摘要"（非原始转录）做**局级总评**
- 输出结构化 JSON：每维 `{score:1-5, rationale:一句, evidence:片段, flag:bool}`

### 7. 聚合 + 报告 `aggregate.py` / `report.py`
- 每维均分 + 分布 + worst-N（带证据片段）
- **对比上一版**（同一冻结集 before/after）→ 回归检测
- 硬故障清单
- 输出：`runs/<ts>/report.md`（人读）+ 追加 `runs/index.jsonl`（趋势）

### 8. 降噪
LLM 有随机性：每个 scenario 跑 `--repeats K`（默认 3）取均值/中位，降低单局噪音。

## rubrics/director.md 草案（首张镜头）

> 你是资深互动叙事制作人，评 InkWild **导演 agent** 单回合/单局质量。按下列维度各打 1-5 分（1=严重失败，3=及格，5=优秀），每维给一句理由 + 一段证据片段；发现严重问题置 flag=true。只输出 JSON。

| 维度 | 1 分 | 5 分 |
|---|---|---|
| **场景推进** | 原地打转/复读 | 每回合有实质推进，钩子清楚 |
| **节奏张力** | 张力与弧线位置脱节（开局就高潮/高潮却平） | 张力贴合所处幕 |
| **NPC 激活合理性** | 该出场的没出/无关的乱入/发言顺序乱 | 激活与发言顺序都贴合情境 |
| **信息门控** | 提前抖真相 / 该给的死活不给 | 该露露该藏藏，节奏得当 |
| **弧线连贯** | 与三幕/剧本节拍矛盾、断线索 | 与 arc/剧本一致、线索接得上 |
| **能动性响应** | 无视玩家行动 / 硬轨道 | 真接住玩家这步、给有意义后果 |
| **结局触发**(script) | 早触/never/乱触 | 时机正确 |

输出：`{"per_dim":{...}, "overall":1-5, "summary":"一句", "flags":[...]}`

## VPS / cron 跑法
```bash
cd inkwild && git pull
# 对着 VPS 上跑起来的栈（或 AUTOPLAY_BACKEND_URL 指远端）
python -m eval.run --scenarios core --rubric director --repeats 3 --out runs/$(date +%F-%H%M)
```
hermes 两种用法：①直接跑 CLI（CLI 内部调判官+喂 rubric，全自动可 cron）②hermes 当判官 agent 加载 rubric（更交互、适合探索 worst-N）。结果 jsonl 累积成趋势。判官模型必须强于被测。

## 方法论注意（red-team 出来的真坑，别忽视）
- **判官本身要标定，别迷信绝对分**：LLM-as-judge 有位置偏好、啰嗦偏好、分数压缩（全打 3-4）。**最可信的是同一冻结集上的 before/after delta，不是绝对分**。所以 baseline 对比不是 nice-to-have，是核心用法。判官要用测试夹具校准（已知好/烂转录断言方向）。
- **NPC 镜头 > 导演镜头 的可判性**：npc_dialogues 逐角色存 → NPC 评得很实；导演只能反推效果（见 §4 限制）。**建议 P0 先做最实的，不一定非从导演起**——这点你定（见待定决策）。
- **评测有真实成本**：scenarios × repeats(K) × turns ×（游戏 LLM 调用 + 判官调用）。粗估 5 scenario×K3×8 回合 ≈ 15 局 ×~5min + 判官 ≈ 一次跑 1+ 小时、deepseek 侧 ~$25-30 + 判官成本。要有 budget 意识，cron 频率别太密。

## 分期
- **P0（先跑通）**：driver(复用 zh_play) + DB capture(npc_dialogues/state_snapshot) + hardchecks + judge + 一张 rubric + report + **baseline diff**（P0 就要，否则分数没意义）。一条命令对冻结甄嬛传集出一份质量报告。
- **P1**：补齐其余镜头(`npc/narrator/system/director`)；**后端小 hook：落 director 决策 JSON** 让导演镜头评"决策"而非只评"效果"；评测集扩到 3-5 世界 × 多 persona。
- **P2**：cron 自动化；HTML 看板；评测自身成本预算 guard。

## 待定决策（实现前拍）
1. **判官模型**：用哪个强模型当判官（Claude / 某强 slot），及其成本。
2. **抓痕方式**：P0 用"跑完 DB 拉"（不改后端，推荐）；将来要更细的导演决策可加后端 eval-debug 通道。
3. **评测目标**：VPS 自己起全栈 vs 打远端实例。
4. **降噪 K 值** vs 评测集大小的取舍（K 大更准但更贵）。

## 测试
- `hardchecks` 规则用构造样本单测（注入一个秘密泄漏/截断/孤儿引用，断言能抓出）。
- `judge` 用一段已知"好"和"烂"的转录夹具，断言分数方向正确（好的高分、烂的低分 + flag）。
- `aggregate/report` 用假数据断言聚合数与 worst-N 选取正确。

## 范围外
- 真人评测/众包打分（判官先用 LLM）。
- 在线 A/B（先离线冻结集回归）。
- 多语言评测（先中文）。
