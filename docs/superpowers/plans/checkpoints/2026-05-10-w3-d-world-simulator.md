# Checkpoint: W3-D world_simulator 接 events_data

**Date:** 2026-05-10
**Task:** §6 Task 5.4 — WorldSimulator tick() 接 events_data trigger 处理

## Status: DONE

---

## Files Modified

### `backend/engine/state_manager.py`
- 新增字段 `triggered_event_ids: set[str]` — 默认 `field(default_factory=set)`，防重复触发事件
- 新增字段 `world_state: dict` — 默认 `field(default_factory=dict)`，存储 events_data effects 的 world_state_changes
- `to_dict()` — 新增这两个字段的序列化（`triggered_event_ids` 序列化为 list，JSON 安全）
- `from_dict()` — 反序列化时将 `triggered_event_ids` list 转回 set

### `backend/engine/world_simulator.py`
- 新增 imports：`random`, `condition_dsl.{parse, evaluate, ConditionDSLParseError}`
- 新增模块级函数 `_process_events_data(state, world_config, events)` — events_data trigger 处理逻辑
- `tick()` 末尾调用 `_process_events_data()`（步骤 4，不影响步骤 1-3 现有逻辑）

### `backend/tests/test_world_simulator_events_data.py` (新建)
- 12 个单元测试，全部 `@pytest.mark.no_db`（不依赖 DB）
- 覆盖：触发、disabled 跳过、已触发跳过、条件为 False、npc_intent_driven、DSL 解析错误、probability=0、无 events_data 字段、多 clues、二次 tick 不重复、probability < 0 clamped、probability > 1 clamped

---

## GameState 修改

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `triggered_event_ids` | `set[str]` | `set()` | 已触发事件 id 集合 |
| `world_state` | `dict` | `{}` | events_data world_state_changes 落点 |

两个字段均为新增（未改动现有字段），向后兼容：`from_dict` 对不存在的键直接用 dataclass 默认值。

---

## Tests

```
tests/test_world_simulator_events_data.py  12 passed
Full regression (522 passed, 2 deselected, 54 warnings) — 无退步
```

---

## 实现要点

### `_process_events_data` 逻辑
1. `world_config.get("events_data") or []` — 无字段时安全返回空列表（老世界兼容）
2. 跳过 `disabled=True`
3. 跳过 `event_id in state.triggered_event_ids`
4. `dsl_parse + dsl_evaluate` 失败 → `logger.warning` + continue（不抛错）
5. `kind == "conditional"`:
   - `prob = max(0.0, min(1.0, float(...)))` — probability clamped 到 [0,1]
   - `world_state_changes` → `state.world_state[k] = v`
   - `npc_mood_changes` → `state.npc_relations[npc]["mood"]`（自动初始化 relation）
   - `spawn_clues` → `state.discovered_clues.append({id, content, found_at})`
   - 产出 `WorldEvent(event_type="scripted_event", ...)`
6. `kind == "npc_intent_driven"`:
   - `state.npc_intents[npc_name] = intent_payload`
   - 产出 WorldEvent
7. 未知 kind → `logger.warning` + continue（不标为已触发）
8. `state.triggered_event_ids.add(event_id)` — 在 kind 分支外统一标记

### tick() 变动
- 步骤 4 在 return 之前调用 `_process_events_data(updated_state, world_config, events)`
- `updated_state` 是 `copy.deepcopy(state)`，原始 state 不变（符合现有模式）

---

## Concerns / Notes

- 无已知 concern
- `world_state` 和 `triggered_event_ids` 需要在 Alembic migration 中随 `game_state` JSON 字段自然升级（JSON 列，无需 schema migration）
