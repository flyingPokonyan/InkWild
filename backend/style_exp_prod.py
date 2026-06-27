"""Style/画法 gradient: 6 strong stylized media vs 1 厚涂对照. 2 题材 × 6 = 12.
Tests 用户's hypothesis: 廉价=写实渲染套壳, 高级=强风格化+克制留白. No mood/
luminosity injected — let the 画法 drive everything. Self-contained."""
import asyncio, time, urllib.request
from pathlib import Path
from database import async_session
from services.model_management import resolve_slot_image_generator

OUT = Path("/tmp/style_exp"); OUT.mkdir(exist_ok=True)
_LOGO = ("画面里不要任何可读文字、标题、字幕、数字、乱码、logo、品牌、署名；"
    "牌匾纸张卷轴只作模糊纹理，不要可辨认字符。")
# 风格化通用要求（②-⑥），强调表达而非渲染
_STYLIZED = ("请用一种强烈而克制的画法去『表达』这个世界，而不是把场景渲染逼真："
    "敢于大胆留白、概括取舍、宁简勿满，体现明确的手绘艺术语言与构图。"
    "避免面面俱到的写实厚涂渲染、3D 渲染感、塑料感、照片感、HDR、信息过载、廉价 stock 感。"
    "媒介始终是『画』不是照片。具体画法：")

STYLES = {
"1厚涂对照": ("用厚涂数字概念美术（digital painting / concept art）绘制，写实的光影、材质与氛围渲染，细节丰富、信息饱满。", False),
"2水墨写意": ("中国水墨写意——墨色浓淡干湿、飞白、大面积留白、寥寥数笔概括神韵，重意境不重细节，宣纸肌理。", True),
"3复古版画": ("复古铜版画 / 木刻版画——硬朗的刻线、有限套色、平面化、强烈的黑白灰关系与装饰性肌理，像古籍插图。", True),
"4水彩淡彩": ("水彩 / 钢笔淡彩——透明轻盈的水彩晕染、湿边、大量留白、概括的形体，雅致的书籍插画感。", True),
"5扁平插画": ("现代扁平插画——限定的几个主色、大色块、概括的几何形体、装饰性平面构图、大胆留白，不画写实光影。", True),
"6丝网波普": ("丝网印刷 / 波普平面海报——高对比的平面色块、套色错位质感、简练有力的图形语言、强装饰性。", True),
}

def build(name, essence, style_key):
    desc, stylized = STYLES[style_key]
    ess = f"以下是这个世界的内核，请理解后创作：{essence}\n" if essence else ""
    head = (f"{ess}为虚构作品《{name}》创作一幅 3:2 的封面图，用于网站世界列表卡片陈列，"
        "缩略到 280px 仍要一眼传达气质，聚焦一个核心意象。")
    style = (f"{_STYLIZED}{desc}" if stylized else desc)
    return f"{head}{style}画面会陈列在近黑色网站卡片上，暗部不要糊成死黑、高光不要过曝，整体清楚可读。{_LOGO}"

WORLDS = [
    ("锦绣宫阙", "深宫红墙金瓦，权谋与情爱在烛影里交织"),
    ("灰雾迷城", "被数据与雨水淹没的赛博都市，记忆可以买卖"),
]

async def gen(image_gen, name, style, prompt):
    t0 = time.time()
    if (OUT / f"{name}_{style}.png").exists():
        print(f"SKIP {name} {style}", flush=True); return
    try:
        res = await image_gen.generate_image(prompt, aspect_ratio="3:2")
        dt = time.time() - t0; path = OUT / f"{name}_{style}.png"
        if res.has_data: path.write_bytes(res.base64_data); print(f"OK  {name:6} {style:8} {dt:5.1f}s", flush=True)
        elif res.has_url: urllib.request.urlretrieve(res.url, path); print(f"OK  {name:6} {style:8} {dt:5.1f}s", flush=True)
        else: print(f"EMPTY {name} {style}", flush=True)
    except Exception as e:
        print(f"ERR {name:6} {style:8} {type(e).__name__}: {e}", flush=True)

async def main():
    async with async_session() as db:
        image_gen = await resolve_slot_image_generator(db, "image_generation")
    if image_gen is None: print("no gen"); return
    tasks = [gen(image_gen, n, s, build(n, e, s)) for n, e in WORLDS for s in STYLES]
    await asyncio.gather(*tasks)
    print("done", flush=True)

asyncio.run(main())
