import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, SmallInteger, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

_JSONB = JSON().with_variant(JSONB(), "postgresql")

from database import Base
from utils import utcnow


class World(Base):
    __tablename__ = "worlds"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    genre: Mapped[str] = mapped_column(String(50))
    era: Mapped[str] = mapped_column(String(50))
    difficulty: Mapped[int] = mapped_column(SmallInteger)
    estimated_time: Mapped[str] = mapped_column(String(50))
    cover_image: Mapped[str] = mapped_column(String(500), default="")  # 3:2, server-cropped from hero_image
    hero_image: Mapped[str] = mapped_column(String(500), default="")  # 21:9, source-of-truth
    base_setting: Mapped[str] = mapped_column(Text)
    locations_data: Mapped[list[dict]] = mapped_column(JSON, default=lambda _ctx=None: [])
    script_setting: Mapped[str | None] = mapped_column(Text, nullable=True)
    free_setting: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="private")
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    free_playable_character_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    lore_pack: Mapped[dict | None] = mapped_column(_JSONB, nullable=True, default=None)
    shared_events: Mapped[list | None] = mapped_column(_JSONB, nullable=True, default=None)
    events_data: Mapped[list | None] = mapped_column(_JSONB, nullable=True, default=None)
    # 自由模式「人生进度」起点预设（spec docs/plans/2026-06-24-free-start-stages.md）。
    # 形如 {"protagonist_character_id": str, "stages": [{id, milestone, subtitle,
    # tagline, order, era, start_location, opening_framing, known_relations:[{npc,standing}]}]}。
    # None / 缺省 = 该世界不提供起点选择，自由模式走老的「固定 initial_location」开局。
    free_start_stages: Mapped[dict | None] = mapped_column(_JSONB, nullable=True, default=None)
    created_by_user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class NPC(Base):
    """Legacy table — kept temporarily for migration. Use WorldCharacter instead."""
    __tablename__ = "npcs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"))
    name: Mapped[str] = mapped_column(String(50))
    personality: Mapped[str] = mapped_column(Text)
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge: Mapped[list[str]] = mapped_column(JSON, default=list)
    schedule: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    initial_location: Mapped[str] = mapped_column(String(100))


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"))
    name: Mapped[str] = mapped_column(String(100))
    trigger_type: Mapped[str] = mapped_column(String(50))
    trigger_condition: Mapped[dict] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(Text)
    effects: Mapped[dict] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(20), default="both")
    priority: Mapped[int] = mapped_column(SmallInteger, default=0)


class Character(Base):
    """Legacy table — kept temporarily for migration. Use WorldCharacter instead."""
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"))
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    abilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    starting_location: Mapped[str] = mapped_column(String(100))
    starting_inventory: Mapped[list[str]] = mapped_column(JSON, default=list)
    mode: Mapped[str] = mapped_column(String(20), default="both")


class Ending(Base):
    __tablename__ = "endings"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"))
    ending_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(SmallInteger, default=0)
    hard_conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    soft_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="script_only")
    # 3:2 ending card image — produced by the cover_brief pipeline.
    # NULL when generation failed or not yet generated; front-end falls back
    # to text-only ending display.
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)


class WorldCharacter(Base):
    __tablename__ = "world_characters"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    world_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("worlds.id"), index=True)
    name: Mapped[str] = mapped_column(String(50))

    # NPC-level info (all characters have this)
    personality: Mapped[str] = mapped_column(Text, default="")
    # Canonical / authored speech style (称谓、句式、口头禅、范例台词). IP worlds seed
    # this from the IPKnowledgePack voice_style+tone_lingo; original worlds have the
    # generator produce it. Injected into the NPC system prompt's STABLE prefix at
    # runtime. NULL on legacy rows → no voice block (byte-identical to before).
    # See spec 2026-06-01-npc-voice-style-ip-anchor.
    voice_style: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge: Mapped[list[str]] = mapped_column(JSON, default=list)
    schedule: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    initial_location: Mapped[str] = mapped_column(String(100), default="")
    # "男" / "女" / "" — empty means unset (admin can fill later); used by
    # cover_brief portrait pipeline for original-world characters. For known
    # IP characters, reference_anchor (from IP pack) takes priority and this
    # field may stay empty.
    gender: Mapped[str] = mapped_column(String(10), default="")

    # Playable character info (meaningful when playable=True)
    playable: Mapped[bool] = mapped_column(default=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    abilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    starting_inventory: Mapped[list[str]] = mapped_column(JSON, default=list)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)

    mode: Mapped[str] = mapped_column(String(20), default="both")
    # NPC-2 — initial NPC↔NPC relations seeded into ``npc_relations`` at
    # session start. List of {target, trust, label, history_summary}; nullable
    # so older worlds (and characters with no notable peer ties) stay valid.
    initial_peer_relations: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    # 0-100 importance score. ``api/worlds.get_world`` sorts characters by this
    # so the protagonist surfaces first. Derived at publish from role_tag /
    # is_image_target signals; 0 = legacy rows (sort last).
    narrative_weight: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
