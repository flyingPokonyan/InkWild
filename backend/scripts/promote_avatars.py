"""Promote chosen 甄嬛传 characters to playable + generate IP-anchored avatars.

Edits the world draft payload in place:
  - payload['playable']: list of {name, role_tag, description} (publish derives playable flag from this)
  - payload['character_images'][name] = url  (publish derives avatar from this)
  - world_characters[].playable/is_image_target/avatar kept in sync for draft editor

Run inside backend container: python -m scripts.promote_avatars
"""
import asyncio
import json

from sqlalchemy.orm.attributes import flag_modified

DRAFT = "cc287ece-9708-4008-9279-7afdf91573ea"
PLAYABLE = [
    "甄嬛", "沈眉庄", "安陵容", "华妃年世兰", "皇后宜修",
    "端妃", "敬妃", "果郡王允礼", "温实初",
]


async def main():
    from api.admin import _get_generation_task_service, _build_generation_world_creator_agent
    from services.cover_brief_helper import derive_world_cover_brief
    from services.cover_brief import build_character_portrait_prompt
    from services.world_creator_agent_v2 import _generate_image_with_fallback
    from services.image_storage import get_image_storage, make_image_key
    from services.ip_recognizer import IPRecognition
    from models.draft import WorldDraft

    svc = _get_generation_task_service()
    agent = _build_generation_world_creator_agent()
    if asyncio.iscoroutine(agent):
        agent = await agent
    llm, image_gen, storage = agent.llm, agent.image_gen, get_image_storage()

    rec = json.load(open("/tmp/zhz_state.json"))["rec"]
    rec_obj = IPRecognition(
        kind=rec.get("kind", "known_ip"), ip_name=rec.get("ip_name"),
        ip_type=rec.get("ip_type"), one_liner=rec.get("one_liner"),
        confidence=rec.get("confidence", 1.0), source_hints=rec.get("source_hints", []),
    )

    async with svc.session_factory() as session:
        draft = await session.get(WorldDraft, DRAFT)
        payload = dict(draft.payload)
        chars = payload.get("world_characters", [])
        by_name = {c["name"]: c for c in chars}
        char_images = dict(payload.get("character_images") or {})

        # which playable chars still lack an avatar
        need = [n for n in PLAYABLE if n in by_name and not char_images.get(n) and not by_name[n].get("avatar")]
        print("[plan] playable=", PLAYABLE)
        print("[plan] need avatars=", need, flush=True)

        # briefs for the avatar-needing chars
        char_inputs = [
            {"name": by_name[n]["name"], "role_tag": by_name[n].get("role_tag", ""),
             "personality": by_name[n].get("personality", ""), "gender": by_name[n].get("gender", ""),
             "is_image_target": True}
            for n in need
        ]
        cover_brief, char_briefs = await derive_world_cover_brief(
            world_data=payload, characters=char_inputs, recognition=rec_obj, ip_pack=None, llm=llm,
        )
        print("[brief] world=", getattr(cover_brief, "world_name", "?"), "ip=", getattr(cover_brief, "ip_name", "?"), flush=True)

        async def gen(n):
            cb = char_briefs.get(n)
            if cb is None:
                print(f"[skip] no brief for {n}"); return n, None
            prompt = build_character_portrait_prompt(cover_brief, cb)
            url, _ = await _generate_image_with_fallback(
                image_gen, [prompt], aspect_ratio="2:3", storage=storage,
                storage_key=make_image_key("characters", n), log_key="npc:" + n,
            )
            print(f"[avatar] {n} -> {url}", flush=True)
            return n, url

        results = await asyncio.gather(*[gen(n) for n in need])
        for n, url in results:
            if url:
                char_images[n] = url
                by_name[n]["avatar"] = url

        # stamp playable + is_image_target on world_characters; rebuild playable list
        for n in PLAYABLE:
            if n in by_name:
                by_name[n]["playable"] = True
                by_name[n]["is_image_target"] = True
        payload["playable"] = [
            {"name": by_name[n]["name"], "role_tag": by_name[n].get("role_tag", ""),
             "description": by_name[n].get("description", "")}
            for n in PLAYABLE if n in by_name
        ]
        payload["character_images"] = char_images
        payload["world_characters"] = chars
        draft.payload = payload
        flag_modified(draft, "payload")
        await session.commit()

    have = sum(1 for n in PLAYABLE if char_images.get(n))
    print(f"[DONE] playable={len(payload['playable'])} avatars_for_playable={have}/{len(PLAYABLE)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
