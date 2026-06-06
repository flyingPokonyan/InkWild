"""Backfill ``world_characters.voice_style`` for an existing world via a cheap LLM.

The IP research pipeline already extracts canon voice for newly-generated IP
worlds, and ``build_character_prompt`` now asks the generator for voice_style on
every new world. This script covers the gap for ALREADY-PUBLISHED worlds whose
characters predate the field.

For each character missing voice_style, a cheap realtime slot (npc_agent / flash)
infers a speech style from name + personality + the world's IP context (the
base_setting names the canon for IP-replica worlds). Additive and NULL-safe:
only fills empty rows unless --force; never touches personality. Spoiler-safe:
the prompt forbids leaking secrets / future plot.

Usage (inside the backend container so it reaches the DB):
    docker exec talealive-backend-1 python -m cli.backfill_voice_style \
        --world e9c87a8e-cde7-4229-9c4f-02d764c2a197 [--dry-run] [--force] [--limit N]

See docs/superpowers/specs/2026-06-01-npc-voice-style-ip-anchor-design.md §5.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import select

from database import async_session
from models.world import World, WorldCharacter
from services.model_management import resolve_slot_router

_SYSTEM = (
    "你是叙事角色的「声音设计师」。给定一个角色，输出它的 voice_style（说话方式）。"
    "只输出一个 JSON 对象：{\"voice_style\": \"...\"}，不要任何额外文字。\n"
    "voice_style 要求：30-80 字，写清【自称 / 对人称谓】【句式与语气特征】【口头禅】，"
    "并附 1-2 句**范例台词**。让这个角色的嗓音和别人明显区分开。\n"
    "若该角色出自已知作品（见世界设定），voice_style 要贴合其在原作中的台词口吻。\n"
    "严禁泄露角色秘密或剧透后续剧情；只写「怎么说话」，不写「知道什么」。"
)


def _build_user(world: World, char: WorldCharacter) -> str:
    ip_ctx = (world.base_setting or "")[:600]
    return (
        f"世界名称：{world.name}\n"
        f"世界设定（用于判断是否 IP 复刻、锁定原作口吻）：\n{ip_ctx}\n\n"
        f"角色名：{char.name}\n"
        f"角色性格：{char.personality or '（未填）'}\n\n"
        f"请输出该角色的 voice_style JSON。"
    )


async def _gen_voice_style(router, world: World, char: WorldCharacter) -> str | None:
    parts: list[str] = []
    async for ev in router.stream_json(
        messages=[{"role": "user", "content": _build_user(world, char)}],
        system=_SYSTEM,
        max_tokens=512,
    ):
        if ev.get("type") == "text_delta":
            parts.append(ev.get("text", ""))
    raw = "".join(parts).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    vs = str(data.get("voice_style") or "").strip()
    return vs or None


async def run(world_id: str, *, slot: str, force: bool, dry_run: bool, limit: int | None) -> int:
    async with async_session() as db:
        world = await db.get(World, world_id)
        if world is None:
            print(f"world {world_id} not found")
            return 2
        rows = (
            await db.execute(
                select(WorldCharacter).where(WorldCharacter.world_id == world_id)
            )
        ).scalars().all()

        targets = [c for c in rows if force or not (c.voice_style or "").strip()]
        if limit:
            targets = targets[:limit]
        print(
            f"[{world.name}] {len(rows)} characters, {len(targets)} to backfill "
            f"(force={force}, dry_run={dry_run}, slot={slot})"
        )

        router = await resolve_slot_router(db, slot)
        if router is None:
            print(f"no router for slot {slot}")
            return 2

        ok = 0
        for c in targets:
            try:
                vs = await _gen_voice_style(router, world, c)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {c.name}: gen failed: {exc}")
                continue
            if not vs:
                print(f"  ? {c.name}: empty / unparseable, skipped")
                continue
            print(f"  ✓ {c.name}: {vs[:70]}{'…' if len(vs) > 70 else ''}")
            if not dry_run:
                c.voice_style = vs
            ok += 1

        if not dry_run:
            await db.commit()
        print(f"done: {ok}/{len(targets)} filled{' (dry-run, not committed)' if dry_run else ''}")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", required=True)
    ap.add_argument("--slot", default="npc_agent")
    ap.add_argument("--force", action="store_true", help="overwrite non-empty voice_style")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    return asyncio.run(run(a.world, slot=a.slot, force=a.force, dry_run=a.dry_run, limit=a.limit))


if __name__ == "__main__":
    sys.exit(main())
