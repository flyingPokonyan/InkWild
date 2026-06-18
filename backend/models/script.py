import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, JSON, SmallInteger, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from utils import utcnow


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(SmallInteger, default=3)
    estimated_time: Mapped[str] = mapped_column(String(50), default="30-60 min")
    events_data: Mapped[list[dict]] = mapped_column(JSON, default=lambda _ctx=None: [])
    clues_data: Mapped[dict] = mapped_column(JSON, default=dict)
    endings_data: Mapped[list[dict]] = mapped_column(JSON, default=lambda _ctx=None: [])
    script_setting: Mapped[str] = mapped_column(Text, default="")
    playable_character_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 剧本「外挂角色」：本剧本需要、但所属世界名册里没有的 NPC（v2 反哺产物）。
    # 角色归剧本所有，世界一律不动 —— 发布剧本不会改 world_characters，避免越界/绕审核。
    # 运行时开局组 NPC 名册时与世界角色并集（全程 name 索引，无需 DB 行）。
    # 每项形状对齐 WorldCharacter 子集：name/personality/voice_style/secret/knowledge/
    # schedule/initial_location/description/narrative_weight/initial_peer_relations。
    # 将来「多剧本共用角色一键并入世界」功能据此识别来源。
    local_characters: Mapped[list[dict]] = mapped_column(JSON, default=list)
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    script_type: Mapped[str] = mapped_column(String(30), default="mystery")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="private", index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
