"""AI picks the 画法 per world, then renders. Tests the real mechanism:
does the LLM choose a fitting + varied style, and does the batch hold together?
12 多题材世界. Self-contained. Run local (Clash off)."""
import asyncio, json, time, urllib.request
from pathlib import Path
from database import async_session
from services.model_management import resolve_slot_router, resolve_slot_image_generator

OUT = Path("/tmp/ai_style"); OUT.mkdir(exist_ok=True)
_LOGO = ("画面里不要任何可读文字、标题、字幕、数字、乱码、logo、品牌、署名；牌匾纸张只作模糊纹理。")
_STYLIZED = ("请用一种强烈而克制的画法去『表达』这个世界，而不是把场景渲染逼真："
    "敢于大胆留白、概括取舍、宁简勿满，体现明确的手绘艺术语言。"
    "避免面面俱到的写实厚涂渲染、3D 渲染感、塑料感、照片感、HDR、信息过载。媒介是『画』不是照片。具体画法：")

STYLE_DESC = {
"水墨写意": "中国水墨写意——墨色浓淡干湿、飞白、大面积留白、寥寥数笔概括神韵，重意境，宣纸肌理。",
"工笔重彩": "中国工笔重彩——精细勾线、矿物颜料的沉稳重彩、装饰性的图案与金线，典雅考究。",
"铜版木刻": "复古铜版画 / 木刻版画——硬朗刻线、有限套色、平面化、强烈黑白灰与装饰肌理，像古籍插图。",
"水彩淡彩": "水彩 / 钢笔淡彩——透明轻盈的水彩晕染、湿边、大量留白、概括形体，雅致书籍插画感。",
"扁平极简": "现代扁平插画——限定几个主色、大色块、概括的几何形体、装饰性平面构图、大胆留白，不画写实光影。",
"丝网波普": "丝网印刷 / 波普平面海报——高对比平面色块、套色错位质感、简练有力的图形语言、强装饰性。",
"浮世绘": "日本浮世绘 / 木版画——平涂色块、装饰性的线条与波纹、留白、传统东方版画构图。",
"复古绘本": "复古童书 / 绘本插画——温暖手绘、柔和颗粒质感、概括造型、有故事书般的亲切感。",
"钢笔线描": "钢笔线描 + 单色淡彩——纤细灵动的线条、克制的局部上色、大量留白，文学速写感。",
"新艺术装饰": "新艺术运动装饰风（Art Nouveau）——流畅的曲线、装饰性边框、平面化、华丽而克制的图案感。",
"蜡笔色粉": "蜡笔 / 色粉 / 干笔触——粗粝温暖的笔触肌理、柔和的色彩过渡、手作感、概括的形体。",
"拼贴构成": "拼贴 / 构成主义——纸张拼贴、几何分割、错位的图形与肌理、强设计感的平面构成。",
}

WORLDS = [
    ("深宫权谋", "古风权谋", "森严宫闱，嫔妃倾轧，权谋与情爱在朱墙金瓦间交织"),
    ("赛博迷城", "赛博朋克", "数据与雨水淹没的赛博都市，记忆可被买卖删改"),
    ("民国谍影", "民国谍战", "十里洋场，租界谍影，旗袍与枪声并存的危险年代"),
    ("江湖剑客", "武侠", "快意恩仇的武侠江湖，刀光剑影、酒馆山门、侠骨柔情"),
    ("云海炼金所", "西方奇幻", "漂浮群岛上的炼金术师与学徒，飞艇、魔法阵与古老契约"),
    ("雾镇疑案", "悬疑推理", "常年浓雾的山中小镇，连环失踪与隐秘真相"),
    ("都市夜未眠", "现代都市", "繁华都市的午夜，霓虹、便利店、孤独心事与相遇"),
    ("夏日青葱", "校园青春", "夏日校园，社团、黄昏操场、心动与成长"),
    ("星舰远征", "科幻太空", "深空中的孤独星舰，未知信号、舱门与浩瀚星海"),
    ("锈色残阳", "末世废土", "核冬之后的废土，锈迹、幸存者与残阳"),
    ("仙门问道", "仙侠修真", "缥缈仙门，云海宫阙、御剑修真、问道长生"),
    ("古宅惊魂", "恐怖悬疑", "雨夜深山古宅，烛影摇红、低语与不安"),
]


