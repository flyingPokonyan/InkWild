"""A (gpt-image 自由发挥, no focus) vs B (中间地带: 主题+钩子, 构图交给 gpt-image).
Same world + same 画法, only the 'what to draw' dimension differs. Self-contained."""
import asyncio, time, urllib.request
from pathlib import Path
from database import async_session
from services.model_management import resolve_slot_image_generator

OUT = Path("/tmp/focus_cmp"); OUT.mkdir(exist_ok=True)
_LOGO = ("画面里不要任何可读文字、标题、字幕、数字、乱码、logo、品牌、署名；牌匾纸张只作模糊纹理。")
_CRAFT = ("用这种画法去『表达』，而不是把场景渲染逼真：敢于大胆留白、概括取舍、宁简勿满，"
    "构图有清晰的焦点、一抹克制的点睛色，体现明确的手绘艺术语言。"
    "避免面面俱到的写实厚涂渲染、3D 渲染感、塑料质感、照片感、HDR、信息过载、廉价 stock 感、二游立绘与网文封面感。媒介始终是「画」，不是照片。")
_WEB = ("画面陈列在近黑色网站卡片上，明暗由画法与题材自定，但暗画面也要透气、暗部不糊死黑、高光不过曝，清楚可读。")
STYLE = {
    "新艺术装饰": "新艺术运动装饰风（Art Nouveau）——流畅曲线、装饰性边框、平面化、华丽而克制的图案感。",
    "水墨写意": "中国水墨写意——墨色浓淡干湿、飞白、大面积留白、寥寥数笔概括神韵，重意境，宣纸肌理。",
    "水彩淡彩": "水彩 / 钢笔淡彩——透明轻盈的水彩晕染、湿边、大量留白、概括形体，雅致书籍插画感。",
    "丝网波普": "丝网印刷 / 波普平面海报——高对比平面色块、套色错位质感、简练有力的图形语言、强装饰性。",
}

# (name, 画法, essence, 主题钩子 for B)
WORLDS = [
    ("甄嬛传", "新艺术装饰", "深宫红墙金瓦，嫔妃之间权谋与情爱交织",
     "紫禁城深宫里的权谋暗涌，华美旗装下步步杀机"),
    ("庆余年", "水墨写意", "一个带着现代记忆的少年，身处古代庙堂的权力漩涡",
     "少年身处古代庙堂的权力棋局，怀揣不属于这个时代的秘密"),
    ("长安十二时辰", "水彩淡彩", "盛唐长安，十二时辰之内的一场生死追凶",
     "盛唐长安的十二时辰生死追凶，繁华灯火下暗藏危机"),
    ("记忆典当行", "水彩淡彩", "一座记忆可以被买卖、典当的诡谲都市",
     "一间买卖记忆的诡谲当铺，藏着关于遗忘与失去的交易"),
    ("灰雾迷城", "丝网波普", "被数据与雨水淹没的赛博都市，记忆可被买卖删改",
     "雨水与数据淹没的赛博都市，记忆被人窃取改写的危机"),
]

def build_A(name, style, essence):  # gpt-image 自由发挥
    return (f"以下是这个世界的内核，请理解后创作：{essence}。为虚构作品《{name}》创作一幅 3:2 封面图，"
        f"用于网站世界列表卡片，一眼传达气质。画法：{STYLE[style]}{_CRAFT}{_WEB}{_LOGO}")

def build_B(name, style, essence, theme):  # 中间地带: 主题+钩子, 构图交给 gpt-image
    return (f"以下是这个世界的内核，请理解后创作：{essence}。为虚构作品《{name}》创作一幅 3:2 封面图，"
        f"用于网站世界列表卡片。这张封面要传达：{theme}——由你构想最能一眼勾住人、让人想点进去的那个画面（画什么、什么构图都由你定）。"
        f"画法：{STYLE[style]}{_CRAFT}{_WEB}{_LOGO}")

async def gen(image_gen, name, variant, prompt):
    t0 = time.time()
    if (OUT / f"{name}_{variant}.png").exists():
        print(f"SKIP {name} {variant}", flush=True); return
    try:
        res = await image_gen.generate_image(prompt, aspect_ratio="3:2")
        dt = time.time() - t0; path = OUT / f"{name}_{variant}.png"
        if res.has_data: path.write_bytes(res.base64_data); print(f"OK  {name:8} {variant:8} {dt:5.1f}s", flush=True)
        elif res.has_url: urllib.request.urlretrieve(res.url, path); print(f"OK  {name:8} {variant:8} {dt:5.1f}s", flush=True)
        else: print(f"EMPTY {name} {variant}", flush=True)
    except Exception as e:
        print(f"ERR {name:8} {variant:8} {type(e).__name__}: {e}", flush=True)

async def main():
    async with async_session() as db:
        image_gen = await resolve_slot_image_generator(db, "image_generation")
    if image_gen is None: print("no gen"); return
    tasks = []
    for name, style, essence, theme in WORLDS:
        tasks.append(gen(image_gen, name, "A纯发挥", build_A(name, style, essence)))
        tasks.append(gen(image_gen, name, "B主题钩子", build_B(name, style, essence, theme)))
    await asyncio.gather(*tasks)
    print("done", flush=True)

asyncio.run(main())
