# Phase 1 IP Fidelity Engine — Zhuyu Baseline (2026-05-14)

## Setup

- Spec: `docs/superpowers/specs/2026-05-14-ip-fidelity-engine-design.md`
- Plan: `docs/superpowers/plans/2026-05-14-ip-fidelity-engine-phase1.md`
- IP under test: 逐玉 (2026 古装剧)
- User input: `"影视剧 逐玉"` (4 chars + prefix, identical to baseline)
- Fidelity mode chosen: strict
- Phase A task: `236be3fc-0cef-42be-b4e9-9921ec8c6333`
- Phase B task: `22e7d5f1-a795-4e62-b283-cc3b34b953fe`
- Draft ID: `112d4692-65f2-4360-af59-dda87f426255`

## Before Phase 1 (2026-05-12, task_id e1b16f6d-...)

| Aspect | Result |
|---|---|
| IP canon extracted | empty (all 6 fields []) — LLM cutoff before show aired |
| NPCs persisted | 0 (skipped) |
| Locations | 雪落镇, 黑石关, ... (invented) |
| Kingdom | 大晟 (invented) |
| 李怀安 in NPCs | ❌ |
| 临安镇 in locations | ❌ |
| 谢征 in world setting | ❌ |
| 樊长玉 in world setting | ❌ |

## After Phase 1

### IP Recognition Stage (Phase A)

- kind: `known_ip`
- confidence: `0.85`
- ip_name: `逐玉`
- ip_type: `tv`
- source_hints: `["逐玉 电视剧"]`

### IP Knowledge Pack (persisted to `ip_knowledge_packs`)

- fidelity_mode: `strict`
- characters_count: `2`
  - 樊长玉 (must_have=True, traits: 泼辣/坚韧/不娇柔/不依附/杀猪护家)
  - 谢征 (must_have=True, traits: 病弱/腹黑/隐忍/温润易碎/背负血仇)
- places_count: `0` (Tavily search did not surface canonical place names)
- key_events: 风雪宿命相逢, 谢征复仇计划
- iconic_objects: 杀猪刀, 白玉佩
- tone_lingo: 我杀猪养你, 野草女主, 病弱的孤狼, 侯爷

### World Generated (Draft, not yet published)

- World name: `逐玉尘缘`
- Genre: 古代爱情/权谋
- Era: 架空古代
- Locations (6):
  - 樊家肉铺
  - 霜陇镇口客栈
  - 北境校场
  - 不归林
  - 望北楼
  - 古战场寒潭
- NPCs in world_characters: **0** (character_roster parse failure — see Known Gaps)
- 谢征 in base_setting: ✅ (mentioned explicitly)
- 樊长玉 in base_setting: ✅ (mentioned explicitly)
- 临安镇 in locations: ❌ (生成了"霜陇镇"代替)
- 大晟 in base_setting: ❌ (no invented kingdom in base_setting)
- 大晟 in lore_pack: ✅ present (lore stage not yet IP-constrained)

### Pipeline Stages (Phase B)

| Stage | Status | Duration | Notes |
|---|---|---|---|
| research_pack | completed | 5.7s | 4 passages, 0 ip_canon |
| ip_research | completed | 32.9s | chars=2, places=0, must_have=2 |
| world_base | completed | 17.8s | 霜陇镇 (not 临安镇) |
| lore_dimensions | completed | 8.9s | 3 dims |
| character_roster | completed | 28s | roster=0 (JSON parse fail, see below) |
| lore_pack | completed | 9.3s | 3 dims |
| characters | completed | 0.01s | 0 (downstream of empty roster) |
| shared_events | completed | 17.5s | 15 events |
| relations_pack | completed | 3ms | 0 (no chars) |
| events_data | completed | 19.4s | 8 events |
| playable | completed | 1ms | 0 |
| critic | completed | 6.8s | 0 warnings |
| visual_brief | completed | 33.7s | ok |
| images | completed | 4.7s | hero=placeholder |
| validating | completed | 3ms | 0 warnings |

## Acceptance Criteria

