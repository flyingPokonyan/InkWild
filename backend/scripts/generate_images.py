"""One-off script: generate cover images and character avatars for existing worlds.

Usage: cd backend && ../.venv/bin/python scripts/generate_images.py
"""

import asyncio
import json
import sqlite3

from config import settings
from llm.grok import GrokProvider
from services.image_storage import get_image_storage, make_image_key, save_generated_image_result
from llm.router import LLMRouter
from llm.deepseek import DeepSeekProvider
from services.world_creator_agent import IMAGE_PROMPTS_TOOL, _collect_tool_output, _str, _ensure_list


async def main():
    if not settings.grok_api_key:
        print("ERROR: GROK_API_KEY not set")
        return

    grok = GrokProvider()
    storage = get_image_storage()
    llm = LLMRouter(
        providers={settings.llm_provider: DeepSeekProvider()},
        fallback_chain=[settings.llm_provider],
    )

    conn = sqlite3.connect("dev.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all worlds
    worlds = cursor.execute("SELECT * FROM worlds").fetchall()

    for world in worlds:
        world_id = world["id"]
        world_name = world["name"]
        genre = world["genre"]
        era = world["era"]
        base_setting = world["base_setting"] or ""
        locations_data = json.loads(world["locations_data"]) if world["locations_data"] else []
        existing_cover = world["cover_image"]

        print(f"\n{'='*60}")
        print(f"World: {world_name} (id: {world_id})")

        # Get playable characters
        chars = cursor.execute(
            "SELECT * FROM world_characters WHERE world_id = ? AND playable = 1",
            (world_id,)
        ).fetchall()

        # Also get all characters for context
        all_chars = cursor.execute(
            "SELECT * FROM world_characters WHERE world_id = ?",
            (world_id,)
        ).fetchall()

        avatar_names = [c["name"] for c in chars]
        print(f"  Playable characters: {avatar_names}")

        # Step 1: Generate image prompts via DeepSeek
        print("  Generating image prompts via DeepSeek...")

        location_preview = "、".join(
            loc.get("name", "") for loc in locations_data[:5]
        ) if locations_data else "茶摊、药铺、戏台、祠堂、府邸"

        char_details = "\n".join(
            f"- {c['name']}：{(c['personality'] or '')[:80]}，位于{c['initial_location'] or ''}"
            for c in all_chars if c["name"] in avatar_names
        )

        context = (
            f"世界名称：{world_name}\n"
            f"类型：{genre}\n"
            f"时代：{era}\n"
            f"世界设定：{base_setting[:400]}\n"
            f"主要地点：{location_preview}\n\n"
            f"需要生成头像的角色：\n{char_details}\n\n"
            "请为这个世界生成AI绘图提示词。要求：\n"
            "- 封面提示词要体现世界的核心氛围和标志性场景，英文，80-150词\n"
            "- 角色头像提示词要体现角色的外貌、气质、身份，英文，60-100词\n"
            "- 提示词要具体、有画面感，包含光影、色调、艺术风格等细节\n"
            "- 风格统一，适合同一个世界观\n"
            "- 所有提示词用英文书写"
        )

        prompts_data = await _collect_tool_output(
            llm,
            messages=[{"role": "user", "content": context}],
            tools=[IMAGE_PROMPTS_TOOL],
            system=(
                "你是一个专业的AI绘图提示词工程师，擅长将叙事世界观转化为高质量的图像生成提示词。"
                "你的提示词要具体、有画面感，能让AI绘图模型生成符合世界观的精美插画。"
                "请调用工具返回结构化数据。"
            ),
            max_tokens=2048,
        )

        if not prompts_data:
            print("  ERROR: DeepSeek did not return image prompts")
            continue

        cover_prompt = _str(prompts_data.get("cover_prompt"))
        char_prompts = {}
        for cp in _ensure_list(prompts_data.get("character_prompts")):
            if isinstance(cp, dict) and cp.get("name") and cp.get("prompt"):
                char_prompts[cp["name"]] = _str(cp["prompt"])

        print(f"  Cover prompt ({len(cover_prompt)} chars): {cover_prompt[:100]}...")
        for name, prompt in char_prompts.items():
            print(f"  Avatar prompt for {name} ({len(prompt)} chars): {prompt[:80]}...")

        # Step 2: Generate cover image
        if not existing_cover and cover_prompt:
            print("  Generating cover image via Grok Imagine...")
            try:
                result = await grok.generate_image(cover_prompt, aspect_ratio="16:9")
                key = make_image_key("worlds", world_name)
                url = await save_generated_image_result(storage, result, key)
                if url:
                    cursor.execute("UPDATE worlds SET cover_image = ? WHERE id = ?", (url, world_id))
                    conn.commit()
                    print(f"  ✓ Cover saved: {url}")
                else:
                    print("  ✗ No image returned for cover")
            except Exception as e:
                print(f"  ✗ Cover generation failed: {e}")
        else:
            print(f"  Cover already exists: {existing_cover}")

        # Step 3: Generate character avatars
        for char in chars:
            char_name = char["name"]
            existing_avatar = char["avatar"]
            if existing_avatar:
                print(f"  Avatar for {char_name} already exists: {existing_avatar}")
                continue

            prompt = char_prompts.get(char_name)
            if not prompt:
                print(f"  No prompt for {char_name}, skipping")
                continue

            print(f"  Generating avatar for {char_name}...")
            try:
                result = await grok.generate_image(prompt, aspect_ratio="1:1")
                key = make_image_key("characters", char_name)
                url = await save_generated_image_result(storage, result, key)
                if url:
                    cursor.execute("UPDATE world_characters SET avatar = ? WHERE id = ?", (url, char["id"]))
                    conn.commit()
                    print(f"  ✓ Avatar saved: {url}")
                else:
                    print(f"  ✗ No image returned for {char_name}")
            except Exception as e:
                print(f"  ✗ Avatar generation failed for {char_name}: {e}")

    conn.close()
    print(f"\n{'='*60}")
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
