import asyncio, sys
ADMIN = "fc13c915-a3fb-4500-abce-85830e8ae2eb"
async def main():
    from api.admin import _get_generation_task_service
    from services.publish_service import publish_script_draft
    svc = _get_generation_task_service()
    for did in sys.argv[1:]:
        try:
            async with svc.session_factory() as s:
                sc = await publish_script_draft(s, draft_id=did, actor_user_id=ADMIN, audit_enabled=False)
            print(f"[pub] {did[:8]} -> {getattr(sc,'status','?')} | {getattr(sc,'name','?')}", flush=True)
        except Exception as e:
            print(f"[ERR] {did[:8]}: {type(e).__name__}: {str(e)[:140]}", flush=True)
    print("[DONE]", flush=True)
asyncio.run(main())
