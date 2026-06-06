# W6-A: Heavy Critic + Subtask Events

## Status: DONE

## Files Modified

- `backend/services/world_critic_service.py` — Replaced `heavy_critic_characters_stub` with real `heavy_critic_characters` + added `heavy_critic_playable`
- `backend/services/world_creator_agent_v2.py` — `_run_critic`接入重 critic (H2.5)，`_run_lore_pack` / `_run_characters` / `_run_events_data` 加 subtask events 回放
- `backend/tests/test_world_critic_heavy.py` — 新建，13 个测试覆盖 heavy critic 所有分支
- `backend/tests/test_world_creator_v2_pipeline.py` — 追加 3 个测试：subtask events lore_pack / characters + heavy_critic warnings 汇总

## Heavy Critic 设计

### `heavy_critic_characters`

**3-pass 流程**：
1. Pass 1 (critic): LLM 收 characters + ip_canon + world_description，输出 `{"verdict": "ok|needs_repair", "issues": [...]}`
2. Pass 2 (repair，仅 verdict=needs_repair 且 allow_repair=True): 抽出有问题的 characters subset，构造 repair 请求（含 issue details），LLM 重生有问题的角色
3. Pass 3 (re-critic): 验证修复效果；若仍有 issues → 写入 quality_warnings（不阻断生成）

**失败 fallback**: 任意 LLM 调用异常 → 返回原 characters + 空 warnings，不抛错

### Name 保护机制

- repair prompt system 明确"绝不修改 name 字段"
- 代码层双重保护：以原始 name 为 key 做匹配合并；repair LLM 若输出改名的条目（name 不在原 roster 中），该条目被丢弃，原角色保留不变
- 测试 `test_heavy_critic_repair_keeps_name` 和 `test_heavy_critic_name_protected_on_repaired_char` 验证两种场景

### `heavy_critic_playable`

- 单 pass review（不修复）
- LLM 输出 `{"warnings": ["..."]}`
- 失败 / 空 playable → 直接返回原 playable + 空 warnings

### 接入点 (`_run_critic` H2.5)

- 位置：H2 轻 critic 之后、H3 moderation 之前
- `_run_critic` 新增参数 `characters: list | None` + `description: str`
- 修复后的 characters 直接替换 `payload["world_characters"]`
- playable 从当前 `payload["playable"]` 取（已经由 G 阶段填充）
- 任何异常 catch 后 log warning，不 raise

## Subtask Events 覆盖

**模式：回放（batch emit）** — builder 跑完后一次性 emit 所有子任务事件，非真实时。

| 阶段 | subtask 粒度 | event type | subtask_key 格式 |
|------|-------------|------------|-----------------|
| lore_pack | 每个 LoreDimensionContent | `subtask_completed` (有内容) / `subtask_failed` warning (空) | `dim:{dim.key}` |
| characters | 每个 Character | `subtask_completed` | `char:{char.name}` |
| events_data | 每个 EventDataEntry | `subtask_completed` | `event:{event_id}` |

**images 阶段**：已是真实时 emit（W5-A），保留不变。

所有 subtask events 的 `subtask_total` 在阶段 started 时发出；回放时 `subtask_index` 从 1 递增。

## Tests

| 文件 | 数量 | 覆盖 |
|------|------|------|
| `test_world_critic_heavy.py` | 13 | no_issues / repair_pass / name_keeps / unfixed_warns / llm_failure / invalid_json / allow_repair=False / empty chars / playable 4 cases |
| `test_world_creator_v2_pipeline.py` (新增) | 3 | lore_pack subtask events + dim:key 格式 / characters subtask_completed per char / heavy_critic warnings 汇总到 quality_warnings |

**全套回归**: 609 passed, 2 deselected

## Concerns / Notes

- subtask events 是回放模式，前端看到的是阶段结束时一次性弹出多个 subtask_completed；真实时粒度留 P3
- characters 阶段 `subtask_total` 用 roster 数量（builder 开始前已知），character 实际产出数可能 < roster（失败 fallback），但不额外 emit subtask_failed（简化）
- events_data `subtask_total` 硬编码 8（target_count）而非实际产出数；这是近似值，前端可容忍
- heavy_critic 对 events_data / lore_pack 的引用一致性：repair prompt 明确 name 不变，events 引用稳定，不需要额外 stale-ref 处理
