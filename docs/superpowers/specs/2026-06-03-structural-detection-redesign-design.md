# 结构演化：从"判玩家主张"改为"认世界记录"（A-route 后置检测器）—— 设计 spec

状态：设计已拍板（2026-06-03），转实现计划
关系：**修订** [`2026-06-03-structural-evolution-pipeline-design.md`](2026-06-03-structural-evolution-pipeline-design.md) 的**自由模式那一半**。剧本模式（作者里程碑 / S3）不变。本 spec 取代该文档里"自由模式 LLM 仲裁判官（S4）"的设计。
一句话：**玩家永远不是世界改变的作者，世界才是。结构变更只从"世界本回合的真实产出（NPC 行动 + 旁白）"中检测并提交，绝不从玩家的主张中提交。**

---

## 0. 为什么推翻 S4 判官

已落地的 S1–S4 里，自由模式靠一个判官判"玩家声称的结构变更合不合理"。真跑发现："我通过宣旨当了皇上（实际没宣）"这类**伪造因由**攻击，要靠不断给判官喂上下文去识破——这是补补丁的军备竞赛，因为**问错了问题**：判"玩家的话可不可信"天生可被更狡猾的话绕过。

正解是换问题：**不判玩家的话，认世界的记录。** 一条结构变更能提交，当且仅当**世界本回合的真实产出里，世界自己（NPC/旁白）真的把它演了出来**。玩家撒谎时，世界（按哲学 A，NPC 按性格）根本不会替他演那道旨 → 记录里空 → 不提交。撒谎这条攻击面被**结构性消除**，不靠判官越来越聪明。

---

## 1. 核心原则（已拍板）

1. **哲学 A 贯彻到底**：世界底色只通过世界自身逻辑改变。玩家打的字永远只是**尝试**，世界对它反应；玩家的主张**本身从不构成提交依据**。
2. **认世界记录，不认任何人的"打算"**：提交只从"已记录的世界产出"中检测——不是玩家的主张，也不是导演的"提议/打算"。
3. **检测器只忠实读取，不重新判合法**：把"这事合不合法/该不该发生"留在 NPC/旁白裁定玩家动作那一层（模型 + prompt 能力，已被现有评测背书）。检测器只回答"世界这回合到底有没有真的发生结构变更"。**绝不在检测器里塞 plausibility 判断**（那等于把删掉的判官又请回来）。
4. **通用性铁律不变**：零题材专属逻辑；`kind` 仍是机械后果枚举；测试横跨 ≥3 题材。
5. **默认休眠 + rare-fire**：绝大多数回合不触发检测器。

---

## 2. 合法性底线（明确写清，避免误解）

A-route 把"强行动作合不合法"的底线**落在 NPC/导演/旁白对玩家动作的忠实裁定上**：
- **动嘴类**（"我是皇后""我奉旨继位"）：NPC 按性格自然驳斥，世界不演 → 检测器读不到 enact → 不提交。**撒谎天然落空。**
- **动手类**（"我捅死华妃"）：能不能成，由**世界裁定**——有 NPC 在场就由 NPC 反应（守卫拦、目标躲）；物理离谱的壮举由导演/旁白 pushback。检测器只读裁定结果。
- 这层是模型 + prompt 能力，现有评测（NPC 按性格反应、IP 忠诚）已背书"够用"。**若将来发现最薄的点（离谱壮举且无人阻拦）不达标 → 强化 NPC/旁白裁定那一层，不动检测器。**

---

## 3. 架构

### 3.1 导演：降级为轻提示 + 保留反应铺设
- **删**：导演 `structural_change_proposed` 里的 `supported` / `in_world_cause` / `justification` / `world_reaction` 这套**判断**字段。
- **保留（关键，别删骨气）**：玩家做结构断言时，导演照旧把"玩家当众如此声称"作为**客观刺激**写进 `per_npc_focus` / `scene_brief`，让 NPC 按性格自然反应（驳斥/惊疑/上报）。这套 S2 反应机制不变。
- **新增**：导演输出一个**廉价布尔提示** `structural_in_play: bool`——"本回合是否触及世界底色（有结构变更被尝试或可能被世界 enact）"。仅作 rare-fire 闸门。可附一个极简 hint（涉及哪个实体 / 大概什么 kind）帮检测器聚焦，但不做判断。

### 3.2 后置结构检测器（自由模式 only）
- 新增 `engine/structural_detector.py`，cheap-LLM，照搬 `stance_inference` / S4 的模式（`stream_json` + parse-or-safe-default）。
- **触发**：仅当 `game_mode == "free"` 且本回合 `structural_in_play == true` 且 flag 开。
- **位置**：回合末（orchestrator 现有 structural 观测点，~1840 行），此时 **NPC 的真实产出（`npc_actions`）+ 旁白已就绪**。
- **输入**：本回合 NPC 实际行动（`npc_actions` 的 dialogue/physical，比散文明确）+ 旁白文本 +（可选）导演 hint。**不把玩家的主张当作权威证据**——玩家输入只作背景，真凭据是世界产出。
- **输出**：`{changed: bool, fact_key, fact_text, kind, target_ref}`，`changed=false` 时其余空。解析失败 / 模糊 → `changed=false`（保守，宁漏不造）。
- **提交**：`changed=true` → `commit_structural_fact(game_state, {..., provenance="free_detector"})`，走已就绪的 S3 账本 + 一阶级联；下回合经 `apply_structural_overlay` 进脊柱。

