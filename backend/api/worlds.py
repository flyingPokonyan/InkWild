from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user_optional, get_db
from models.script import Script
from models.user import User
from models.world import World, WorldCharacter
from schemas.world import CharacterDTO, ScriptDTO, WorldDetailResponse, WorldListItem
from services.world_image_fields import resolve_world_image_fields_from_model

router = APIRouter(prefix="/api/worlds", tags=["worlds"])


@router.get("")
async def list_worlds(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(World).where(World.status == "published").order_by(World.play_count.desc()))
    worlds = result.scalars().all()
    published_script_world_ids = set(
        (await db.execute(select(Script.world_id).where(Script.is_published.is_(True)))).scalars().all()
    )
    items = []
    for world in worlds:
        images = resolve_world_image_fields_from_model(world)
        items.append(
            WorldListItem(
                id=str(world.id),
                name=world.name,
                description=world.description,
                genre=world.genre,
                era=world.era,
                difficulty=world.difficulty,
                estimated_time=world.estimated_time,
                cover_image=images["cover_image"],
                hero_image=images["hero_image"],
                play_count=world.play_count,
                has_script=bool(world.script_setting) or world.id in published_script_world_ids,
            ).model_dump()
        )
    return {"code": 0, "data": items}


@router.get("/{world_id}")
async def get_world(
    world_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    world = await db.get(World, world_id)
    if not world:
        return {"code": 40001, "data": None, "message": "世界不存在"}

    # 私有/非公开世界仅 owner（或 admin）可取 —— 给私有预览/试玩用；其他人仍 404。
    viewer_id = str(current_user.id) if current_user else None
    is_admin = bool(current_user and current_user.is_admin)
    is_owner = viewer_id is not None and str(world.created_by_user_id) == viewer_id
    if world.status != "published" and not is_owner and not is_admin:
        return {"code": 40001, "data": None, "message": "世界不存在"}

    characters = (await db.execute(
        select(WorldCharacter)
        .where(WorldCharacter.world_id == world.id, WorldCharacter.playable.is_(True))
        .order_by(
            WorldCharacter.narrative_weight.desc(),
            WorldCharacter.created_at.asc(),
        )
    )).scalars().all()
    # 公开剧本对所有人可见；owner 还能看到自己的私有剧本（自己玩 script 模式），admin 看全部。
    script_q = (
        select(Script)
        .where(Script.world_id == world.id)
        .order_by(Script.created_at.desc())
    )
    if is_admin:
        pass
    elif is_owner:
        script_q = script_q.where(
            or_(Script.is_published.is_(True), Script.created_by_user_id == viewer_id)
        )
    else:
        script_q = script_q.where(Script.is_published.is_(True))
    scripts = (await db.execute(script_q)).scalars().all()
    images = resolve_world_image_fields_from_model(world)
    return {
        "code": 0,
        "data": WorldDetailResponse(
            id=str(world.id),
            name=world.name,
            description=world.description,
            genre=world.genre,
            era=world.era,
            difficulty=world.difficulty,
            estimated_time=world.estimated_time,
            cover_image=images["cover_image"],
            hero_image=images["hero_image"],
            free_setting=world.free_setting,
            has_script_mode=bool(world.script_setting) or len(scripts) > 0,
            characters=[
                CharacterDTO(
                    id=str(character.id),
                    name=character.name,
                    description=character.description or "",
                    abilities=character.abilities or [],
                    starting_location=character.initial_location,
                    starting_inventory=character.starting_inventory or [],
                    avatar=character.avatar,
                )
                for character in characters
            ],
            scripts=[
                ScriptDTO(
                    id=str(script.id),
                    name=script.name,
                    description=script.description,
                    difficulty=script.difficulty,
                    estimated_time=script.estimated_time,
                    cover_image=script.cover_image,
                    playable_character_ids=[str(cid) for cid in (script.playable_character_ids or [])],
                )
                for script in scripts
            ],
        ).model_dump(),
    }
