from pydantic import BaseModel, Field, field_validator

from engine.input_sanitizer import strip_control_chars


class GameStartRequest(BaseModel):
    world_id: str
    character_id: str
    mode: str = "script"
    script_id: str | None = None
    authors_note: str | None = None
    # 自由模式「起点」选择：world.free_start_stages.stages[].id。仅自由模式有意义；
    # 为空 / 非自由模式 / 世界无起点预设 → 走老的固定 initial_location 开局。
    start_stage_id: str | None = None
    # 开新局前先放弃指定的旧局。前端在 start 页检测到同 (world, script/character)
    # 还有 active session 时，用户点「放弃旧的开新」会把那个 session id 传上来。
    force_abandon_session_id: str | None = None


class GameActionRequest(BaseModel):
    action_text: str = Field(max_length=2000)

    @field_validator("action_text", mode="before")
    @classmethod
    def strip_action_text_control_chars(cls, value: str) -> str:
        if isinstance(value, str):
            return strip_control_chars(value)
        return value

    @field_validator("action_text")
    @classmethod
    def reject_blank_action_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action_text cannot be empty")
        return value


class ClueDTO(BaseModel):
    id: str
    content: str
    found_at: str


class NpcRelationDTO(BaseModel):
    trust: int
    mood: str
    last_interaction: str


class GameStateDTO(BaseModel):
    current_time: str
    current_location: str
    player_inventory: list[str]
    discovered_clues: list[ClueDTO]
    npc_relations: dict[str, NpcRelationDTO]
    triggered_events: list[str]


class PathNode(BaseModel):
    time: str
    event: str
    summary: str
    impact: str = "neutral"


class GameStats(BaseModel):
    total_rounds: int
    clues_found: int
    clues_total: int
    play_duration_minutes: int


class GameSummaryResponse(BaseModel):
    ending_type: str
    ending_title: str
    ending_narrative: str
    path_review: list[PathNode]
    evidence_review: dict | None = None
    stats: GameStats


class GameHistoryItem(BaseModel):
    session_id: str
    # 前端 start 页查重需要：相同 (world_id, script_id) 或 (world_id, character_id, free)
    # 已有 active session 时弹「继续 / 放弃旧的开新」。
    world_id: str
    script_id: str | None = None
    character_id: str
    world_name: str
    # 剧本模式下用剧本自己的名字/封面（自由模式两者为 None，前端回落到世界封面）
    script_name: str | None = None
    script_cover_image: str | None = None
    character_name: str
    status: str
    ending_type: str | None
    started_at: str
    last_played_at: str
    cover_image: str | None = None
    rounds_played: int = 0
    current_time: str | None = None
    current_location: str | None = None
    mode: str | None = None
    genre: str | None = None
    era: str | None = None


class SessionMessageDTO(BaseModel):
    role: str
    content: str
    created_at: str


class GameSessionDetailResponse(BaseModel):
    session_id: str
    status: str
    world_name: str
    character_name: str
    character_description: str
    character_abilities: list[str]
    game_state: dict
    messages: list[SessionMessageDTO]
    mode: str = "script"
    script_type: str = "mystery"


class CaseBoardHistoryItem(BaseModel):
    id: int
    session_id: str
    round_number: int
    op_type: str
    path: list
    payload: dict
    before: dict | list | str | int | float | bool | None = None
    after: dict | list | str | int | float | bool | None = None
    reason: str | None = None
    created_at: str


class CaseBoardResponse(BaseModel):
    current: dict
    history: list[CaseBoardHistoryItem]
