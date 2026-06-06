"""Headless 甄嬛传 world generation (strict IP fidelity).

Run inside backend container:
  python -m scripts.gen_zhenhuanzhuan a   # phase_a: IP recognition smoke gate
  python -m scripts.gen_zhenhuanzhuan b   # phase_b: full strict generation (long)

State (draft_id, ip_recognition, task ids) persists in /tmp/zhz_state.json.
"""
import asyncio
import json
import sys

STATE = "/tmp/zhz_state.json"
ADMIN = "fc13c915-a3fb-4500-abce-85830e8ae2eb"  # Pokonyan, is_admin
DESC = (
    "电视剧《后宫·甄嬛传》，清雍正年间紫禁城后宫。高度忠实复刻原著的人物（甄嬛、皇后宜修、"
    "华妃年世兰、沈眉庄、安陵容、端妃、敬妃、叶澜依、曹琴默、果郡王允礼、温实初、苏培盛、崔槿汐、"
    "皇帝、太后等）、宫殿地点（翊坤宫、景仁宫、碎玉轩、咸福宫、延禧宫、养心殿、寿康宫、御花园、"
    "甘露寺、太医院、慎刑司等）、派系（皇后党/华妃党/甄嬛党）与剧情背景。"
)


def _load():
    with open(STATE) as f:
        return json.load(f)


def _save(d):
    with open(STATE, "w") as f:
        json.dump(d, f, ensure_ascii=False)


async def phase_a():
    from api.admin import _get_generation_task_service
    from services.generation_task_service import PHASE_A

    svc = _get_generation_task_service()
    print("[phase_a] starting IP recognition...", flush=True)
    draft_id, task_a = await svc.start_world_generation(
        description=DESC, user_id=ADMIN, phase=PHASE_A
    )
    await svc._run_world_generation(task_a)
    t = await svc.get_task(task_a)
    rec = (t.intermediate_state or {}).get("ip_recognition") or {}
    print("[phase_a] draft_id=", draft_id, flush=True)
    print("[phase_a] recognition=", json.dumps(rec, ensure_ascii=False), flush=True)
    _save({"draft_id": draft_id, "task_a": task_a, "rec": rec})
    kind, conf = rec.get("kind"), rec.get("confidence", 0)
    if kind != "known_ip":
        print(f"[GATE-FAIL] kind={kind} conf={conf}; do NOT run phase_b", flush=True)
        sys.exit(2)
    print(f"[GATE-OK] known_ip conf={conf}; safe to run phase_b", flush=True)


async def phase_b():
    from api.admin import _get_generation_task_service

    st = _load()
    svc = _get_generation_task_service()
    print(f"[phase_b] strict generation on draft {st['draft_id']} ...", flush=True)
    task_b = await svc.start_world_phase_b_task(
        draft_id=st["draft_id"],
        description=DESC,
        user_id=ADMIN,
        ip_recognition=st["rec"],
        fidelity_mode="strict",
    )
    st["task_b"] = task_b
    _save(st)
    print(f"[phase_b] task_b={task_b} (poll generation_tasks for live phase)", flush=True)
    await svc._run_world_generation(task_b)

    tb = await svc.get_task(task_b)
    print("[phase_b] final status=", getattr(tb, "status", "?"), flush=True)
    from models.draft import WorldDraft

    async with svc.session_factory() as s:
        d = await s.get(WorldDraft, st["draft_id"])
        payload = (d.payload if d else {}) or {}
    chars = payload.get("world_characters") or payload.get("characters") or []
    playable = [c for c in chars if c.get("playable")]
    print(f"[DONE] draft={st['draft_id']} total_chars={len(chars)} playable={len(playable)}", flush=True)
    print("[playable]", json.dumps([c.get("name") for c in playable], ensure_ascii=False), flush=True)
    print("[all_chars]", json.dumps([c.get("name") for c in chars], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "a"
    asyncio.run(phase_a() if mode == "a" else phase_b())
