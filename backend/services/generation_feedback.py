from __future__ import annotations


FEEDBACK_TEMPLATES: dict[tuple[str, str], str] = {
    ("boot", "session_started"): "已收到生成请求，正在建立创作会话…",
    ("boot", "loading_world_context"): "先把这个世界的设定和角色资料读进来…",
    ("boot", "world_context_ready"): "世界资料已就绪，共载入 {character_count} 名角色，检索到 {script_count} 条已有剧本",
    ("boot", "agent_ready"): "生成引擎已接入，马上开始拆解任务…",
    ("research", "analysis_started"): "先判断「{stage_label}」这一步要不要补一点参考资料…",
    ("research", "analysis_pulse"): "正在梳理「{stage_label}」真正缺哪一类资料…",
    ("research", "not_needed"): "「{stage_label}」这一步现有信息已经够用了，直接继续",
    ("research", "request_ready"): "为「{stage_label}」整理了 {query_count} 个参考方向，准备开查",
    ("research", "searching"): "正在为「{stage_label}」检索外部资料…",
    ("research", "searching_pulse"): "还在为「{stage_label}」筛更贴近题材的参考线索…",
    ("research", "search_completed"): "「{stage_label}」找到 {artifact_count} 条可用参考，开始提炼重点",
    ("research", "summarizing"): "正在把「{stage_label}」的资料压缩成可直接使用的摘要…",
    ("research", "summarizing_pulse"): "正在把「{stage_label}」的零散资料压成一份可直接使用的摘要…",
    ("research", "reference_doc_ready"): "「{stage_label}」的参考资料整理好了，共提炼 {char_count} 字素材",
    ("research", "search_unavailable"): "搜索暂时不可用，这一步先基于现有设定继续",
    ("world_base", "brief_started"): "先定一下世界的规模、气质和复杂度…",
    ("world_base", "brief_pulse"): "正在平衡世界的规模、气质和复杂度，马上给出骨架…",
    ("world_base", "brief_ready"): "世界策略敲定了，开始搭世界骨架",
    ("world_base", "started"): "正在构思世界框架：名称、背景、地点…",
    ("world_base", "drafting_pulse"): "世界轮廓已经成形，正在补地点层次和潜在暗线…",
    ("world_base", "completed"): "世界「{world_name}」框架完成，包含 {location_count} 个地点",
    ("characters", "brief_started"): "先判断人物数量、关系密度和秘密分布…",
    ("characters", "brief_pulse"): "正在估算人物关系密度，避免角色功能撞车…",
    ("characters", "brief_ready"): "人物策略定好了，开始铺关系网",
    ("characters", "started"): "正在设计人物和关系网…",
    ("characters", "drafting_pulse"): "人物关系已经有轮廓，正在补动机、秘密和彼此牵连…",
    ("characters", "subtask_completed"): "「{name}」档案已生成 · {subtask_index}/{subtask_total}",
    ("characters", "completed"): "创建了 {character_count} 个人物，关系网已搭好骨架",
    ("playable", "brief_started"): "先评估哪些视角最值得开放给玩家…",
    ("playable", "brief_pulse"): "正在比较哪些视角更有戏，也更适合玩家切入…",
    ("playable", "brief_ready"): "可玩视角策略已定，开始筛选核心角色",
    ("playable", "started"): "正在挑选最适合的可玩角色…",
    ("playable", "drafting_pulse"): "正在筛角色，优先保留信息差和行动空间更大的视角…",
    ("playable", "completed"): "选定了 {playable_count} 个可玩角色：{names}",
    ("playable", "review_started"): "先拿最终结局和主线收束再复检一遍可玩视角…",
    ("playable", "review_pulse"): "正在复检可玩视角是否剧透过重或彼此撞车…",
    ("playable", "review_completed"): "可玩视角复检完成，保留了 {playable_count} 个核心视角",
    ("playable", "review_adjusted"): "根据完整剧本收束微调了可玩视角：{names}",
    ("images", "brief_started"): "先统一这批插画的气质、镜头和配色…",
    ("images", "brief_pulse"): "正在统一这批插画的世界观、镜头和配色语言…",
    ("images", "brief_ready"): "视觉策略定好了，开始出世界图和角色头像",
    ("images", "started"): "正在根据世界观整理视觉方案，生成世界详情大图、列表图和角色头像…",
    ("images", "rendering_pulse"): "插画生成中，正在依次补全世界大图、列表图和角色头像…",
    ("images", "subtask_started"): "开始绘制 {subtask_total} 张插画…",
    ("images", "subtask_completed"): "「{label}」绘制完成 · {subtask_index}/{subtask_total}",
    ("images", "completed"): "完成了 {image_count} 张插画（含世界详情大图、列表图与角色头像）",
    ("images", "cover_completed"): "世界主视觉已生成，继续补全其余插画",
    ("images", "skipped"): "当前未配置生图能力，跳过插画生成",
    ("critic", "started"): "先做一轮发布前质检，看看还有没有明显短板…",
    ("critic", "review_pulse"): "审稿中，正在检查重复度、闭环、视角和结构强度…",
    ("critic", "completed"): "质检完成，当前结果已经达到发布线",
    ("critic", "repair_started"): "发现 {target_count} 处需要修正，先局部补强再继续…",
    ("critic", "repair_completed"): "局部修正完成，关键短板已经补上",
    ("critic", "repair_failed"): "局部修正后仍有遗留问题，先保留当前最好结果继续往下走",
    ("validating", "started"): "最后检查一下数据一致性…",
    ("validating", "completed"): "一切正常，数据校验通过",
    ("validating", "warnings"): "发现 {warning_count} 个小问题，已记录",
    ("script_base", "brief_started"): "先定一下剧本节奏、线索密度和结局体量…",
    ("script_base", "brief_pulse"): "正在平衡剧本节奏、线索密度和结局体量…",
    ("script_base", "brief_ready"): "剧本结构策略已定，开始搭核心秘密和主线",
    ("script_base", "started"): "正在构思剧本框架和核心秘密…",
    ("script_base", "drafting_pulse"): "主线已经起稿，正在收束核心秘密和调查入口…",
    ("script_base", "completed"): "剧本「{script_name}」框架完成",
    ("events", "started"): "正在编排事件链和线索…",
    ("events", "drafting_pulse"): "事件链已经铺开，正在把线索挂到关键节点上…",
    ("events", "completed"): "设计了 {event_count} 个事件和 {clue_count} 条线索",
    ("endings", "started"): "正在设计多条结局路线…",
    ("endings", "drafting_pulse"): "正在校准不同结局的门槛、反转力度和收束方式…",
    ("endings", "completed"): "设计了 {ending_count} 个结局（{ending_types}）",
    # === v2 新增 phase（与 world_creator_agent_v2.py _STAGE_INDEX 对齐） ===
    ("research_pack", "started"): "正在收集研究素材（备注 + 联网检索 + IP 知识）…",
    ("research_pack", "pulse"): "正在整理参考素材…",
    ("research_pack", "completed"): "研究素材整理完成",
    ("world_base", "subtask_completed"): "「{label}」已完成 · {subtask_index}/{subtask_total}",
    ("lore_dimensions", "started"): "正在拓展世界维度（时间 / 地理 / 文化 / 经济）…",
    ("lore_dimensions", "pulse"): "正在拓展世界各维度…",
    ("lore_dimensions", "completed"): "世界维度规划完成",
    ("character_roster", "started"): "正在规划人物阵容和身份…",
    ("character_roster", "pulse"): "正在校准角色身份和密度…",
    ("character_roster", "completed"): "人物阵容规划完成，准备进入角色档案创建",
    ("lore_pack", "started"): "正在生成世界设定（多维度并发）…",
    ("lore_pack", "subtask_completed"): "「{dim_label}」维度已完成 · {subtask_index}/{subtask_total}",
    ("lore_pack", "subtask_failed"): "世界设定有一个维度失败，已记录",
    ("lore_pack", "completed"): "世界设定生成完成",
    ("shared_events", "started"): "正在设计世界的共享历史事件…",
    ("shared_events", "pulse"): "正在编织共享历史的因果链…",
    ("shared_events", "completed"): "共享事件设计完成",
    ("relations_pack", "started"): "正在推导角色之间的关系网…",
    ("relations_pack", "completed"): "角色关系网构建完成",
    ("events_data", "started"): "正在生成事件数据（多种事件类型并发）…",
    ("events_data", "subtask_completed"): "「{title}」事件已完成 · {subtask_index}/{subtask_total}",
    ("events_data", "completed"): "事件数据生成完成",
    ("visual_brief", "started"): "正在构思视觉风格（镜头、色温、光线、材质）…",
    ("visual_brief", "pulse"): "正在统一视觉语言…",
    ("visual_brief", "completed"): "视觉构思完成，准备出图",
    # === v2 ip_research warnings ===
    ("ip_research", "ip_pack_underfilled"): (
        "《{ip_name}》的原作锚点抽取不足（仅 {character_count} 个角色），"
        "strict 约束将退化，建议改 loose 或重跑此世界。"
    ),
    ("ip_research", "ip_pack_no_must_have"): (
        "《{ip_name}》抽到 {character_count} 个角色但 must_have 全为 false，"
        "strict 约束注入失效，下游可能自由发挥。"
    ),
    # === v2 script 新增 ===
    ("script_visual_brief", "started"): "正在构思剧本视觉风格…",
    ("script_visual_brief", "completed"): "剧本视觉构思完成",
    ("script_images", "started"): "正在生成剧本海报…",
    ("script_images", "subtask_started"): "「{label}」开始绘制…",
    ("script_images", "subtask_completed"): "「{label}」绘制完成 · {subtask_index}/{subtask_total}",
    ("script_images", "completed"): "剧本海报生成完成",
}


