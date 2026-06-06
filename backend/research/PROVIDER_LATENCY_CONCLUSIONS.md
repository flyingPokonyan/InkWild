# LLM Provider 延迟 / reasoning 结论（2026-05-31）

play 回合 TTFT/延迟排查 + 官方 DeepSeek vs OpenCode 选型实测的**精华结论**。
原始跑测产物可清理，本文件是保留下来的结论。

复测工具：`backend/cli/_ttft_probe.py`（直连测 TTFT，env：`ENDPOINT/KEY/MODEL/REASONING_OFF/PROMPT_MULT/RUNS`）。

---

## 0. 根因（最重要）：reasoning 没真正关掉

play TTFT 慢（40–60s）的真根因 **不是** DeepSeek 端慢、也不是"到顶"，而是
**官方 DeepSeek 上 reasoning 被静默没关**：临时切百炼时留下的配方 `{"enable_thinking": false}`
是百炼的写法，官方 DeepSeek 不认识 → 静默忽略 → `deepseek-v4-pro` 默认 thinking=ON →
director/narrator 每轮先跑隐藏思维链再吐 JSON。

- v4-pro **默认开思考**；v4-flash 几乎不思考（所以 NPC 一直没被坑，长板只在 v4-pro 的 director）。
- **关思考配方是 per-endpoint、且错了会静默失效**——这是最容易复发的坑。

### 各端点正确的关思考配方（extra_body）
| 端点 host | 配方 |
|---|---|
| `api.deepseek.com`（官方直连） | `{"thinking": {"type": "disabled"}}` |
| `opencode.ai`（OpenCode，转发 DeepSeek） | `{"thinking": {"type": "disabled"}}`（同官方，透传有效） |
| `dashscope.aliyuncs.com`（百炼） | `{"enable_thinking": false}` |

**已治本**：`services/model_management.py::_resolve_reasoning_off()` 按 endpoint host 自动派生
正确配方（已知 host 权威，无法被 stale 配置坑），单测 `tests/test_reasoning_off_recipe.py`。

---

## 1. 直连单次探针（reasoning 关闭后，`_ttft_probe.py`）

| 端点 / 模型 | prompt | TTFT | 备注 |
|---|---|---|---|
| 官方 v4-pro | 4.5k | **1.1s** | 关思考 |
| 官方 v4-pro | 12k | **1.1–1.6s** | 关思考 |
| 官方 v4-flash | 4.5k | 0.5–0.6s | |
| OpenCode v4-pro | 4.5k | 2.4–2.9s | 关思考；默认不关=41s |
| OpenCode v4-pro | 12k | 2.7–3.5s | |
| OpenCode v4-flash | 4.5k | 1.8–2.1s | |

> 注意：单次探针只生成 ~700 token，**不代表真实导演**（~1900 token），见下方端到端。

边缘网络往返（401 探测）：官方热请求 ~57–90ms；OpenCode ~280ms（网关鉴权+多一跳开销）。

---

## 2. 端到端真实回合（`_measure_play.py`，深局 round 44–49）

| 指标 | 官方 DeepSeek | OpenCode |
|---|---|---|
| TTFT | ~20.6s (n=1) | **中位 ~27s**（21–29s，n=5）；偶发 ~44s 抖动 |
| done | ~39.9s | **中位 ~38s**（35–46s） |

**结论**：
- OpenCode 比官方 **首包慢约 7s（~1.3x）**，**整轮总时长基本持平**。
- OpenCode **抖动更大**（偶尔蹦 ~40s+ 慢轮），官方更稳。
- 之前一度看到的 "opencode 慢 2x" 是被单次 44s 异常值 + n=1 带偏，实测没那么糟。

---

## 2.5 NPC DeepSeek 缓存命中（原 Q2，结论）

现象"NPC 缓存=0"是误读:实测近两个 session NPC 命中 **37–44%**，0 失败。
看到的 0 是**冷启动前 1–2 轮**——每个 NPC 首次出场必 miss（前缀缓存只在同一 NPC
跨轮重发时命中），round 3+ 开始爬升。

- NPC system prompt 结构:**静态前缀**（世界设定 + 人设 + 已知 + 秘密 + ~32 行规则脊）
  ≈ avg 1400 token，**热轮 100% 命中**（Task B 已把 peer_relations/reflection 移出前缀）；
  **易变尾巴**（scene_brief / per_npc_focus / 记忆召回 / 关系 / 意图 / lore…）≈ avg 1832 token，
  **按定义不可缓存**。
- 所以 ~40% ≈ 前缀占比，**已接近结构上限**。想再压只能:①缩短 1832 token 易变尾巴
  （降成本+顺带抬命中率，但损 NPC 上下文质量）②减冷 miss（养热 NPC / 减每轮活跃 NPC，玩法层）。
- 命中率呈双峰:多数轮 0–45%（首调用），少数 91–98%（同轮多次调用:tool 轮 / climax reflect+act）。
- 跨 NPC 共享头在 DeepSeek **不命中**（前 session 控制实验已证伪，相关重排已 revert）。
- admin 后台目前**无**缓存命中率展示面板。

---

## 3. 选型 / 成本

- **官方 DeepSeek**：按 token 计费（v4-pro ~313/626 分/M，flash 101/202）；最快最稳；适合实时游戏。
- **OpenCode Zen Go**：包月（首月 $5，后 $10/月），额度 $12/5h·$30/周·$60/月；便宜；首包慢 ~7s、更抖。
  - 端点 `https://opencode.ai/zen/go/v1`，openai_compatible，含 deepseek-v4-pro/flash。
- **混用方案**（正式上线推荐，目前未采纳）：`game_main`（导演+旁白，延迟长板）回官方，
  其余（NPC flash、工坊生成、压缩、结局）留 OpenCode → 拿回 ~20s TTFT 同时省大头成本。

---

## 4. 当前生效配置（2026-05-31，测试期=全 OpenCode 省钱）

7 个 deepseek 槽全部绑 **OpenCode Zen Go**：
`game_main / conversation_compression / ending_summary / admin_generation / research_planning` → v4-pro；
`npc_agent / intermission` → v4-flash。
（`image_generation`→gpt-image、`research_summary`→grok 未动。）

### 回滚到官方 DeepSeek（快照）
```sql
UPDATE model_slot_bindings SET model_id='e814ab2f-566d-4679-92af-03be84fead56', updated_at=now()
  WHERE slot_name IN ('game_main','conversation_compression','ending_summary','admin_generation','research_planning');
UPDATE model_slot_bindings SET model_id='3e470be3-9d44-444c-97f5-dc66435089be', updated_at=now()
  WHERE slot_name IN ('npc_agent','intermission');
```
（`e814ab2f`=DeepSeek 官方 v4-pro，`3e470be3`=DeepSeek 官方 v4-flash。）

### 混用（只把导演/旁白拉回官方）
```sql
UPDATE model_slot_bindings SET model_id='e814ab2f-566d-4679-92af-03be84fead56', updated_at=now()
  WHERE slot_name='game_main';
```
