MIN_GAP_BETWEEN_COMPRESSIONS = 5


def estimate_token_count(text: str) -> int:
    """Cheap cross-provider estimate for instrumentation, not billing."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_token_count(messages: list[dict]) -> int:
    return sum(estimate_token_count(str(message.get("content", ""))) for message in messages)


def should_compress(rounds_played: int, last_compressed_round: int, threshold: int) -> bool:
    if rounds_played <= threshold:
        return False
    if rounds_played - last_compressed_round < MIN_GAP_BETWEEN_COMPRESSIONS:
        return False
    return True


def build_compression_prompt(messages: list[dict]) -> str:
    formatted = []
    for message in messages:
        role = "玩家" if message["role"] == "user" else "主持人"
        formatted.append(f"{role}: {message['content']}")

    conversation = "\n".join(formatted)
    return (
        "请将以下游戏对话压缩为简洁的摘要。\n"
        "保留以下关键信息：\n"
        "- 发生的重要事件\n"
        "- NPC说的关键信息\n"
        "- 玩家做出的重要决定和承诺\n"
        "- 发现的线索\n"
        "- 关系变化\n\n"
        "不要遗漏任何可能影响后续剧情的信息。用第三人称叙述。\n\n"
        f"对话记录：\n{conversation}"
    )
