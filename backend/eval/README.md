# InkWild 评分机制（Scorer）

**定位**：这是一套**稳健、可复用的评分机制**。它不关心你怎么产生对话——
你给它 `session_id` + 选一个 rubric（镜头），它吐**结构化分数 + flag**。

「跑播放 / 选世界 / 决定比什么」每次需求都不同 → 那是一次性胶水，由 hermes 按需写
（`eval/examples/` 有模板可抄）。**本目录只维护 Scorer。**

## 契约（hermes ↔ Scorer）

```
hermes：用任意方式产生 game_session（跑新局 / 复用旧局）→ 拿到 session_id
        → 按 condition 编组，调 Scorer
Scorer：session_id → 抓痕 → 硬检 → 判分 → 聚合 → 报告（含 A/B diff）
```

一条命令：
```bash
python -m eval.run \
  --rubric npc \
  --group "条件A=<sid>,<sid>" \
  --group "条件B=<sid>,<sid>" \
  --out eval/runs/xxx.md
```
condition 可以是任何东西：voice 开/关、剧本 A/B、模型 X/Y、prompt v1/v2。
`--group` 可给多个；两个时报告自动出逐维 Δ。

**A/B 相对评测（pairwise，破绝对分饱和——优先用这个比 A/B）**：
```bash
python -m eval.run --pairwise \
  --rubric npc_pairwise \
  --group "no_voice=<sid>" --group "voice=<sid>" \
  --judge-slot <slotA> --judge-slot <slotB> \   # 多判官 → 跨家族胜率面板
  --out eval/runs/xxx.md
```
- 恰好 2 个 `--group`、各 1 个 session；同回合对齐（取两边都有 NPC 台词的共同 turn）+ 随机左右匿名盲判。
- 判官**必须强 + 与被测异源**（同源共享盲区、分辨力打折——实测 deepseek-pro 判 deepseek 只 4/7，4 独立家族面板 5-6/7）。`--judge-slot` 可多次 = 多判官胜率面板。

## 核心文件（维护这些）

| 文件 | 职责 |
|---|---|
| `capture.py` | session_id → 标准记录 `{turns:[{player_action, narrative, npc_dialogues, state_snapshot}]}`（输入契约）|
| `judge.py` | 拿 rubric 逐回合判（map）→ 均值聚合（reduce）。判官走强 slot（默认 admin_generation=v4-pro）|
| `judge_pairwise.py` | **A/B 相对评测**（破绝对分饱和）：回合对齐 + 盲随机左右 + 多判官胜率聚合。`--pairwise` 走它，纯函数有单测 |
| `rubrics/*.md` | **镜头 = 真正的智力资产**。加维度 = 加一个 `.md`，不改代码 |
| `hardchecks.py` | 确定性红旗（**非 LLM**）：秘密泄漏/破第四面墙/空回合/近重复 |
| `report.py` | 聚合 + baseline diff + worst-N |
| `run.py` | 入口：分组 session → 评分 → 报告 |

`examples/`（**不维护**，模板）：`driver.py`(LLM玩家跑新局) / `scenarios.py`(冻结集) / `baseline.py`(体检)。

## 加一个新镜头
往 `rubrics/` 丢个 `<name>.md`（照 `director.md` 的结构：维度表 + JSON 输出格式 + 评分纪律），
然后 `--rubric <name>`。引擎不用动。

## ⚠ 已知校准 TODO（影响"稳健"）
- ~~**NPC 镜头会饱和**（绝对分全打 4.8-5.0）~~ **已治（2026-06-01）**：① `npc.md` 收紧 anchor（及格线=3 / 对调测试 / 取证）把绝对分从 4.8-5.0 拉散到 3.6-4.6；② 新增 **pairwise（`--pairwise` + `npc_pairwise.md`）**——A/B 相对比较在强异源判官间稳健可复现（4 家族验证一致）。**比 A/B 优先用 pairwise**；绝对分仍有压缩。
- **判官绝对分别迷信**：信同一冻结集上的 **Δ** 和 **flag**，不信绝对值。
- **判官要拿人眼校准**：小批样本你先打，再看判官打的，对得上才可信。

见 spec：`docs/superpowers/specs/2026-06-01-eval-harness-design.md`
