"""Tone gradient A/B: L2克制明快 / L3讨喜 / L4高饱和过头. Shared 插画地基.
3 题材 (赛博暗/悬疑暗/古风暖) × 3 档 = 9 张. Self-contained, run on PROD (or
local with Clash off)."""
import asyncio, time, urllib.request
from pathlib import Path
from database import async_session
from services.model_management import resolve_slot_image_generator

OUT = Path("/tmp/tone_exp"); OUT.mkdir(exist_ok=True)
_LOGO = ("不要出现任何可读文字、标题、字幕、数字、乱码、logo、品牌、演员表、奖项、发行日期、"
    "电视台署名或界面元素；牌匾、纸张、卷轴、符咒只能作为模糊纹理，不要生成可辨认字符。")
# 插画地基 (保留)
HOUSE = ("InkWild 媒介地基：手绘插画 / 绘画 / 概念美术质感——有清晰可见的笔触、颜料肌理和概括的色彩区块，"
    "像一张画出来的插画，而不是照相写实的渲染或照片。媒介始终是「画」不是「照片」。"
    "避免照相写实 / 3D 渲染照片感、塑料皮肤反光、HDR 过曝、过度锐化硬边、廉价 stock photo。")
COMP = ("构图讲究、单一焦点、核心意象 1-2 个、留白呼吸；不要拼贴堆叠，也不要海报式文字排版。")

# 三档明快度
TONE = {
"L2克制明快": ("明暗基调：整体偏明快、色彩干净通透、适度饱和，主体清晰跳出来；保留题材气质，"
    "暗题材可以暗但要暖、要透气、不灰不闷不脏。"),
"L3讨喜": ("明暗基调：整体明快、色彩饱和鲜明、暖色调倾向，有讨喜的暖光（金光 / 暖橙 / 晨光 / 烛火）、明亮的高光，"
    "对比清晰、主体明亮跳出，画面理想化、好看、第一眼就吸引人。"
    "即使是暗题材也用温暖明快的方式表现（像暖橙灯火的酒馆那样，暗而暖、亮而透），绝不灰暗沉闷。"),
"L4过头": ("明暗基调：高明度、高饱和、色彩鲜艳明亮、强暖光、强对比，明快讨喜，"
    "像动画电影 / 绘本般鲜明跳跃的色彩，画面非常吸睛、非常亮眼。"),
}

def build(name, essence, mood, tone_key):
    ess = f"以下是这个世界的内核，请理解后创作：{essence}\n" if essence else ""
    moodc = f"画面风格：{mood}。" if mood else ""
    return (f"{ess}为虚构作品《{name}》创作一幅 3:2 的封面图，用于网站世界列表卡片陈列，缩略到 280px 仍要一眼传达气质。"
        f"聚焦一个核心意象，避免信息过载。{HOUSE}{COMP}{TONE[tone_key]}{moodc}"
        f"画面会陈列在近黑色网站卡片上，暗部不要糊成死黑一团、高光不要过曝发白，整体清楚可读。{_LOGO}")

WORLDS = [
    ("灰雾迷城", "被数据与雨水淹没的赛博都市，记忆可以买卖", "霓虹、雨夜、冷光、孤影"),
    ("雾隐镇", "一座常年被浓雾笼罩的山中小镇，谜案与失踪在雾里发生", "灰雾、局部光、雨夜、孤影"),
    ("锦绣宫阙", "深宫红墙金瓦，权谋与情爱在烛影里交织", "暖红、烛光、金饰、华美"),
]

async def gen(image_gen, name, tone, prompt):
    t0 = time.time()
    if (OUT / f"{name}_{tone}.png").exists():
        print(f"SKIP {name} {tone}", flush=True); return
    try:
        res = await image_gen.generate_image(prompt, aspect_ratio="3:2")
        dt = time.time() - t0; path = OUT / f"{name}_{tone}.png"
        if res.has_data: path.write_bytes(res.base64_data); print(f"OK  {name:8} {tone:8} {dt:5.1f}s", flush=True)
        elif res.has_url: urllib.request.urlretrieve(res.url, path); print(f"OK  {name:8} {tone:8} {dt:5.1f}s", flush=True)
        else: print(f"EMPTY {name} {tone}", flush=True)
    except Exception as e:
        print(f"ERR {name:8} {tone:8} {type(e).__name__}: {e}", flush=True)

async def main():
    async with async_session() as db:
        image_gen = await resolve_slot_image_generator(db, "image_generation")
    if image_gen is None: print("no gen"); return
    tasks = []
    for name, essence, mood in WORLDS:
        for tone in TONE:
            tasks.append(gen(image_gen, name, tone, build(name, essence, mood, tone)))
    await asyncio.gather(*tasks)
    print("done", flush=True)

asyncio.run(main())
