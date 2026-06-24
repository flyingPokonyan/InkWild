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


class FreeStartStagesDTO(BaseModel):
    # 这套阶段属于哪个可玩角色（其人生弧 = 整部传）。前端据此判断「选中的是不是主角」。
    protagonist_character_id: str
    stages: list[StartStageDTO] = []


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
