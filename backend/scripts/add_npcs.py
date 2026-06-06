"""给已发布的紫禁深宫世界补一批 canonical 配角 NPC（不可玩、无头像），
让剧本事件能引用这些角色（否则事件被标 disabled、发布被拒）。"""
import asyncio

WORLD = "e9c87a8e-cde7-4229-9c4f-02d764c2a197"

# name, personality, secret, knowledge[], initial_location
NPCS = [
    ("静白师太", "甘露寺主持，势利刻薄，苛待落难妃嫔，对权贵谄媚。", "暗中受人指使为难修行的甄嬛。",
     ["知道甘露寺的人事往来", "知道哪些香客有来头"], "甘露寺"),
    ("夏冬春", "新晋秀女，恃宠骄横、不懂规矩，口无遮拦，仗着家世顶撞华妃。", "并不知道华妃下手有多狠。",
     ["知道新入宫秀女间的攀比", "自以为有家世撑腰"], "碎玉轩"),
    ("余莺儿", "冒名顶替倚梅园小主得宠，嚣张跋扈，攀附华妃。", "除夕夜在倚梅园唱曲的并非她，她窃取了甄嬛的机缘。",
     ["知道自己出身低微", "知道华妃可作靠山"], "翊坤宫"),
    ("剪秋", "皇后心腹宫女，忠心耿耿、手段狠辣，为皇后做见不得光的脏活。", "曾奉皇后之命参与下毒害妃。",
     ["知道皇后许多隐秘指令", "知道景仁宫的暗道与药物"], "景仁宫"),
    ("颂芝", "华妃贴身大宫女，仗主人之势张扬跋扈，对华妃绝对忠心。", "知道欢宜香每日的取用，但不知其害。",
     ["知道华妃的喜恶与日常", "知道翊坤宫人事"], "翊坤宫"),
    ("周宁海", "皇后身边的太监，阴鸷寡言、唯命是从。", "替皇后传递与执行许多隐秘差事。",
     ["知道皇后的部分密令", "熟悉宫中太监网络"], "景仁宫"),
    ("斐雯", "储秀宫宫女，胆小易被收买，曾被皇后党拉拢。", "受祺贵人与皇后指使，准备作伪证构陷甄嬛。",
     ["知道自己被谁收买", "知道构陷的部分安排"], "碎玉轩"),
    ("康禄海", "华妃宫中的太监总管，势利圆滑，看人下菜。", "替华妃党经手过一些不光彩的差事。",
     ["熟悉翊坤宫的进出与采买", "知道华妃党的部分动向"], "翊坤宫"),
    ("小允子", "甄嬛身边的小太监，忠心机灵、跑腿打探消息很在行。", "私下为甄嬛留意各宫风声。",
     ["熟悉宫中各处路径", "能打探到下层消息"], "碎玉轩"),
    ("佩儿", "甄嬛宫中的宫女，老实本分、做事勤谨。", None,
     ["知道碎玉轩的日常起居"], "碎玉轩"),
]


async def main():
    from api.admin import _get_generation_task_service
    from models.world import WorldCharacter

    svc = _get_generation_task_service()
    added = 0
    async with svc.session_factory() as s:
        from sqlalchemy import select
        existing = {
            r for (r,) in (await s.execute(
                select(WorldCharacter.name).where(WorldCharacter.world_id == WORLD)
            )).all()
        }
        for name, personality, secret, knowledge, loc in NPCS:
            if name in existing:
                print(f"[skip] {name} 已存在")
                continue
            sched = {"morning": loc, "afternoon": loc, "evening": loc, "night": loc}
            wc = WorldCharacter(
                world_id=WORLD, name=name, personality=personality, secret=secret,
                knowledge=knowledge, schedule=sched, initial_location=loc,
                playable=False, abilities=[], starting_inventory=[],
                mode="both", gender="", narrative_weight=30,
                description=None, initial_peer_relations=[],
            )
            s.add(wc)
            added += 1
            print(f"[add] {name} @ {loc}")
        await s.commit()
    print(f"[DONE] added={added}")


if __name__ == "__main__":
    asyncio.run(main())
