"""RelationsPack builder — 纯 Python 推导 NPC 关系，无 LLM 调用。

公共 API：
  build_relations_pack(characters, shared_events, ...) -> RelationsPack

逻辑：
  1. 来源 0：角色详情明确给出的 initial_peer_relations（保留 trust/kind）
  2. 来源 1：涉及自己的 shared_events → 对方列为 event_tied 关系
  3. 来源 2：同派系兜底（faction 非空，非自己）→ 同派系核心 NPC（前 max_faction_core_npcs）
  4. 来源 3：敌对派系兜底（显式 enemy_faction_pairs）→ 对方派系核心 NPC
  4. 去重 (target, kind)：同对方 + 同 kind 只保留第一个
  5. 不把自己加为自己的关系
"""
from __future__ import annotations

from collections import defaultdict

from schemas.character_v2 import Character
from schemas.shared_events import ImportantRelation, RelationsPack, SharedEvent


def build_relations_pack(
    characters: list[Character],
    shared_events: list[SharedEvent],
    *,
    same_faction_default_trust: int = 3,
    enemy_faction_default_trust: int = -3,
    enemy_faction_pairs: list[tuple[str, str]] | None = None,
    max_faction_core_npcs: int = 2,
) -> RelationsPack:
    """从 shared_events 和派系信息推导每个 NPC 的重要关系。

    纯 Python 实现，无 LLM 调用。

    Args:
        characters: 角色列表（按 roster 顺序）
        shared_events: 共享历史事件列表
        same_faction_default_trust: 同派系默认 trust 值
        enemy_faction_default_trust: 敌对派系默认 trust 值（通常为负数）
        enemy_faction_pairs: 显式敌对派系对，如 [("gangX", "gangY")]；可选
        max_faction_core_npcs: 每个派系最多取几个核心 NPC（按 roster 顺序）

    Returns:
        RelationsPack
    """
    enemy_faction_pairs = enemy_faction_pairs or []

    # 预计算：所有 character 名字集合（用于校验）
    char_names: set[str] = {c.name for c in characters}

    # 预计算：派系 → 核心 NPC 列表（按 roster 顺序，最多 max_faction_core_npcs）
    faction_core: dict[str, list[str]] = defaultdict(list)
    for char in characters:
        if char.faction:
            if len(faction_core[char.faction]) < max_faction_core_npcs:
                faction_core[char.faction].append(char.name)

    # 预计算：敌对派系对（双向）
    enemy_pairs_set: set[frozenset[str]] = set()
    for f1, f2 in enemy_faction_pairs:
        enemy_pairs_set.add(frozenset({f1, f2}))

    def _is_enemy_faction(f1: str, f2: str) -> bool:
        return bool(f1 and f2 and frozenset({f1, f2}) in enemy_pairs_set)

    # 构建每个 NPC 的 relations
    # 使用 dict 追踪 (target, kind) → 已存在，保留第一个
    relations_by_npc: dict[str, list[ImportantRelation]] = {}
    seen_by_npc: dict[str, set[tuple[str, str]]] = {}

    for char in characters:
        relations_by_npc[char.name] = []
        seen_by_npc[char.name] = set()

    def _add_relation(owner: str, rel: ImportantRelation) -> None:
        """去重后添加 relation；跳过 self。"""
        if rel.target == owner:
            return
        if rel.target not in char_names:
            return
        key = (rel.target, rel.kind)
        if key in seen_by_npc[owner]:
            return
        seen_by_npc[owner].add(key)
        relations_by_npc[owner].append(rel)

    # -----------------------------------------------------------------------
    # 来源 0：角色详情显式关系。关系详情模型比 shared-event 共现更能表达敌友与亲疏，
    # 必须进入最终 runtime relations_pack，不能只留在 character 卡片里。
    # -----------------------------------------------------------------------
    for char in characters:
        for rel in char.initial_peer_relations:
            _add_relation(
                char.name,
                ImportantRelation(
                    target=rel.target,
                    trust=rel.trust,
                    kind=rel.kind or "explicit",
                    why="character.initial_peer_relations",
                ),
            )

    # -----------------------------------------------------------------------
    # 来源 1：shared_events → event_tied 关系
    # -----------------------------------------------------------------------
    for event in shared_events:
        involved = event.involved_npcs
        for i, npc_a in enumerate(involved):
            if npc_a not in relations_by_npc:
                continue
            for npc_b in involved:
                if npc_b == npc_a:
                    continue
                _add_relation(
                    npc_a,
                    ImportantRelation(
                        target=npc_b,
                        trust=0,
                        kind="event_tied",
                        why=event.id,
                    ),
                )

    # -----------------------------------------------------------------------
    # 来源 2：同派系兜底
    # -----------------------------------------------------------------------
    for char in characters:
        if not char.faction:
            continue
        core_npcs = faction_core[char.faction]
        for peer in core_npcs:
            if peer == char.name:
                continue
            _add_relation(
                char.name,
                ImportantRelation(
                    target=peer,
                    trust=same_faction_default_trust,
                    kind="同派系",
                    why=f"faction:{char.faction}",
                ),
            )

    # -----------------------------------------------------------------------
    # 来源 3：敌对派系兜底
    # -----------------------------------------------------------------------
    for char in characters:
        if not char.faction:
            continue
        for other_faction, core_npcs in faction_core.items():
            if other_faction == char.faction:
                continue
            if not _is_enemy_faction(char.faction, other_faction):
                continue
            for peer in core_npcs:
                if peer == char.name:
                    continue
                _add_relation(
                    char.name,
                    ImportantRelation(
                        target=peer,
                        trust=enemy_faction_default_trust,
                        kind="敌对派系",
                        why=f"faction:{other_faction}",
                    ),
                )

    return RelationsPack(relations_by_npc=relations_by_npc)
