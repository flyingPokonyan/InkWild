from pydantic import BaseModel


class CharacterDTO(BaseModel):
    id: str
    name: str
    description: str
    abilities: list[str]
    starting_location: str
    starting_inventory: list[str]
    avatar: str | None = None


class ScriptDTO(BaseModel):
    id: str
    name: str
    description: str
    difficulty: int
    estimated_time: str
    cover_image: str | None = None
    # WorldCharacter UUID 列表。非空 = 该剧本仅这些角色可玩；空 = 放行世界全部可玩角色。
    playable_character_ids: list[str] = []


class StartStageRelationDTO(BaseModel):
    npc: str
    standing: str = ""


class StartStageDTO(BaseModel):
    id: str
    milestone: str  # 进度里程碑（炼气期 / 熹贵妃）——行标题主体
    subtitle: str = ""  # 情境定位（七玄门少年）
    tagline: str = ""  # 节奏取向（爽感流，开局就有分量）
    order: int = 0
    start_location: str = ""
    opening_framing: str = ""
    known_relations: list[StartStageRelationDTO] = []


class CharacterStartStagesDTO(BaseModel):
    # 这套阶段属于哪个可玩角色。一个世界可有多个弧线角色各配一套阶段。
    character_id: str
    stages: list[StartStageDTO] = []


class FreeStartStagesDTO(BaseModel):
    characters: list[CharacterStartStagesDTO] = []


def normalize_free_start_stages(raw: object) -> dict | None:
    """把 world.free_start_stages 归一成消费侧形状 {"characters": [{character_id, stages}]}。

    兼容两代存储形状：
    - 新（多角色）：{"characters": [{"character_id": ..., "stages": [...]}]}
    - 旧（单主角，存量 backfill 数据）：{"protagonist_character_id": ..., "stages": [...]}
    无效 / 空 → None。读侧（API DTO、start_game）统一走这里，存量数据不迁移。
    """
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("characters"), list):
        entries = [
            e for e in raw["characters"]
            if isinstance(e, dict) and e.get("character_id") and isinstance(e.get("stages"), list) and e["stages"]
        ]
        return {"characters": entries} if entries else None
    if raw.get("protagonist_character_id") and isinstance(raw.get("stages"), list) and raw["stages"]:
        return {
            "characters": [
                {"character_id": raw["protagonist_character_id"], "stages": raw["stages"]}
            ]
        }
    return None


class WorldListItem(BaseModel):
    id: str
    name: str
    description: str
    genre: str
    era: str
    difficulty: int
    estimated_time: str
    cover_image: str
    hero_image: str
    play_count: int
    has_script: bool


class WorldDetailResponse(BaseModel):
    id: str
    name: str
    description: str
    genre: str
    era: str
    difficulty: int
    estimated_time: str
    cover_image: str
    hero_image: str
    free_setting: str | None
    has_script_mode: bool
    characters: list[CharacterDTO]
    scripts: list[ScriptDTO]
    # 自由模式起点预设；None = 该世界不提供起点选择。
    free_start_stages: FreeStartStagesDTO | None = None