class _SafeDict(dict):
    """dict that returns "" for missing keys — keeps str.format_map from raising
    when a template references a placeholder absent from the event meta."""

    def __missing__(self, key: str) -> str:  # noqa: D401
        return ""


def _render_message(phase: str, code: str, meta: dict[str, object]) -> str:
    template = FEEDBACK_TEMPLATES.get((phase, code))
    if not template:
        return str(meta.get("message", ""))
    # Flatten payload_summary into the top-level meta so subtask templates can
    # use {name} / {title} / {label} directly without subscript indexing.
    flat: dict[str, object] = dict(meta)
    payload_summary = meta.get("payload_summary")
    if isinstance(payload_summary, dict):
        for k, v in payload_summary.items():
            flat.setdefault(k, v)
    try:
        return template.format_map(_SafeDict(flat))
    except Exception:
        return template


def progress_event(phase: str, code: str, **meta: object) -> dict:
    return {
        "type": "progress",
        "phase": phase,
        "code": code,
        "message": _render_message(phase, code, meta),
        "meta": meta,
    }


def warning_event(phase: str, code: str, **meta: object) -> dict:
    return {
        "type": "warning",
        "phase": phase,
        "code": code,
        "message": _render_message(phase, code, meta),
        "meta": meta,
    }


def error_event(message: str, code: str = "generation_failed", phase: str = "general", **meta: object) -> dict:
    payload = {"message": message, **meta}
    return {
        "type": "error",
        "phase": phase,
        "code": code,
        "message": message,
        "meta": payload,
    }


def result_event(data: dict, partial: bool = False, completed_phases: list[str] | None = None) -> dict:
    event: dict = {"type": "result", **data}
    if partial:
        event["partial"] = True
        event["completed_phases"] = completed_phases or []
    return event


def done_event() -> dict:
    return {"type": "done"}
