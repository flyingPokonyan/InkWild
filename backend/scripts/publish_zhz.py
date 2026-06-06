import asyncio
async def main():
    from api.admin import _get_generation_task_service
    from services.publish_service import publish_world_draft
    svc = _get_generation_task_service()
    async with svc.session_factory() as session:
        world = await publish_world_draft(
            session, draft_id="cc287ece-9708-4008-9279-7afdf91573ea",
            actor_user_id="fc13c915-a3fb-4500-abce-85830e8ae2eb", audit_enabled=False,
        )
        print("PUBLISHED id=", str(world.id), "name=", world.name, "status=", world.status)
asyncio.run(main())