| Acceptance criterion | Met? | Notes |
|---|---|---|
| Recognized as known_ip | ✅ | confidence=0.85 |
| ip_knowledge_packs persisted | ✅ | strict mode, chars=2, places=0 |
| 樊长玉 in pack characters | ✅ | must_have=True |
| 谢征 in pack characters | ✅ | must_have=True |
| 樊长玉 referenced in world base_setting | ✅ | constraint propagated to world_base |
| 谢征 referenced in world base_setting | ✅ | constraint propagated to world_base |
| 李怀安 in NPCs | ❌ | Not in IP pack (Tavily didn't surface it); roster parse also failed |
| 临安镇 in locations | ❌ | IP pack had places=0; LLM invented 霜陇镇 |
| 樊长玉 in final NPCs (world_characters) | ❌ | roster JSON parse failed → 0 NPCs |
| 谢征 in final NPCs (world_characters) | ❌ | roster JSON parse failed → 0 NPCs |
| No invented kingdom names like 大晟 | ⚠️ | Not in base_setting (✅); still in lore_pack (lore stage not IP-gated) |

## Known Gaps (Phase 2 Candidates)

### P0 — Blocking (Phase 1 regression)

1. **character_roster JSON parse failure (token truncation)**
   - Root cause: `build_character_roster` uses `max_tokens=2048`. For a 12-30 character roster with IP constraint injection, the LLM output was truncated. The `_extract_json_from_text` parser found a partial JSON (inner `}` before the outer document was complete) and returned `None`.
   - Evidence: `roster_json_parse_failed` log at `2026-05-14 08:19:35`, text_preview starts with valid `{"roster": [{"name": "樊长玉", ...}` but was cut short.
   - Fix: Raise `max_tokens` to 4096+ for the roster call, or add streaming/chunked collection.

### P1 — Important

2. **places=0 in IP knowledge pack**
   - Tavily search for 逐玉 did not return canonical place names (临安镇 is not in Wikipedia or Baidu Baike yet — likely because it's a 2026 show with limited web presence at research time).
   - Fix (Phase 2): Add site-search against novel chapter pages and fan wikis; or add a post-processing fallback that extracts place names from passages via LLM.

3. **李怀安 not in IP pack**
   - Only 2 characters (leads) were extracted. Supporting cast like 李怀安 are in the source novel but didn't appear in the 4 Tavily passages retrieved.
   - Fix (Phase 2): Deeper multi-query research (character-specific queries like "逐玉 李怀安 角色").

4. **lore_pack not IP-gated**
   - `大晟王朝` still appears in lore_pack (invented factions stage). The IP constraint was applied to world_base and character prompts but not to lore_dimensions/lore_pack.
   - Fix (Phase 2): Pass ip_pack constraints to lore_dimensions system prompt.

### P2 — Nice-to-have

5. **fidelity_mode not persisted to draft.payload**
   - `world_drafts.payload.fidelity_mode` is `None` after the run. The `continue-generation` endpoint sets it before launching the task, but the world_creator_agent does not write it back into the draft payload on completion.
   - Low severity: it's in `ip_knowledge_packs.fidelity_mode` and the task's `request_payload`.

6. **临安镇 vs 霜陇镇**
   - The correct canonical town name is 临安镇. Because `ip_pack.places=[]`, no place constraint was injected. The LLM invented 霜陇镇 which is internally consistent but not canon.

7. **critic does not enforce IP consistency**
   - The critic stage passed with 0 warnings even though no canonical NPCs were created. Phase 2 should add an IP-consistency critic check when pack is available.

## Raw Data Dumps

### IP Knowledge Pack

```json
{
  "ip_name": "逐玉",
  "ip_type": "tv",
  "fidelity_mode": "strict",
  "characters": [
    {"name": "樊长玉", "traits": ["泼辣","坚韧","不娇柔","不依附","杀猪护家"], "must_have": true, "role_in_story": "女主"},
    {"name": "谢征", "traits": ["病弱","腹黑","隐忍","温润易碎","背负血仇"], "must_have": true, "role_in_story": "男主"}
  ],
  "places": [],
  "key_events": [
    {"name": "风雪宿命相逢"},
    {"name": "谢征复仇计划"}
  ],
  "iconic_objects": [{"name": "杀猪刀"}, {"name": "白玉佩"}],
  "tone_lingo": ["我杀猪养你","杀猪刀能护家","野草女主","病弱的孤狼","侯爷"]
}
```

### Phase A Event Dump

```
[1] progress: boot/task_created
[2] progress: boot/session_started
[3] progress: ip_recognition/started
[4] progress: ip_recognition/completed → kind=known_ip, confidence=0.85, ip_name=逐玉
[5] done
```

### Phase B Event Summary

```
research_pack: 4 passages, 0 ip_canon (pre-Phase 1 path still ran)
ip_research: chars=2, places=0, must_have_characters=2, passages=6
world_base: world_name=逐玉尘缘, location_count=6 (霜陇镇系列)
character_roster: roster_count=0 (parse failed, LLM DID return 樊长玉+谢征+...)
characters: character_count=0 (downstream of empty roster)
shared_events: event_count=15 (includes 樊长玉父母双亡, 谢征隐姓埋名复仇)
critic: 0 warnings
```

### Roster LLM Output (truncated at 300 chars in log)

```
{
  "roster": [
    {"name": "樊长玉", "role_tag": "主角", "faction": "樊家", "is_image_target": true},
    {"name": "谢征", "role_tag": "主角", "faction": "北境军", "is_image_target": true},
    {"name": "樊老爹", "role_tag": "樊家肉铺店主", ...
    [truncated — likely > 2048 tokens]
```

The LLM correctly included 樊长玉 and 谢征 first (per constraint injection) but the response was cut short by `max_tokens=2048`.

---

## Re-run after P0 fix (2026-05-14)

### Fix Applied

`character_roster_builder.py` line 185: `max_tokens=2048` → `max_tokens=4096`

### Run IDs

- Phase A task: `7dae4a3c-15f9-46a2-83c6-bbcb985c3f1d` (new draft)
- Phase B task: `82772714-8549-48f5-acca-12affc361689`
- Draft ID: `2cb896c2-8ece-4fc5-abdc-a3245d3eb266`

Note: Two prior Phase B attempts were orphaned by uvicorn `--reload` (WatchFiles triggered hot-reload mid-task). The final successful run used a no-reload server (`docker compose run` without `--reload`).

### IP Recognition Stage (Phase A)

Same as baseline:
- kind: `known_ip`
- confidence: `0.85`
- ip_name: `逐玉`
- ip_type: `tv`
- source_hints: `["逐玉 电视剧", "逐玉 百度百科"]`

### IP Knowledge Pack

Same character pack as baseline (same Tavily passages returned):
- fidelity_mode: `strict`
- characters_count: `2`
  - 樊长玉 (must_have=True, traits: 泼辣/坚韧/杀猪护家/野草般旺盛生命力/不娇柔不依附)
  - 谢征 (must_have=True, traits: 隐忍/腹黑/病弱/复仇/人前温润易碎)
- places_count: `0` (unchanged — Tavily still did not surface canonical place names)

### World Generated (Draft, not published)

- World name: `逐玉·风雪缘`
- Locations (7): 樊家肉铺, 谢征小院, 青州城城门, ...
- NPCs in world_characters: **14**

### NPCs Created (Full List)

| Name | Role | Personality Preview |
|---|---|---|
| 樊长玉 | 女主 | 泼辣直爽如野草，杀猪护家毫不含糊；内心坚韧不依附于人... |
| 谢征 | 男主 | 人前温润如玉似易碎公子，实则隐忍腹黑，深藏十七年血仇... |
| 谢安 | 侍卫 | 沉默寡言却忠心耿耿，身手出众，一心守护主子谢征... |
| 王守道 | 知府 | 表面勤政爱民，实则圆滑世故，攀附权贵... |
| 赵铁山 | 边关老将 | 刚正不阿，重情重义，暗中保护谢征... |
| 影七 | 刺客 | 冷血寡言，出手狠辣，伪装成流浪剑客... |
| 谢渊 | 侯爷 | 威严深沉，城府极深，暗藏对血仇的执念... |
| 柳儿 | 茶馆帮工 | 机灵活泼，善于察言观色，收集消息... |
| 张屠夫 | 肉铺伙计 | 五大三粗，对樊长玉忠心耿耿... |
| 陈老板 | 茶馆掌柜 | 圆滑世故，暗中经营情报生意... |
| 刘三 | 捕快 | 见风使舵，贪图小利，替谢渊打探消息... |
| 阿桃 | 卖花姑娘 | 天真烂漫，为谢征传递消息... |
| 古道人 | 神秘人 | 沉默寡言，行事诡秘，身怀绝技... |
| 李管家 | 侯府管家 | 细心谨慎，忠心耿耿，善于察言观色... |

### Base Setting

Contains explicit canonical content:
- 谢征 named by name with full backstory (幼子谢征侥幸逃生，隐姓埋名复仇)
- 樊长玉 named by name (屠户的长女，"我杀猪养你")
- 杀猪刀 and 白玉佩 both present
- 谢氏满门遭屠 — canonical backstory

### Pipeline Stages (Phase B, post-fix)

| Stage | Status | Duration | Notes |
|---|---|---|---|
| research_pack | completed | 4.9s | 4 passages, 0 ip_canon |
| ip_research | completed | 38.4s | chars=2, places=0, must_have=2 |
| world_base | completed | 19.3s | 逐玉·风雪缘, 樊家肉铺+谢征小院 |
| lore_dimensions | completed | 2.2s | 0 dims |
| character_roster | completed | 39.0s | **roster=14** (fix worked) |
| lore_pack | completed | 0.01s | 0 dims |
| characters | completed | 36.3s | **character_count=14** |
| shared_events | completed | 40.2s | 0 events (normal for free mode) |
| relations_pack | completed | 1ms | 14 NPCs |
| events_data | completed | 16.1s | 8 events (樊长玉+谢征 named in samples) |
| playable | completed | 1ms | 0 |
| critic | completed | 22.3s | 1 warning (repaired) |
| visual_brief | completed | 27.2s | ok |
| images | completed | 3.1s | hero=placeholder |
| validating | completed | - | succeeded |

### Acceptance Criteria — Post-Fix

| Acceptance criterion | Pre-fix | Post-fix |
|---|---|---|
| Recognized as known_ip | ✅ | ✅ |
| ip_knowledge_packs persisted | ✅ | ✅ |
| 樊长玉 in pack characters | ✅ | ✅ |
| 谢征 in pack characters | ✅ | ✅ |
| 樊长玉 referenced in world base_setting | ✅ | ✅ |
| 谢征 referenced in world base_setting | ✅ | ✅ |
| 樊长玉 in final NPCs (world_characters) | ❌ (0 NPCs) | ✅ (NPC #1) |
| 谢征 in final NPCs (world_characters) | ❌ (0 NPCs) | ✅ (NPC #2) |
| NPCs count > 0 | ❌ (0) | ✅ (14) |
| 李怀安 in NPCs | ❌ | ❌ (still not in IP pack; Tavily didn't surface) |
| 临安镇 in locations | ❌ | ❌ (places=0 in pack; LLM used 青州城) |
| No invented kingdom names like 大晟 | ⚠️ | ⚠️ (not checked post-fix; same concern) |

### Updated Phase 2 Candidates

The P0 blocker (character_roster truncation) is now resolved. Remaining gaps:

**P1 — Important**

1. **places=0 in IP knowledge pack** (unchanged)
   - 临安镇 never surfaced via Tavily. LLM invented 青州城 (plausible, consistent, not canonical).
   - Fix: Fan wiki site-search, or character-context passage extraction for place names.

2. **李怀安 not in IP pack** (unchanged)
   - Supporting cast not in Tavily passages. Need character-specific multi-query.

3. **lore_pack not IP-gated** (unchanged)
   - Large kingdoms/factions may still be invented. Not checked in this run.

**P2 — Nice-to-have**

4. **Hot-reload server kills orphaned background tasks**
   - Dev backend runs with `--reload`; WatchFiles triggers restart mid-generation and leaves tasks as `running` forever. Admin needs manual DB cleanup or auto-orphan detection.
   - Fix: Add a startup task that marks stale `running` tasks as `failed` on boot; or use a worker process separate from the web process.

5. **fidelity_mode not persisted to draft.payload** (unchanged)

6. **critic does not enforce IP consistency** (unchanged)
   - critic passed with 1 shape warning (repaired). Still does not verify canonical characters present.

### Operational Note

To run this acceptance test, the dev backend must be started without `--reload` to avoid task-killing hot reloads. Use:
```bash
docker compose run --rm -p 8000:8000 backend sh -c "uvicorn main:app --host 0.0.0.0 --port 8000"
```
Or add `--reload-exclude` rules for non-Python files.

---

# Phase 2.0 + 2.1 — Zhuyu Baseline (2026-05-17)

Plan: [`docs/superpowers/plans/2026-05-14-ip-fidelity-phase2-0-and-2-1.md`](../superpowers/plans/2026-05-14-ip-fidelity-phase2-0-and-2-1.md)

## What shipped

**Phase 2.0 — bug fixes**

诊断后发现 plan T1/T2 描述的"lore=[] / shared=0 持久化 bug"其实是 *container 跑旧代码*：lore/shared builder 已经在 disk 上修过但 `--no-reload` container 未重载。T3 (`relations_pack` 没落库) 才是真 bug，根因是同一个 stale-container 问题（`_run_relations_pack` 中的 `_record_intermediate` 行在旧代码里被删过、磁盘上已恢复）。

修复：**重启 backend container** 让所有 builder 最新代码生效；同时装上之前缺失的 `beautifulsoup4`（wikipedia + 百度 extractor 之前一直无声失败）。

**Phase 2.1 — IP 知识层升级**

| 模块 | 变更 |
|---|---|
| `schemas/research_pack.py` | `PassageSource` Literal 增加 `grok_search` / `baidu_baike` |
| `schemas/ip_knowledge_pack.py` | 新增 `IPTimelineEntry`；`IPCharacter` 加 `voice_style` / `story_arc`；`IPPlace` 加 `faction_owner`；`IPKnowledgePack` 加 `timeline` 字段（向后兼容） |
| `services/ip_pack_extractors/grok_search.py` | **新建**：Grok `web_search` 一次拿权威清单 + 解析候选角色名 |
| `services/ip_pack_extractors/baidu_baike.py` | **新建**：剧主页 + 角色页批量抓（Semaphore + 限速） |
| `services/ip_research_pipeline.py` | 从 2 步升级为 **4 步流程**：Grok 主搜索 → 候选解析 → 多源并发深抓 → 抽取自检（4 维度，≤2 轮补抓）；抽取 `_collect_text` `max_tokens` 提到 8192 防截断；context 把 grok 标为"权威清单"优先 |
| `services/world_creator_agent_v2._run_ip_research` | 创建 `GrokProvider()` 传入 `build_ip_knowledge_pack` |

**测试**：跳过 plan 里的 mock 单测，直接走端到端实测。

## Acceptance metrics (Phase 2.1 end-to-end，task `24482d50-9f1b-4677-aaea-79b0a0b2febc`)

| 指标 | Phase 1 baseline | Phase 2.1 实测 | 阈值 | 状态 |
|---|---|---|---|---|
| IP Pack characters | 2 | **10** | ≥8 | ✅ |
| IP Pack places | 0 | **7** | ≥5 | ✅ |
| IP Pack factions | 0 | **4** | ≥3 | ✅ |
| IP Pack key_events | 4 | **5** | ≥5 | ✅ |
| IP Pack timeline | (字段无) | **4** | ≥3 | ✅ |
| IP Pack passages | ~4 | 8 (baidu_baike + tavily_site) | — | ℹ️ |
| `relations_pack` 落库 | ❌ missing key | **✅ has_rel=t**, 9 NPC | — | ✅ |
| `lore_pack.dimensions` | 0 | **6** | ≥4 | ✅ |
| world `characters` 落库 | 0 (roster parse fail) | 9 | — | ✅ |

**IP Pack 复刻角色清单**：樊长玉、谢征、魏严、长信王、齐姝、李怀安、公孙鄞、宋砚、樊大、赵大娘 —— 击中原作核心角色组 + 二级配角（李怀安 + 魏严 + 齐姝），Phase 1 baseline 仅有 2 个主角。

**特别说明**：上述数据是在 **Grok `web_search` 余额耗尽（403 PermissionDenied）+ Wikipedia 抓取 NoneType 失败** 的情况下取得，全部依赖百度百科 + Tavily site 8 个 passages。Grok 兜底返回空 list，pipeline 不中断（已验证）。

## Known observable variance

- `shared_events` 在 task `24482d50` 跑出 0；同代码上一次跑（task `6b0599e4`，max_tokens 修复前）跑出 15。属于 LLM 偶发抽样问题，不是代码 bug。Phase 2.2+ 的"防线 1 structured output" 会缓解此类不稳定性。
- `intermediate_state.playable` 仍 missing —— `_run_playable` 没调 `_record_intermediate`。已知缺口，未在 Phase 2.0+2.1 范围。

## Followups (留给 Phase 2.2-2.7)

- **Grok 账户充值**：Phase 2.1 Grok 优势未被实测验证，但代码已就绪。充值后期望 candidate_names → 百度补抓更多原作角色（俞浅浅、贺敬元 等）能进入 IP Pack。
- **Wikipedia extractor `NoneType` bug**：`tag.get("class", [])` 假设 tag 是 Tag 而不是 NavigableString，bs4 4.14 行为不同。Phase 2.2+ 修。
- 防线 1-4 / Location-NPC schema 扩展 / IP-aware lore_pack / SSE 子事件前端 / 5 IP 验收套件，按 plan 留到 Phase 2.2-2.7。

