# Checkpoint: w4-b — world_moderation_service + publish_world_draft 拦截

**Date:** 2026-05-10
**Task:** Plan §5 Task 4.5 + 4.6 — Spec §5.5 内容审核（moderation pass）

## Status: DONE

## Files Modified

- **Created:** `backend/services/world_moderation_service.py`
- **Modified:** `backend/api/admin.py` — `publish_world_draft` + `publish_script_draft` 加 moderation 拦截
- **Created:** `backend/tests/test_world_moderation_service.py`
- **Created:** `backend/tests/test_publish_moderation_block.py`

## Moderation API 实际签名

`engine/moderation.py` 中的核心接口：

```python
@dataclass
class ModerationResult:
    allowed: bool
    scores: dict[str, int]
    flagged_categories: list[str]
    reason: str | None
    source: str  # "local" | "llm"

async def classify(text: str, *, scope: str = "input", llm_router: LLMRouter | None = None) -> ModerationResult
def classify_locally(text: str, *, scope: str = "input") -> ModerationResult
```

注意：`engine/moderation.py` 的 `ModerationResult` 不是 `{"flagged": bool, "reasons": [str]}` 格式。
`world_moderation_service.py` 的 `ModerationCallable` 接受调用方传入的 callable，要求返回 `{"flagged": bool, "reasons": list[str]}`，与 engine/moderation 的 ModerationResult **不直接兼容** — 调用方负责适配（wrap classify 的结果）。

## 实现要点

### world_moderation_service.py
- `moderate_world_payload(payload, moderation_callable, *, sample_passages=5) -> list[str]`
  - 抽样字段：characters[].personality、characters[].secret、shared_events[].summary、events_data[].summary、lore_pack.dimensions[].content_blocks[].body
  - 每类取前 `sample_passages` 条（deterministic，便于测试）
  - 命中返回 `moderation_flag:<reason>` warning
  - callable 抛错 → 记 log，返回 []，不阻断
- `extract_moderation_flags(quality_warnings) -> list[str]`
  - 从 quality_warnings 取所有 `moderation_flag:` 开头的 reason（保留重复）

### admin.py 修改
- `publish_world_draft` + `publish_script_draft` 加 `force_publish: bool = Query(False)` 参数
- 置于函数签名末尾（`admin_user` 之后）以保持现有直接调用的测试兼容性
- commit 前检查 `draft.payload.quality_warnings` → `extract_moderation_flags`
- 含 moderation flags 且 `force_publish=False` → HTTP 422
- 仅 `moderation_flag:*` 触发拦截，其他 quality_warnings（如 `shape_violation:`）不拦截

## Tests

| 文件 | 测试数 | 结果 |
|------|--------|------|
| test_world_moderation_service.py | 8 | 全 PASS |
| test_publish_moderation_block.py | 6 | 全 PASS |
| test_admin_drafts_api.py | 4 | 全 PASS（回归） |
| test_admin_publish_atomicity.py | 2 | 全 PASS（回归，曾因参数顺序问题修复） |
| 全套 (552 tests) | 552 | 全 PASS |

## 关键决策

1. `force_publish` 参数放在 `admin_user` 之后：现有 atomicity 测试通过位置参数调用 `publish_world_draft(draft_id, request, db, admin)`，若 `force_publish` 插入 `db` 前会造成参数位移错误。
2. `ModerationCallable` 接口格式 `{"flagged": bool, "reasons": list[str]}` 与 `engine.moderation.ModerationResult` 不同，故 service 层定义独立的 callable 协议，调用方适配。
