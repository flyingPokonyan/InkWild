# 世界详情角色排序 + Cover V3 Prompt 落地 — 2026-05-19

> **Q1**：世界详情页人物角色按重要程度排序。当前 `WorldCharacter` 表无任何重要程度字段，API 返回顺序是 PG 任意。加 `narrative_weight` 列，publish 时按现有 `role_tag` / `is_image_target` 派生，前端按权重排。
>
> **Q2**：把 `cover_brief.py` 现有"三分支 `ip_mode` × dense brief"统一为 V3 极简模板（IP 名当主语 + key art 形式松动 + LLM 派生 mood）。实验 16+4 张图验证：V3 跃迁明显，mood cue 是打破均值的关键钩子。
>
> 两件事独立 commit，不互相依赖；先 Q1（短平快）再 Q2（深度）。

---

## 1. 实验背景（Q2）

完整对比脚本与测试图见 `backend/scripts/exp_cover_prompts_ip_anchor_2026_05.py`（16 张矩阵）+ `exp_cover_prompts_v3_unified_2026_05.py`（4 张 mood 消融）。

核心发现：

1. **V1（IP 锚提前但保留"电影海报+字体规定"）是反优化** —— 模型更倾向商业海报均值。
2. **V2（key art / 形式不限）** —— 解锁构图多样性，但 typography 仍当字体规定时模型仍在"必出标题字"预期里。
3. **V3（V2 + mood cue + 标题非强制）** —— 4 个作品 4 种风格（水墨长卷 / 朱红戏剧绘画 / 极简剪影 / 工笔群像），不撞均值。
4. **mood 消融实验**：V3_UNIFIED（去掉 mood）4 张全部退化到商业海报均值。结论：**mood cue 是打破均值的必要钩子**。
5. **派生表 = 写死**：题材 → mood 映射本身又会让"同题材世界撞 mood"。改为 LLM 在 `cover_brief_helper` 派生（与 `world_name_english` 同一次 call，零额外成本）。

---

## 2. Q1 — 角色排序

### 2.1 改动点

| # | 文件 | 改动 |
|---|---|---|
| 1 | 新 Alembic migration | 加 `world_characters.narrative_weight` |
| 2 | `backend/models/world.py` | `WorldCharacter` 加字段 |
| 3 | `backend/services/publish_service.py` | `_persist_characters` 派生 narrative_weight |
| 4 | `backend/api/worlds.py` | `get_world` 加 `order_by` |
| 5 | `backend/tests/test_publish_service.py`（已有） | 加 1 case |

### 2.2 派生规则

publish 时在 `_persist_characters`（line ~275-292）：

```python
role_tag = wc_data.get("role_tag", "")
if "主角" in role_tag or role_tag == "主":
    wc.narrative_weight = 100
elif "宿敌" in role_tag or "反派" in role_tag:
    wc.narrative_weight = 90
elif wc_data.get("is_image_target"):
    wc.narrative_weight = 70
else:
    wc.narrative_weight = 50
```

### 2.3 API 排序

`backend/api/worlds.py:48-50` 改：

```python
characters = (await db.execute(
    select(WorldCharacter)
      .where(WorldCharacter.world_id == world.id, WorldCharacter.playable.is_(True))
      .order_by(WorldCharacter.narrative_weight.desc(), WorldCharacter.created_at.asc())
)).scalars().all()
```

### 2.4 兼容性

- 现有已发布世界 `narrative_weight = 0`（migration default），排序结果跟现状一致（按 created_at）。
- 后续 admin 编辑器加 0-100 滑块再分批 backfill；本 plan 不做。

---

## 3. Q2 — Cover V3 落地

### 3.1 `cover_brief.py` 改造

**删**：
- `IpMode` literal + `derive_ip_mode()` 函数
- `derive_typography_hint()` 派生表（typography 改 LLM 派生，与 mood 合并到 helper）
- `_world_intro()` 三分支
- `_title_clause()` 里的"中央安全区"硬约束（V3 让模型决定标题位置）

**`CoverBrief` schema 改**：

```python
class CoverBrief(BaseModel):
    world_name: str
    world_name_english: str = ""
    genre_tag: str = ""
    mood: str = ""              # 新增：LLM 派生 3-5 个画面气质 cue 词，顿号分隔
    ip_name: str | None = None  # None = original / unknown
    # 删: ip_mode, typography_hint

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy(cls, data):
        # 兼容旧 visual_brief JSONB 里的 ip_mode / typography_hint 字段
        if isinstance(data, dict):
            for legacy in ("ip_mode", "typography_hint"):
                data.pop(legacy, None)
        return data
```

**新 prompt 模板（hero）**：

```python
_FACE_SHORT = "人物虚构，不与任何真实演员相似。"
_LOGO_SHORT = "不要 logo、品牌、奖项、发行日期、电视台署名。"


def _world_subject(brief: CoverBrief) -> str:
    """统一 IP 锚句式（去 ip_mode 分支）。"""
    if brief.genre_tag:
        s = f"《{brief.world_name}》—— 一部{brief.genre_tag}作品"
    else:
        s = f"《{brief.world_name}》"
    if brief.ip_name and brief.ip_name != brief.world_name:
        s += f"，视觉对标《{brief.ip_name}》"
    return s + "。"


def _mood_clause(mood: str) -> str:
    if not mood:
        return ""
    return f"画面气质：{mood}（可作为画面元素自然出现，不必强制做成标题字）。"


def _title_hint(zh: str, en: str) -> str:
    en_part = f" / {en.strip()}" if en and en.strip() else ""
    return f"若画面包含标题文字，使用「{zh}」{en_part}。"


def build_world_hero_prompt(brief: CoverBrief) -> str:
    return (
        f"{_world_subject(brief)}"
        "为这部虚构 IP 创作一幅 21:9 的 key art —— "
        "可以是海报、剧照、宣传画或概念图，挑你认为最能传达调性的形式。"
        f"{_mood_clause(brief.mood)}"
        f"{_title_hint(brief.world_name, brief.world_name_english)}"
        f"{_FACE_SHORT}{_LOGO_SHORT}"
    )
```

