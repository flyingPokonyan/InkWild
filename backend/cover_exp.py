"""Cover style A/B: new (插画地基) vs old (写实) prompts, 3:2, concurrent."""
import asyncio
import time
import urllib.request
from pathlib import Path

from database import async_session
from services.cover_brief import (
    CoverBrief,
    build_world_cover_prompt,  # NEW prompt (current code = 插画地基)
    _DARK_UI_HINT,
    _LOGO_NEGATIVE,
    _mood_clause,
    _world_subject_and_essence,
)
from services.model_management import resolve_slot_image_generator

OUT = Path("/tmp/cover_exp")
OUT.mkdir(exist_ok=True)

# --- OLD (写实) house style — verbatim from pre-2026-06-26 ---
_OLD_HOUSE = (
    "InkWild 统一的是陈列纪律，不是把所有题材画成同一种风格："
    "干净、克制、低噪点、低 AI 感、单一焦点、真实材质，适合深色香槟金 UI 陈列。"
    "允许每个世界保留自己的色温、美术方向、时代质感和情绪；"
    "画面可以通透清爽，但不要为了明亮清新而改写阴郁、恐怖、诡秘、宫廷或末日题材的原本气质。"
    "避免二游立绘、网文封面、游戏宣传图、廉价 stock photo、塑料皮肤、"
    "过度锐化、过饱和蓝紫能量光、漂浮碎片和泛 AI fantasy glow。"
)
_OLD_COHESION = (
    "整体呈现影视级 key art / 高级剧照式主视觉的质感：构图讲究、有明确视觉主体、"
    "戏剧性的光影与景深，精致考究、有高级感。"
    "保持单一、浑然一体的画面与统一焦点，主体控制在 1-2 个核心意象，留出呼吸感；"
    "不要把多个标志性元素拼贴、分屏、堆叠成大杂烩，也不要做商业海报式文字排版。"
)


def _old_fidelity(brief: CoverBrief) -> str:
    ip = (brief.ip_name or "").strip()
    if ip:
        return (
            f"原作/已知 IP 识别优先：必须保留《{ip}》的时代质感、题材气质、"
            "人物关系、核心意象、服饰建筑和材质语言；"
            "InkWild 风格只约束构图清洁、无文字和网页适配，不要改成通用清新/明亮风格。"
        )
    return (
        "原创世界优先忠实世界描述和剧情内核；"
        "InkWild 风格只约束构图清洁、无文字和网页适配，不要套通用模板。"
    )


def build_old_world_cover(brief: CoverBrief) -> str:
    subject, essence = _world_subject_and_essence(brief)
    ip = (brief.ip_name or "").strip()
    return (
        f"{essence}"
        f"{subject}创作一幅 3:2 的封面图，用于网站世界列表里的小尺寸卡片陈列，"
        "缩略到 280px 宽时仍要一眼传达这个作品的整体气质。"
        "请理解它的内核后自由创作，聚焦一个核心意象，避免信息过载。"
        f"{_old_fidelity(brief)}{_OLD_HOUSE}{_OLD_COHESION}"
        f"{_mood_clause('' if ip else brief.mood)}{_DARK_UI_HINT}{_LOGO_NEGATIVE}"
    )


BRIEFS = [
    CoverBrief(world_name="雾隐镇", ip_name=None,
               essence="一座常年被浓雾笼罩的山中小镇，谜案与失踪在雾里发生",
               mood="灰雾、低饱和、局部光、雨夜、孤影"),
    CoverBrief(world_name="长安十二时辰", ip_name="长安十二时辰", mood=""),
    CoverBrief(world_name="灰雾迷城", ip_name=None,
               essence="被数据与雨水淹没的赛博都市，记忆可以买卖",
               mood="霓虹、雨夜、冷光、孤影"),
    CoverBrief(world_name="哈利波特", ip_name="哈利波特", mood=""),
]


async def gen(image_gen, name, variant, prompt):
    t0 = time.time()
    try:
        res = await image_gen.generate_image(prompt, aspect_ratio="3:2")
        dt = time.time() - t0
        path = OUT / f"{name}_{variant}.png"
        if res.has_data:
            path.write_bytes(res.base64_data)
            print(f"OK  {name:8} {variant:4} {dt:5.1f}s data={len(res.base64_data)}B -> {path.name}")
        elif res.has_url:
            urllib.request.urlretrieve(res.url, path)
            print(f"OK  {name:8} {variant:4} {dt:5.1f}s url -> {path.name}")
        else:
            print(f"EMPTY {name:8} {variant:4} {dt:5.1f}s (moderation block?)")
    except Exception as e:
        print(f"ERR {name:8} {variant:4} {type(e).__name__}: {e}")


async def main():
    async with async_session() as db:
        image_gen = await resolve_slot_image_generator(db, "image_generation")
    if image_gen is None:
        print("no image generator bound"); return
    tasks = []
    for b in BRIEFS:
        tasks.append(gen(image_gen, b.world_name, "new", build_world_cover_prompt(b)))
        tasks.append(gen(image_gen, b.world_name, "old", build_old_world_cover(b)))
    await asyncio.gather(*tasks)
    print("done")


asyncio.run(main())
