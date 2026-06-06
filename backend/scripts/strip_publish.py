import asyncio
ADMIN = "fc13c915-a3fb-4500-abce-85830e8ae2eb"
STRIP = ["080d6245-54bd-4183-88ce-b4d65b134145"]  # A1安: 剥掉 disabled 事件
PUB = ["080d6245-54bd-4183-88ce-b4d65b134145", "6ab10a34-3a0a-437f-8f4d-4a64f5fcc747",
       "ac97dbd3-23d4-4301-abb6-6f73187efb0a", "8d078d9f-1564-4bd1-8a8f-0eb1d000c711"]
async def main():
    from api.admin import _get_generation_task_service
    from services.publish_service import publish_script_draft
    from models.draft import ScriptDraft
    from sqlalchemy.orm.attributes import flag_modified
    svc = _get_generation_task_service()
    for did in STRIP:
        async with svc.session_factory() as s:
            d = await s.get(ScriptDraft, did)
            p = dict(d.payload)
            evs = p.get("events_data") or []
            kept = [e for e in evs if not e.get("disabled")]
            print(f"[strip] {did[:8]}: {len(evs)}->{len(kept)} events", flush=True)
            p["events_data"] = kept
            d.payload = p
            flag_modified(d, "payload")
            await s.commit()
    for did in PUB:
        try:
            async with svc.session_factory() as s:
                sc = await publish_script_draft(s, draft_id=did, actor_user_id=ADMIN, audit_enabled=False)
            print(f"[pub] {did[:8]} -> {getattr(sc,'status','?')} | {getattr(sc,'name','?')}", flush=True)
        except Exception as e:
            print(f"[ERR] {did[:8]}: {type(e).__name__}: {str(e)[:140]}", flush=True)
    print("[DONE]", flush=True)
asyncio.run(main())