**Script cover / Ending card** 按相同范式：

```python
def build_script_cover_prompt(world_brief, *, script_title, script_title_english):
    return (
        f"为《{world_brief.world_name}》中的剧情线《{script_title}》"
        "创作一幅 3:2 的 key art —— 可以是海报、剧照、宣传画或概念图。"
        f"{_mood_clause(world_brief.mood)}"
        f"{_title_hint(script_title, script_title_english)}"
        f"{_FACE_SHORT}{_LOGO_SHORT}"
    )


def build_ending_card_prompt(world_brief, ending):
    return (
        f"为《{world_brief.world_name}》创作一张「{ending.title}」结局画面卡。"
        f"故事到这里的状态：{ending.description}"
        f"{_mood_clause(world_brief.mood)}"
        f"若画面包含标题文字，使用「{ending.title}」。"
        f"{_FACE_SHORT}无血腥暴力直白展示，可象征性表达。{_LOGO_SHORT}3:2 横版。"
    )
```

**Character portrait** 保留"眼线上三分位"约束（前端圆形头像 crop 依赖），其他放松：

```python
def build_character_portrait_prompt(world_brief, char):
    descriptor = _character_descriptor(char)  # 保留现有 ref_anchor / 4 维派生
    style_cue = (
        f"《{world_brief.world_name}》风格的 "
        if world_brief.ip_name
        else ""
    )
    return (
        f"为《{world_brief.world_name}》中的角色「{char.name}」（{descriptor}）"
        f"创作一幅 {style_cue}2:3 人物海报。"
        f"{_FACE_SHORT}"
        "眼线落在画面上三分位附近（前端将自动裁出圆形头像）。"
        f"画面下方约 1/6 高度的区域居中渲染文字「{char.name}」，"
        "文字宽度约占画面宽度 1/4-1/3，不要遮挡角色面部。"
        f"{_LOGO_SHORT}2:3 竖版。"
    )
```

### 3.2 `cover_brief_helper.py` 改造

**`_WORLD_HELPER_SYSTEM` 加 mood 输出**：

```text
输出 schema：
{
  "world_name_english": "...",
  "mood": "3-5 个画面气质 cue 词，顿号分隔（如「毛笔书法、朱印、龙袍、烛火、深红」）",
  "characters": { ... }
}

mood 规则：
- 词的方向：视觉元素（毛笔书法/朱印/烛火/灯笼/星空）、色调（深红/冷青/暮色/暖黄）、氛围（仙气/烟雾/留白/几何感）。
- 不要：人物动作、具体场景描述、物理摄影术语（"广角"/"浅景深"等）。
- 不同世界 mood 必须有区分度——避免所有古装都"毛笔书法+朱印"撞均值。结合 world_name / IP / 故事核心冲突，给出独特组合。
```

**`derive_world_cover_brief()` 改**：
- 删除 `derive_typography_hint()` 调用（连同 cover_brief.py 里那个函数一起删）
- 删除 `derive_ip_mode()` 调用，直接 `ip_name = recognition.ip_name if recognition and recognition.confidence >= 0.6 else None`
- 构造 `CoverBrief` 时塞入 LLM 返回的 `mood`（fallback 空字符串）

### 3.3 调用方收尾

**`world_creator_agent_v2.py`**（grep `derive_ip_mode` / `derive_typography_hint` / `ip_mode` 找所有引用点）：删除对应调用，参数链同步收敛。

### 3.4 兼容旧数据

走 schema validator 兼容路径（见 §3.1 的 `_drop_legacy` validator）。已发布世界继续用旧图，admin 想出新图自己手动 trigger 重生。

### 3.5 测试

- `backend/tests/test_cover_brief.py`（如已有）改：4 个 builder 各 1 case 测最终 prompt 含关键片段（"key art"、mood、IP 锚条件拼接）+ 1 个 schema validator case（旧 dict → 新 CoverBrief）。
- `backend/tests/test_cover_brief_helper.py` 加 1 case：mock helper LLM 返回含 mood 的 JSON → `CoverBrief.mood` 非空。
- 不补边角 case 测试。

---

## 4. 实施顺序

**Q1**（~1 小时）：
1. 写 migration → 跑 `alembic upgrade head` 本地验证
2. 改 `models/world.py` + `services/publish_service.py` + `api/worlds.py`
3. 加 1 个 publish_service test
4. Commit

**Q2**（~半天）：
1. 改 `cover_brief.py`（删旧 + 加新 builder + schema validator）
2. 改 `cover_brief_helper.py`（system prompt + return mood）
3. 改 `world_creator_agent_v2.py` 调用方
4. 改/加测试
5. 跑现有 cover_brief / helper test 套件确认无回归
6. Commit

完成后开 admin 工坊跑一个新世界端到端验证（看真实 hero/cover/portrait/ending card 5 类图）。