### 3.3 剧本模式：不变
作者结构里程碑（world_state 条件，确定性，S3）保留。**检测器不在剧本模式跑**（避免提交作者没批准的变更，保 authored 弧 / IP 安全）。

### 3.4 删除 S4 判官
`engine/structural_arbiter.py` + orchestrator 里的判官调用 + config flag 语义改为"检测器开关"（见 §6）。

---

## 4. 数据流（自由模式单回合）

1. world tick → `apply_structural_overlay`（脊柱叠上**已有**账本，S3 不变）。
2. 导演：正常排场 + 把结构断言作为客观刺激给 NPC（S2 反应铺设）+ 输出 `structural_in_play`。
3. NPC 按性格行动（驳斥假断言 / 或当火候到时真 enact 变更）；旁白织成叙事，**流给玩家**。
4. 回合末：若 free + `structural_in_play` + flag → 跑检测器读 `npc_actions` + 旁白 → `changed?` → 是则 `commit_structural_fact(provenance="free_detector")`。
5. 状态持久化（含新账本）。下回合 overlay 带上它。

> 同回合可见性：变更在第 N 回合的**叙事里已经发生**（玩家看得到），脊柱从 N+1 回合起结构性记住——与 S3 行为一致。

---

## 5. 边界与失败模式（已 review）

- **漏判（under-commit）**：旁白模糊 → 检测器保守不提交。失败方向安全（漏掉可再推，不凭空造）。缓解：喂结构化 `npc_actions` 而非只喂散文。
- **要求 enact 瞬间**："挣够了但世界从没真演出来"不提交——这是**对的**（哲学 A 要世界真做出动作）。连带要求：导演（S1 steering）在火候到时**真把那一幕摆出来**，检测器才抓得到。
- **离谱强行壮举**：底线在 NPC/旁白裁定（§2），不在检测器。
- **检测器调用失败/超时** → `changed=false`（绝不误提交）。
- **幂等**：`commit_structural_fact` 已按 `fact_key`+`fact_text` 去重（S3 既有）。

---

## 6. 从现有 S1–S4 迁移（要改/删什么）

| 项 | 处置 |
|---|---|
| `DirectorResult.structural_change_proposed` | 瘦身：保留为轻提示载体或换成 `structural_in_play: bool`（实现计划定）；删 supported/cause/justification/world_reaction 的**判断**语义 |
| 导演 prompt 的结构规则块（S2） | 保留"把断言作为客观刺激给 NPC 反应"；删"判 supported / 填 world_reaction"那部分；加"输出 structural_in_play" |
| `engine/structural_arbiter.py`（S4） | **删除**（含其测试） |
| orchestrator ~1840 判官+提交块 | 改为"free + structural_in_play + flag → 检测器 → 提交" |
| config flag | `structural_free_arbiter_enabled` → 改名/复用为检测器开关（dev/eval 旋钮，默认 on） |
| `engine/structural_ledger.py`（S3） | **不动**（commit + overlay + cascade 已验证） |
| 剧本里程碑 `_process_structural_milestones`（S3） | **不动** |
| `engine/structural_detector.py` | **新增** |

> 诚实代价：S4 判官（已建+验证）被删。其价值是验证了撒谎问题、喂出了这个更干净的设计。

---

## 7. 测试策略（轻量 + 通用性 + 真机）

- **单元**：检测器 `parse`（changed / not-changed / garbage→保守 false）；"玩家撒谎、NPC 产出里无 enact → changed=false"（喂构造的 npc_actions）；"NPC 真 enact → changed=true 抽出正确 fact/kind/target"。横跨 ≥3 题材。
- **真机**（verify 同前）：自由模式两局——①玩家凭空/伪造因由声称 → NPC 驳 → 检测器读产出 → 不提交；②玩家通过真行动促成、世界（NPC）真 enact → 检测器读产出 → 提交、下回合进脊柱。
- 剧本里程碑回归（S3 不动，跑一遍确认没碰坏）。

---

## 8. 非目标

- ❌ 检测器做 plausibility / 合法性判断（那是 NPC/旁白裁定层的事）。
- ❌ 全量 N 阶级联（仍一阶，S3 不变）。
- ❌ 题材专属分支。
- ❌ 检测器在剧本模式跑。
- ❌ 常态回合跑检测器（rare-fire）。

---

## 9. 留给实现计划

- `structural_in_play` 的具体字段形态 + 导演 prompt 增改文案。
- 检测器 prompt（题材中立，"只读世界产出、判有没有真 enact"）+ cheap slot 绑定（复用 npc_agent 槽，走 LLMRouter）。
- orchestrator ~1840 块的替换 + 拿到 `npc_actions`/旁白文本喂检测器。
- S4 判官删除 + flag 改名 + 相关测试清理。
- S1/S2/S3 哪些 prompt 行保留/删除的精确 diff。