async def collect(llm, system, user, max_tokens=2048):
    parts = []
    async for ev in llm.stream_with_tools(messages=[{"role": "user", "content": user}], tools=[], system=system, max_tokens=max_tokens):
        if ev.get("type") == "text_delta":
            parts.append(ev.get("text", ""))
    return "".join(parts).strip()


async def pick_styles(router):
    pool = list(STYLE_DESC.keys())
    system = ("你是 InkWild 的美术指导。给定一批互动故事世界和一个『画法池』，为每个世界挑选一种"
        "最能表达它气质、又最高级耐看不廉价的画法。原则：①绝不用厚涂写实渲染（太廉价像 AI 出图）；"
        "②整批世界尽量用不同画法，让陈列丰富、不雷同（同一画法最多复用一两次）；③画法要贴合题材气质。"
        "只输出 JSON 数组，不要解释。")
    user = json.dumps({
        "worlds": [{"name": n, "genre": g, "essence": e} for n, g, e in WORLDS],
        "style_pool": pool,
        "output_format": '[{"name":"世界名","style":"画法池中之一","reason":"12字内理由"}]',
    }, ensure_ascii=False)
    text = await collect(router, system, user)
    s, e = text.find("["), text.rfind("]")
    arr = json.loads(text[s:e + 1])
    return {d["name"]: (d["style"], d.get("reason", "")) for d in arr}


def build(name, essence, style):
    desc = STYLE_DESC.get(style) or STYLE_DESC["水墨写意"]
    return (f"以下是这个世界的内核：{essence}。为虚构作品《{name}》创作一幅 3:2 封面图，"
        f"用于网站世界列表卡片，聚焦一个核心意象。{_STYLIZED}{desc}"
        f"画面陈列在近黑色网站卡片上，暗部不糊死黑、高光不过曝，清楚可读。{_LOGO}")


async def gen(image_gen, name, style, prompt):
    t0 = time.time()
    if (OUT / f"{name}_{style}.png").exists():
        print(f"SKIP {name}", flush=True); return
    try:
        res = await image_gen.generate_image(prompt, aspect_ratio="3:2")
        dt = time.time() - t0; path = OUT / f"{name}_{style}.png"
        if res.has_data: path.write_bytes(res.base64_data); print(f"OK  {name:8} [{style}] {dt:5.1f}s", flush=True)
        elif res.has_url: urllib.request.urlretrieve(res.url, path); print(f"OK  {name:8} [{style}] {dt:5.1f}s", flush=True)
        else: print(f"EMPTY {name}", flush=True)
    except Exception as ex:
        print(f"ERR {name:8} [{style}] {type(ex).__name__}: {ex}", flush=True)


async def main():
    async with async_session() as db:
        router = await resolve_slot_router(db, "admin_generation")
        image_gen = await resolve_slot_image_generator(db, "image_generation")
    if image_gen is None or router is None:
        print("missing router/image_gen"); return
    # 固定上一轮 AI 选的画法（补跑用），霍格→云海炼金所沿用复古绘本
    FIXED = {
        "深宫权谋": ("工笔重彩", "金碧朱墙"), "赛博迷城": ("丝网波普", "故障霓虹"),
        "民国谍影": ("钢笔线描", "旗袍暗巷"), "江湖剑客": ("水墨写意", "墨韵剑气"),
        "云海炼金所": ("复古绘本", "群岛童话"), "雾镇疑案": ("铜版木刻", "雾锁谜团"),
        "都市夜未眠": ("水彩淡彩", "霓虹孤独"), "夏日青葱": ("蜡笔色粉", "青春光影"),
        "星舰远征": ("扁平极简", "深空孤独"), "锈色残阳": ("拼贴构成", "废土锈铁"),
        "仙门问道": ("浮世绘", "缥缈仙韵"), "古宅惊魂": ("新艺术装饰", "妖冶鬼魅"),
    }
    print("=== 用固定画法补跑 ===", flush=True)
    picks = FIXED if FIXED else await pick_styles(router)
    for n, _g, _e in WORLDS:
        st, rs = picks.get(n, ("水墨写意", "default"))
        print(f"  {n:8} -> {st:6}  ({rs})", flush=True)
    print("=== 生图中 ===", flush=True)
    em = {n: e for n, g, e in WORLDS}
    tasks = [gen(image_gen, n, picks.get(n, ("水墨写意", ""))[0], build(n, em[n], picks.get(n, ("水墨写意", ""))[0])) for n, g, e in WORLDS]
    await asyncio.gather(*tasks)
    print("done", flush=True)

asyncio.run(main())
