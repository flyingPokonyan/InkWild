# OpenClaw 启动 Prompt — 2026-05 VPS Eval

> 这是你（OpenClaw, GPT-5.5）在 VPS 上启动时收到的指令。复制粘贴整段。

---

你的任务：执行 InkWild 2026-05 VPS 自动化评测实验。

**重要心态**：这是一个**长期、按计划推进**的活动，**没有 deadline**。每个阶段做扎实再进下一阶段，发现问题就停下来回报，不要赶。Quality > speed。

## 必读

1. `CLAUDE.md` — 项目规范
2. `docs/experiments/2026-05-vps-eval.md` — 本次实验的圣经（所有 invariant + schema）

其他文档（系统架构 / 各 agent / SSE 协议 / 创作工坊）按你需要去 `docs/ARCHITECTURE.md` 和 `docs/modules/` 自取，不强制清单。

## 三阶段执行，每阶段间停下来等用户确认

### 阶段 1：写 plan

读完文档后，写 `experiments/2026-05-vps-eval/plan.md`，告诉用户你打算怎么实施——核心讲清楚：你对实验的理解 / player & judge & runner 怎么实现 / 批次和并发怎么划 / 成本估算 / 续跑机制 / 主要风险。格式和详尽度你自己判断，但要让用户看完就能拍板。

写完停下来，等用户 review。通过再进阶段 2。

### 阶段 2：Smoke test（5 个世界）

按 plan 跑前 5 个世界（4 source layer 各 1-2 个）走完完整流程：生成 → Tier1 → 至少 1 个 archetype/model/seed 游玩 → Tier2 + tag。

**Tier 1 不及格的不要直接淘汰**，先让用户看一眼校准 rubric 阈值。

跑完写 `smoke-report.md`：5 世界产物 / 分数 + judge reasoning / tag 列表 / 你观察到的 bug / 你建议的调整。

停下来等用户 review。通过再进阶段 3。

### 阶段 3：Full run

按 brief §8 参数全量执行。

- 每 50 session 写一次 `progress.md`（追加，不覆盖）
- hard kill 触发 / cost 超 $2500 / 任何 invariant 冲突 → **立刻停下来发 push 通知 + 写 alert.md**
- **持续运行期**：daily cron pg_dump + 关键节点异地备份（详见 brief §9）
- **全部完成后**的收尾流程：
  1. 全量 pg_dump + 哈希校验
  2. 数据落地 user 本地 / S3 + 收据校验
  3. 准备 30 局 review 包
  4. 写 final.md

## Invariants（破一条全部数据作废，详见 brief §7）

1. Player agent 只读 narrator 输出 + 自己历史 action，**禁止访问 game_state**
2. Judge ≠ Player ≠ 被评 agent 主力（防同源共谋）
3. 数据 schema 跑中**不准改**，新增字段必须先问用户
4. 失败 session 必须落库（崩 / 超时 / 审核 / hard_kill 都要记录）
5. Daily 全量备份 + 关键节点（生成完成 / Tier1 完成 / 游玩完成）强制 pg_dump + 异地存档 + 哈希校验

## 你被允许 deviate 的事

- 实现细节（语言 / 库 / 并发模型 / 文件组织）—— 你随便
- 批次大小 / 并发数 —— 你判断
- judge prompt 的具体措辞 —— 你写，但 rubric 维度 + 0-5 锚点必须严格按 brief §5
- 报告格式 —— 你定，但必须包含 brief §12 要求的字段

## 你不被允许 deviate 的事

- Brief §7 的 5 条 invariants
- Brief §6 的数据 schema 字段名 / 取值集
- Brief §5.3 的综合分公式 / 权重
- Brief §3 的 4 层来源分布

## 启动前用户会告诉你的事

- LLM provider API keys 在哪个 env / secret manager
- 数据回传通道（S3 bucket name + 凭证 / 或本地 rsync target）
- 你的活动 push 通知该发去哪（webhook / email）

如果上面任何一项缺失，**先停下来问用户**，不要假设。

---

Go. 开始读文档。
