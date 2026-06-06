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
