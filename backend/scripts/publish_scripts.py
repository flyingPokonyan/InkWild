import asyncio
ADMIN = "fc13c915-a3fb-4500-abce-85830e8ae2eb"
GOOD = [
    ("华妃争锋篇", "f3290f08-3391-4158-9f82-baf3e6f12cf7"),
    ("滴血验亲",   "aa75ace9-53aa-4034-ad0b-0f1ff5b9eadd"),
    ("熹妃回宫",   "ae80407f-b55d-4f48-82d7-7b6937f454ac"),
    ("甘露青丝断", "936992b2-01cc-420e-8212-3ccce7c9fb6e"),
    ("枫红一丈",   "c35354d1-fdcd-46c6-8394-dec85324f3ca"),
    ("纯元旧衣",   "9a12dcee-9f8f-4d74-afd8-25c7174d4cdd"),
    ("砒霜旧案",   "e67e24fc-e1b0-43ac-860e-62e5ef236a9c"),
]
async def main():
    from api.admin import _get_generation_task_service
    from services.publish_service import publish_script_draft
    svc = _get_generation_task_service()
    for label, did in GOOD:
        try:
            async with svc.session_factory() as s:
                sc = await publish_script_draft(s, draft_id=did, actor_user_id=ADMIN, audit_enabled=False)
            print(f"[pub] {label} -> {getattr(sc,'status','?')} id={getattr(sc,'id','?')}", flush=True)
        except Exception as e:
            print(f"[ERR] {label}: {type(e).__name__}: {str(e)[:160]}", flush=True)
    print("[ALL_PUB_DONE]", flush=True)
asyncio.run(main())
