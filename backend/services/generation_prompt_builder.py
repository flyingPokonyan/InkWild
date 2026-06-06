from __future__ import annotations

from schemas.generation_strategy import CharacterBrief, PlayableBrief, ScriptBrief, VisualBrief, WorldBrief


def _join_lines(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line)


def _existing_script_reference_block(existing_scripts: list[dict] | None) -> str:
    if not existing_scripts:
        return ""

    lines: list[str] = []
    for script in existing_scripts[:4]:
        name = str(script.get("name", "")).strip()
        if not name:
            continue
        description = str(script.get("description", "")).strip()
        secret = str(script.get("script_setting", "")).strip()
        event_names = "、".join(str(item).strip() for item in script.get("event_names", [])[:4] if str(item).strip())
        ending_types = "、".join(str(item).strip() for item in script.get("ending_types", [])[:4] if str(item).strip())

        lines.append(f"- 《{name}》：{description or '无简介'}")
        if secret:
            lines.append(f"  - 核心秘密：{secret[:120]}")
        if event_names:
            lines.append(f"  - 已用事件：{event_names}")
        if ending_types:
            lines.append(f"  - 结局类型：{ending_types}")

    return "\n".join(lines)


class GenerationPromptBuilder:
    def build_world_base_prompt(
        self,
        description: str,
        genre: str,
        era: str,
        world_brief: WorldBrief,
        reference_doc: str = "",
        repair_note: str = "",
    ) -> str:
        lines = [
            "请根据以下描述生成一个互动叙事世界的框架。",
            f"描述：{description}",
            f"类型：{genre or '不限'}",
            f"时代：{era or '不限'}",
            "",
            "## 世界生成策略",
            f"- 世界形态：{world_brief.world_shape or '由你综合判断'}",
            f"- 基调：{world_brief.tone or '与题材匹配'}",
            f"- 现实感：{world_brief.realism_level or '适中'}",
            f"- lore 密度：{world_brief.lore_density or '适中'}",
            f"- 核心冲突轴：{'、'.join(world_brief.conflict_axes) or '至少两条'}",
            f"- 地点目标数量：{world_brief.location_count_target}",
            f"- 世界张力目标数量：{world_brief.tension_count_target}",
            f"- 后续人物规模预期：{world_brief.npc_count_target}",
            f"- 游玩时长：{world_brief.playtime_band}",
        ]
        if reference_doc:
            lines.extend(["", "## 参考资料", reference_doc[:1600]])
        if repair_note:
            lines.extend(["", "## 修正要求", repair_note[:600]])
        lines.extend(
            [
                "",
                "## 输出要求",
                f"- 世界观设定详细，能支撑 {world_brief.playtime_band or '完整一局'} 的游玩",
                f"- 生成 {world_brief.location_count_target} 个左右的地点，每个都有独特功能和氛围",
                f"- 自由模式张力写 {world_brief.tension_count_target} 条左右，每行一条",
                "- 你必须调用 create_world_base 工具返回结果，不要输出纯文本",
            ]
        )
        return _join_lines(lines)

    def build_character_prompt(
        self,
        world_base: dict,
        character_brief: CharacterBrief,
        reference_doc: str = "",
        repair_note: str = "",
    ) -> str:
        location_names = ", ".join(loc.get("name", "") for loc in world_base.get("locations", []))
        lines = [
            f"世界名称：{world_base.get('name', '')}",
            f"世界设定：{str(world_base.get('base_setting', ''))[:700]}",
            f"地点列表：{location_names}",
            "",
            "## 人物系统策略",
            f"- 人物数量目标：{character_brief.count_target}",
            f"- 关系密度：{character_brief.relationship_density or '中等偏高'}",
            f"- 阵营数量：{character_brief.faction_count}",
            f"- 秘密浓度：{character_brief.secret_density or '每人不必都有显性秘密'}",
            f"- 信息分布：{character_brief.knowledge_distribution or '分散在不同人物手上'}",
            f"- 日程粒度：{character_brief.schedule_granularity}",
            f"- 原型组合：{'、'.join(character_brief.archetype_mix) or '按世界需要自由搭配'}",
            f"- 权力结构：{character_brief.power_distribution or '要有明显层次'}",
        ]
        if reference_doc:
            lines.extend(["", "参考资料：", reference_doc[:1200]])
        if repair_note:
            lines.extend(["", "修正要求：", repair_note[:600]])
        lines.extend(
            [
                "",
                "请为这个世界生成完整的人物表。",
                f"- 人物数尽量接近 {character_brief.count_target}",
                "- 确保能形成至少 2-3 组有意义的关系网",
                "- 每个人物必须和至少一个其他人物有明确关系",
                "- 每个人物有鲜明性格、秘密（可为空）、掌握的知识",
                "- 每个人物给出 voice_style（说话方式）：自称 / 称谓、句式特征、口头禅，并附 1-2 句范例台词，"
                "30-80 字。不同人物的嗓音要能明显区分开，避免千人一腔",
                "- 若参考资料表明本世界基于已知作品（IP 复刻）：对原作已有角色，personality 开头点明原作身份锚"
                "（如「《作品名》中的<角色名>，<一句话身份>」），voice_style 要贴合该角色在原作中的台词口吻与口头禅",
                "- 日程安排的 key 为时段（上午/下午/傍晚/夜晚/深夜），value 为地点名",
                "- initial_location 必须是上面地点列表中的某一个",
            ]
        )
        return _join_lines(lines)

    def build_playable_prompt(
        self,
        title: str,
        summary: str,
        characters: list[dict],
        playable_brief: PlayableBrief,
        script_mode: bool = False,
        repair_note: str = "",
    ) -> str:
        char_summary = "\n".join(f"- {c.get('name', '')}：{str(c.get('personality', ''))[:50]}" for c in characters)
        lines = [
            f"名称：{title}",
            f"摘要：{summary}",
            "",
            "人物列表：",
            char_summary,
            "",
            "## 可玩视角策略",
            f"- 核心推荐数量：{playable_brief.recommended_count_target}",
            f"- 整体开放上限参考：{playable_brief.playable_count_target}",
            f"- 视角组合：{'、'.join(playable_brief.viewpoint_mix) or '尽量形成差异化视角'}",
            f"- 能力分布：{playable_brief.ability_mix or '互补'}",
            f"- 剧透暴露上限：{playable_brief.spoiler_exposure_cap or '避免过早掌握核心真相'}",
            f"- 起始资源丰富度：{playable_brief.inventory_richness or '适中'}",
            f"- 差异维度：{'、'.join(playable_brief.role_diversity_axes) or '身份、信息、行动方式'}",
            "",
            f"请从中挑选适合作为{'该剧本' if script_mode else '玩家'}角色的人物。",
            f"- 请按推荐优先级从高到低返回，前 {playable_brief.recommended_count_target} 个必须是最值得开放的核心视角",
            f"- 核心推荐数量以 {playable_brief.recommended_count_target} 个左右为准，宁缺毋滥；不要为了凑数而选择功能重复的角色",
            f"- 只有当额外视角也具备同等级的可玩性时，才可以超过核心推荐数量；总数不要超过 {playable_brief.playable_count_target}",
            "- 优先推荐目标冲突鲜明、行动路线互补、信息分布合理、玩家体验差异明显的人物",
            "- 如果角色主要是旁观者、信息过少、剧透过重或与已有视角高度重复，不要选入",
            "- 视角必须彼此明显不同，能力或信息优势要能区分开",
            "- name 必须和人物列表中的名字完全一致",
        ]
        if repair_note:
            lines.extend(["", "## 修正要求", repair_note[:500]])
        return _join_lines(lines)

    def build_script_base_prompt(
        self,
        world_name: str,
        world_description: str,
        genre: str,
        era: str,
        world_setting: str,
        npc_summary: str,
        outline: str,
        script_brief: ScriptBrief,
        reference_doc: str = "",
        existing_scripts: list[dict] | None = None,
        repair_note: str = "",
    ) -> str:
        existing_script_block = _existing_script_reference_block(existing_scripts)
        lines = [
            f"世界名称：{world_name}",
            f"世界简介：{world_description[:160]}",
            f"世界类型：{genre or '不限'}",
            f"时代：{era or '不限'}",
            f"世界设定：{world_setting[:500]}",
            f"人物列表：\n{npc_summary}",
            f"故事大纲：{outline}",
            "",
            "## 剧本结构策略",
            f"- 剧本类型：{script_brief.script_type or '由你综合判断'}",
            f"- 线索密度：{script_brief.clue_density or '中等'}",
            f"- 揭示节奏：{script_brief.reveal_cadence or '逐步推进'}",
            f"- 红鲱鱼强度：{script_brief.red_herring_level or '适中'}",
            f"- 分支程度：{script_brief.branchiness or '适中'}",
            f"- 时间压力：{script_brief.time_pressure or '按剧情需要'}",
            f"- 玩家主动性：{script_brief.player_agency_level or '中等偏高'}",
        ]
        if reference_doc:
            lines.extend(["", "参考资料：", reference_doc[:1200]])
        if existing_script_block:
            lines.extend(
                [
                    "",
                    "## 同世界已有剧本概览",
                    existing_script_block,
                    "",
                    "## 避免重复要求",
                    "- 避免重复已有剧本的核心真相、幕后机制、主要反转和主事件编排",
                    "- 可以保留世界气质，但必须提供新的案件切口、调查路径和秘密结构",
                ]
            )
        if repair_note:
            lines.extend(["", "## 修正要求", repair_note[:700]])
        lines.extend(
            [
                "",
                "请生成剧本框架。",
                "- 如果用户没有提供明确故事大纲，你需要先自行提出一个适合该世界的核心案件/核心冲突，再展开完整剧本",
                "- script_setting 写出完整真相和核心秘密（200-400字），这些内容不会展示给玩家",
                "- 难度 1-5，预计游玩时长如「30-60分钟」",
            ]
        )
        return _join_lines(lines)

    def build_events_prompt(
        self,
        world_name: str,
        world_description: str,
        genre: str,
        era: str,
        world_setting: str,
        npc_summary: str,
        script_base: dict,
        script_brief: ScriptBrief,
        reference_doc: str = "",
        existing_scripts: list[dict] | None = None,
        repair_note: str = "",
    ) -> str:
        existing_script_block = _existing_script_reference_block(existing_scripts)
        lines = [
            f"世界名称：{world_name}",
            f"世界简介：{world_description[:160]}",
            f"世界类型：{genre or '不限'}",
            f"时代：{era or '不限'}",
            f"世界设定：{world_setting[:400]}",
            f"人物列表：\n{npc_summary}",
            f"剧本名称：{script_base.get('name', '')}",
            f"剧本简介：{script_base.get('description', '')}",
            f"核心秘密：{str(script_base.get('script_setting', ''))[:350]}",
            "",
            "## 事件链策略",
            f"- 事件目标数量：{script_brief.event_count_target}",
            f"- 线索密度：{script_brief.clue_density or '中等'}",
            f"- 揭示节奏：{script_brief.reveal_cadence or '逐步推进'}",
            f"- 红鲱鱼强度：{script_brief.red_herring_level or '适中'}",
            f"- 触发类型组合：{'、'.join(script_brief.trigger_type_mix) or 'time、clue、location 混合'}",
            f"- 玩家主动性：{script_brief.player_agency_level or '中等偏高'}",
        ]
        if reference_doc:
            lines.extend(["", "参考资料：", reference_doc[:1200]])
        if existing_script_block:
            lines.extend(
                [
                    "",
                    "## 同世界已有剧本概览",
                    existing_script_block,
                    "",
                    "## 避免重复要求",
                    "- 避免重复已有剧本已经使用过的主事件节奏、关键反转和调查推进方式",
                    "- 这次的线索挂载位置和事件链主骨架必须与已有剧本拉开明显差异",
                ]
            )
        if repair_note:
            lines.extend(["", "## 修正要求", repair_note[:700]])
        lines.extend(
            [
                "",
                "请生成事件链和线索。",
                f"- 事件数尽量接近 {script_brief.event_count_target}",
                "- 引用已有 NPC 和地点",
                "- 事件之间要有逻辑递进关系",
                "- 触发类型可使用：time、clue、location、clue_count、rounds_without_progress",
                "- 线索定义：key 为线索 ID，value 为描述",
            ]
        )
        return _join_lines(lines)

    def build_endings_prompt(
        self,
        world_name: str,
        script_base: dict,
        events: list[dict],
        script_brief: ScriptBrief,
        reference_doc: str = "",
        existing_scripts: list[dict] | None = None,
        repair_note: str = "",
    ) -> str:
        event_names = ", ".join(str(event.get("name", "?")) for event in events[:12])
        existing_script_block = _existing_script_reference_block(existing_scripts)
        lines = [
            f"世界名称：{world_name}",
            f"剧本名称：{script_base.get('name', '')}",
            f"核心秘密：{str(script_base.get('script_setting', ''))[:350]}",
            f"事件链：{event_names}",
            "",
            "## 结局策略",
            f"- 结局组合：{'、'.join(script_brief.ending_mix) or 'good、bad、timeout 等混合'}",
            f"- 结局目标数量：{script_brief.ending_count_target}",
            f"- 分支程度：{script_brief.branchiness or '适中'}",
            f"- 时间压力：{script_brief.time_pressure or '按剧情需要'}",
        ]
        if reference_doc:
            lines.extend(["", "参考资料：", reference_doc[:1000]])
        if existing_script_block:
            lines.extend(
                [
                    "",
                    "## 同世界已有剧本概览",
                    existing_script_block,
                    "",
                    "## 避免重复要求",
                    "- 避免复用已有剧本已经出现过的结局类型组合、收束逻辑和最后揭示方式",
                    "- 这次结局要和已有剧本形成新的成败分布与反转落点",
                ]
            )
        if repair_note:
            lines.extend(["", "## 修正要求", repair_note[:700]])
        lines.extend(
            [
                "",
                "请生成结局条件。",
                f"- 结局数尽量接近 {script_brief.ending_count_target}",
                f"- 优先覆盖这些结局类型：{'、'.join(script_brief.ending_mix) or 'good、normal、bad、hidden、timeout'}",
                "- hard_conditions 为可选的硬性判定条件（JSON 对象或 null）",
                "- soft_conditions 为 AI 判定的软性条件描述（字符串或 null）",
                "- priority 数值越高越优先判定",
            ]
        )
        return _join_lines(lines)

    def build_playable_review_prompt(
        self,
        title: str,
        summary: str,
        script_setting: str,
        endings: list[dict],
        characters: list[dict],
        provisional_playable: list[dict],
        playable_brief: PlayableBrief,
    ) -> str:
        ending_summary = "\n".join(
            f"- {item.get('ending_type', '?')}：{item.get('title', '')}"
            for item in endings[:6]
            if isinstance(item, dict)
        )
        provisional_summary = "\n".join(
            f"- {item.get('name', '')}：{item.get('description', '')}"
            for item in provisional_playable
            if isinstance(item, dict)
        )
        char_summary = "\n".join(
            f"- {char.get('name', '')}：{str(char.get('personality', ''))[:60]}"
            for char in characters[:10]
            if isinstance(char, dict)
        )
        lines = [
            f"剧本名称：{title}",
            f"剧本简介：{summary}",
            f"核心秘密：{script_setting[:220]}",
            "",
            "当前候选可玩角色：",
            provisional_summary or "- 暂无",
            "",
            "世界人物：",
            char_summary,
            "",
            "最终结局概览：",
            ending_summary or "- 暂无",
            "",
            "## 复检目标",
            f"- 核心推荐数量：{playable_brief.recommended_count_target}",
            f"- 总数不要超过：{playable_brief.playable_count_target}",
            "- 如果当前候选已经合理，请尽量保留，不要为了变化而变化",
            "- 只有在角色过度剧透、功能重复、体验差异不足时才调整",
            "- 返回最终可玩角色列表，并标记是否做了调整",
        ]
        return _join_lines(lines)

    def build_world_review_prompt(
        self,
        description: str,
        genre: str,
        era: str,
        world_base: dict,
        characters: list[dict],
        playable_data: list[dict],
    ) -> str:
        location_summary = "\n".join(
            f"- {loc.get('name', '')}：{str(loc.get('description', ''))[:80]}"
            for loc in world_base.get("locations", [])[:8]
            if isinstance(loc, dict)
        )
        character_summary = "\n".join(
            f"- {char.get('name', '')}：{str(char.get('personality', ''))[:60]}"
            for char in characters[:10]
            if isinstance(char, dict)
        )
        playable_summary = "\n".join(
            f"- {item.get('name', '')}：{item.get('description', '')}"
            for item in playable_data
            if isinstance(item, dict)
        )
        lines = [
            f"原始需求：{description}",
            f"类型：{genre or '不限'}",
            f"时代：{era or '不限'}",
            "",
            f"生成世界名称：{world_base.get('name', '')}",
            f"世界简介：{world_base.get('description', '')}",
            f"世界设定：{str(world_base.get('base_setting', ''))[:500]}",
            "",
            "地点：",
            location_summary or "- 暂无",
            "",
            "人物：",
            character_summary or "- 暂无",
            "",
            "可玩角色：",
            playable_summary or "- 暂无",
            "",
            "请作为高级世界编辑审稿。",
            "- 重点检查世界辨识度、地点功能区分、人物关系张力、可玩视角差异。",
            "- 只有当问题足以影响发布质量时才判定不通过。",
            "- 优先选择最小修复范围，不要轻易要求重做整个世界。",
            "- repair_targets 只允许选择：world_base、characters、playable。",
            "- repair_brief 用 1-3 句话明确说明怎么修。",
        ]
        return _join_lines(lines)

    def build_script_review_prompt(
        self,
        world_name: str,
        world_description: str,
        script_base: dict,
        events: list[dict],
        endings: list[dict],
        playable_data: list[dict],
        existing_scripts: list[dict] | None = None,
    ) -> str:
        existing_script_block = _existing_script_reference_block(existing_scripts)
        event_summary = "\n".join(
            f"- {event.get('name', '')}：{str(event.get('description', ''))[:80]}"
            for event in events[:10]
            if isinstance(event, dict)
        )
        ending_summary = "\n".join(
            f"- {ending.get('ending_type', '?')}：{ending.get('title', '')}"
            for ending in endings[:6]
            if isinstance(ending, dict)
        )
        playable_summary = "\n".join(
            f"- {item.get('name', '')}：{item.get('description', '')}"
            for item in playable_data
            if isinstance(item, dict)
        )
        lines = [
            f"世界名称：{world_name}",
            f"世界简介：{world_description[:180]}",
            f"剧本名称：{script_base.get('name', '')}",
            f"剧本简介：{script_base.get('description', '')}",
            f"核心秘密：{str(script_base.get('script_setting', ''))[:400]}",
            "",
            "事件链：",
            event_summary or "- 暂无",
            "",
            "结局：",
            ending_summary or "- 暂无",
            "",
            "可玩角色：",
            playable_summary or "- 暂无",
        ]
        if existing_script_block:
            lines.extend(["", "同世界已有剧本概览：", existing_script_block])
        lines.extend(
            [
                "",
                "请作为高级剧本编辑审稿。",
                "- 重点检查重复度、真相闭环、事件推进、线索充分性、结局收束和可玩视角质量。",
                "- 只有当问题足以影响发布质量时才判定不通过。",
                "- 优先选择最小修复范围，不要轻易要求整份重写。",
                "- repair_targets 只允许选择：script_base、events、endings、playable。",
                "- repair_brief 用 1-3 句话明确说明怎么修。",
            ]
        )
        return _join_lines(lines)

    def build_cover_prompt(self, world_base: dict, visual_brief: VisualBrief) -> str:
        return self.build_hero_prompt(world_base, visual_brief)

    def build_hero_prompt(self, world_base: dict, visual_brief: VisualBrief) -> str:
        tags = ", ".join(visual_brief.style_tags) or "cinematic, atmospheric, detailed environment"
        negatives = ", ".join(visual_brief.negative_tags) or "text, ui, watermark, logo"
        location_preview = ", ".join(
            str(loc.get("name", "")).strip()
            for loc in list(world_base.get("locations", []))[:4]
            if isinstance(loc, dict) and str(loc.get("name", "")).strip()
        )
        segments = [
            visual_brief.cover_subject or world_base.get("name", ""),
            str(world_base.get("description", ""))[:180],
            f"genre: {world_base.get('genre', '')}" if world_base.get("genre") else "",
            f"era: {world_base.get('era', '')}" if world_base.get("era") else "",
            f"key locations: {location_preview}" if location_preview else "",
            visual_brief.mood,
            visual_brief.palette,
            visual_brief.composition or "wide cinematic establishing shot",
            visual_brief.camera_language,
            tags,
            (
                "world-setting-first key art for the in-game world detail page, displayed as a near full-screen "
                "100% viewport hero background, immersive environment, layered depth, readable with interface "
                "overlay, characters are optional, environment and atmosphere should carry the image first, if "
                "people appear they must feel like natural inhabitants of the world, avoid staged poses, avoid "
                "forced gestures, avoid mandatory handheld props, 16:9 composition"
            ),
            f"consistency notes: {visual_brief.consistency_notes}" if visual_brief.consistency_notes else "",
            f"negative prompt: {negatives}",
        ]
        return ", ".join(segment for segment in segments if segment)

    def build_poster_prompt(
        self,
        world_base: dict,
        characters: list[dict],
        playable_data: list[dict],
        hook_map: dict[str, dict],
        visual_brief: VisualBrief,
    ) -> str:
        tags = ", ".join(visual_brief.style_tags) or "cinematic, atmospheric, detailed illustration"
        negatives = ", ".join(visual_brief.negative_tags) or "text, ui, watermark, logo"
        candidate_names = [
            str(item.get("name", "")).strip()
            for item in playable_data[:2]
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        if not candidate_names:
            candidate_names = [
                str(char.get("name", "")).strip()
                for char in characters[:2]
                if isinstance(char, dict) and str(char.get("name", "")).strip()
            ]

        optional_presence_bits: list[str] = []
        for name in candidate_names:
            hook = hook_map.get(name, {})
            summary = ", ".join(
                bit
                for bit in [
                    str(hook.get("appearance", "")).strip(),
                    str(hook.get("costume", "")).strip(),
                    str(hook.get("mood", "")).strip(),
                ]
                if bit
            )
            if summary:
                optional_presence_bits.append(summary)

        location_preview = ", ".join(
            str(loc.get("name", "")).strip()
            for loc in list(world_base.get("locations", []))[:3]
            if isinstance(loc, dict) and str(loc.get("name", "")).strip()
        )
        segments = [
            world_base.get("name", ""),
            str(world_base.get("description", ""))[:180],
            f"genre: {world_base.get('genre', '')}" if world_base.get("genre") else "",
            f"era: {world_base.get('era', '')}" if world_base.get("era") else "",
            f"optional inhabitant cues: {'; '.join(optional_presence_bits)}" if optional_presence_bits else "",
            f"signature locations: {location_preview}" if location_preview else "",
            visual_brief.mood,
            visual_brief.palette,
            visual_brief.composition,
            visual_brief.camera_language,
            tags,
            (
                "vertical poster key art for world lists, discovery cards, and admin thumbnails, world-setting-first "
                "composition, strong visual anchor, readable at thumbnail size, characters are optional, environment, "
                "architecture, symbols, weather, or naturally integrated inhabitants can carry the image, if people "
                "appear they must fit the world's background and era, avoid staged poses, avoid forced gestures, "
                "avoid mandatory handheld props, 3:4 composition"
            ),
            f"consistency notes: {visual_brief.consistency_notes}" if visual_brief.consistency_notes else "",
            f"negative prompt: {negatives}",
        ]
        return ", ".join(str(segment).strip() for segment in segments if str(segment).strip())

    def build_avatar_prompt(self, character: dict, hook_map: dict[str, dict], visual_brief: VisualBrief) -> str:
        hook = hook_map.get(character.get("name", ""), {})
        tags = ", ".join(visual_brief.style_tags) or "bust portrait, atmospheric lighting"
        negatives = ", ".join(visual_brief.negative_tags) or "text, ui, watermark"
        segments = [
            character.get("name", ""),
            hook.get("appearance", "") or str(character.get("personality", ""))[:100],
            hook.get("costume", ""),
            hook.get("mood", "") or visual_brief.mood,
            hook.get("motif", "") or character.get("initial_location", ""),
            visual_brief.palette,
            visual_brief.camera_language,
            tags,
            "natural portrait, grounded presence, clearly belongs to this world's era and setting, avoid exaggerated action pose",
            f"negative prompt: {negatives}",
        ]
        return ", ".join(str(segment).strip() for segment in segments if str(segment).strip())
