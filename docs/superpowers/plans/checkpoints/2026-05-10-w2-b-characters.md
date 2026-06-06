# Checkpoint: Task 2.3 + 2.4 — character_roster + characters_batch builder

**Date**: 2026-05-10  
**Plan**: `docs/superpowers/plans/2026-05-10-world-creator-v2.md` §3 Task 2.3 + 2.4  
**Status**: DONE

---

## Status: DONE

### Files modified

| 操作 | 文件 |
|------|------|
| Create | `backend/schemas/character_v2.py` |
| Create | `backend/services/character_roster_builder.py` |
| Create | `backend/tests/test_character_roster_builder.py` |

### Tests

```
tests/test_character_roster_builder.py  9 passed
tests/test_research_pack_builder.py     8 passed (regression)
Total: 17 passed, 0 failed
```

所有 9 个新测试全部通过，研究包 builder 回归测试无破坏。

### Implementation summary

**`schemas/character_v2.py`**:
- `CharacterRosterEntry`: name / role_tag / faction / is_image_target
- `CharacterScheduleSlot`: time / location（供未来扩展）
- `CharacterPeerRelation`: target / trust(-10~10) / kind
- `Character`: 完整 NPC schema，含 personality / secret / knowledge / schedule / initial_location / initial_peer_relations

**`services/character_roster_builder.py`**:
- 复用 `research_pack_builder` 的 `_collect_stream_text` + `_extract_json_from_text` 模式（内联实现）
- `build_character_roster`: 启发式提取"X个角色/NPC"数量提示，失败返回空 list
- `build_characters_in_batches`:
  - `batches = [roster[i:i+batch_size] for i in range(0, len(roster), batch_size)]`
  - `asyncio.Semaphore(concurrency)` 控并发
  - `asyncio.gather(return_exceptions=True)` 单批失败不阻塞其他批
  - dedup 校验：extra → 丢弃+warn，duplicate → 保留第一个+warn，missing → warn 不补
  - 返回按 roster 顺序排列的 list[Character]

### Concerns / Notes

- `playable` 字段本 task 不出（按约束，由后续 playable 阶段决定）
- 不改 `v2_agent` 也不改 `generation_prompt_builder.py`（M2-D 才串入）
- `CharacterPeerRelation.kind` 兼容 LLM 输出的 `label` 字段（见 v1 schema 字段名差异）
- passages 摘录注入限制前 5 条 × 200 字符，防止 context 过长
