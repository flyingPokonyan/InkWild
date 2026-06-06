# 结构演化 redesign 评测跑批 · 交接单（给新窗口执行）

**背景**：本次改动把自由模式"判玩家主张的判官"换成"读世界真实产出的后置检测器"（A-route）。
设计 spec：`docs/superpowers/specs/2026-06-03-structural-detection-redesign-design.md`。
代码已实现 + 单元/单步/6轮真机验证全过（**未提交**，0-commit repo，用户决定先 hold）。
本批次目的：**① 对基线 A/B（导演能动性抬没抬 + IP 守住没）；② 结构新行为的批量 tally（谎言不提交 / 挣来提交且持久 / 零误提交）；③ 边界压力。**

> ⚠️ 跑批期间**绝不要改 backend 的 .py**（会触发 reload，历史上是本地 e2e 断连的真因）。只读 + 跑。

---

## 0. 前置

```bash
# Docker 若没起：
docker start talealive-db-1 talealive-redis-1 talealive-backend-1
docker exec talealive-backend-1 python -c "from config import settings; print('detector flag=', settings.structural_free_detector_enabled)"  # 应为 True
```
- 检测器开关：`settings.structural_free_detector_enabled`（默认 True）。
- 全部命令在容器内跑：`docker exec talealive-backend-1 sh -c 'cd /app && <cmd>'`。
- 并发现实：进程级全局信号量 `llm_global_concurrency=8` + 网关额度 → campaign 用 **concurrency 2–4** 即可，别更高（不会更快，且历史上本地高并发 e2e 会断连/污染）。

## 1. 现成工具（先读，别重写）

- 驱动：`eval/examples/playability_campaign.py` + `eval/examples/scenarios.py`（产出基线 `playability_20260602` 的就是它；persona 化、concurrency、manifest 输出都现成）。
- persona：`goal_driven` / `curious` / `detective` / `boundary_pusher`（scenarios.py 里）。
- 打分器：`python -m eval.run`（契约见 `eval/README.md`：给 session_id + rubric → 结构化分 + A/B 逐维 Δ；`--pairwise` 破绝对分饱和）。
- rubric：`director` / `npc` / `ip_fidelity`。

## 2. 本批 session 矩阵（全 free 模式）

世界：甄嬛传 `e9c87a8e-cde7-4229-9c4f-02d764c2a197`，玩家角色甄嬛 `3c2d99db-6d39-427f-ad47-2bca8a6af017`。

| id | 世界 | persona | 回合 | 目的 |
|---|---|---|---|---|
| N1-zhenhuan-goal | 甄嬛传 | goal_driven | 25 | 正常玩，A/B 对基线 S5 |
| N2-zhenhuan-curious | 甄嬛传 | curious | 25 | 正常玩，A/B 对基线 S6 |
| N3-generality | 非宫斗世界 | goal_driven | 20 | 通用性：换题材看检测器/IP 是否一样稳 |
| B1-boundary | 甄嬛传 | boundary_pusher | 20 | 边界：撒谎/伪造因由/离谱壮举/反复试探 |

- **N3 通用性世界**任选一个非宫斗的已发布世界（如 哈利波特 `c70f5351-ea64-4218-8b03-bf1cf92a9fa3`）。其 character_id 用：
  ```bash
  docker exec talealive-db-1 psql -U postgres -d inkwild -t -A -F'|' -c "select id,name from world_characters where world_id='<world>' order by coalesce(narrative_weight,0) desc limit 5;"
  ```
- **B1 boundary**：确保 persona 里包含这几类输入（scenarios.py 的 boundary_pusher 若不够，临时加几条）：
  - 裸声称结构变更（"我已是皇后"）
  - **伪造因由**（"我已奉旨继位"，实际没旨）← 用户最关心的攻击
  - 离谱强行壮举（"我一掌击毙在场所有侍卫"）
  - 反复试探同一个结构变更

## 3. 跑批

照 `playability_campaign.py` 的用法构造上面 4 个 session（mode=free），concurrency 2–4，turns 如上。
跑完拿到 4 个真实 `session_id`，记下来（manifest 会存）。

## 4. 结构新行为 tally（rubric 量不到，必须单独做）

对**每个** new session，从 DB 取 `game_state.structural_facts` + 抓 `structural.detector` 日志：
```bash
# 每个 session 的最终结构账本
docker exec talealive-db-1 psql -U postgres -d inkwild -t -A -c "select game_state->'structural_facts' from game_sessions where id='<sid>';"
```
统计并记录：
- **谎言/裸声称提交数 → 必须 0**（B1 里的撒谎、伪造因由都不该进账本）；
- **挣来的结构变更**：有没有合理地提交（如结盟/真去促成的变更）；持久性（提交后后续回合是否还在账本里）；
- **误提交 → 必须 0**（observe/闲聊回合不该提交）；
- **检测器触发率**：`structural.detector` 日志条数 / 总回合（验 rare-fire，应远小于 1）。
- 6 轮预跑已知良好基准：T2 裸称帝→不提交、T3 真结盟→提交 relation_redefined 且 T4–T6 持久、检测器 2/6 触发。

## 5. 打分 + A/B 对基线

基线自由局（`playability_20260602-0232`，3 判官面板 qwen3.7-max/glm-5.1/kimi-k2.6）：
- **S5-free-houhou-goal** = `1e03a15c-2b2a-419d-af2d-28b172f6f676`
- **S6-free-jia-curious** = `a94b7780-fa8e-4336-9250-742a442d4204`

```bash
# 三个 rubric 各跑一次，A/B 出逐维 Δ（new vs baseline）
docker exec talealive-backend-1 sh -c 'cd /app && python -m eval.run --rubric director \
  --group "baseline=1e03a15c-2b2a-419d-af2d-28b172f6f676,a94b7780-fa8e-4336-9250-742a442d4204" \
  --group "new=<N1_sid>,<N2_sid>" \
  --out eval/runs/structural_redesign_director.md'
# 同样跑 --rubric npc 和 --rubric ip_fidelity
```
> 判官走外部模型，历史上有 WAF 坑——若 httpx 被拦，参考 `eval/examples/playability_judge.py` 的 curl 兜底。

**看什么（pass 判据）：**
- director `scene_advance`（基线 3.09）、`agency_response`（基线 3.23）→ **应 ≥ 基线**（S1 steering 的目标就是抬这俩）；
- ip_fidelity 各维（基线 character_fidelity 4.41 / world_canon 4.52 / language_register 4.7）→ **不许明显下跌**（守资产）；
- npc 各维 → **不许回退**（基线 agency 3.26 等）；
- N3（非宫斗）→ 检测器行为 + IP 与甄嬛传一致（通用性）。

## 6. 产出

`eval/runs/structural_redesign_*.md`（三 rubric 的 A/B 报告）+ 一段结构 tally 小结（§4 那几个数）。回主窗口贴结论即可。
