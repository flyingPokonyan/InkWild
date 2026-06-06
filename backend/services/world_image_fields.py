from __future__ import annotations


def _clean_image_url(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def resolve_world_image_fields(
    *,
    cover_image: object = "",
    hero_image: object = "",
) -> dict[str, str]:
    cover = _clean_image_url(cover_image)
    hero = _clean_image_url(hero_image)

    if not hero:
        hero = cover
    if not cover:
        cover = hero

    return {"cover_image": cover, "hero_image": hero}


def resolve_world_image_fields_from_mapping(data: dict | None) -> dict[str, str]:
    payload = data or {}
    return resolve_world_image_fields(
        cover_image=payload.get("cover_image"),
        hero_image=payload.get("hero_image"),
    )


def resolve_world_image_fields_from_model(world: object) -> dict[str, str]:
    return resolve_world_image_fields(
        cover_image=getattr(world, "cover_image", ""),
        hero_image=getattr(world, "hero_image", ""),
    )
