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


def claim_compression_round(
    rounds_played: int, last_compressed_round: int, threshold: int
) -> int | None:
    """Return the round to stamp as ``last_compressed_round`` when a compaction
    is due this turn, else ``None``.

    The stamp MUST be advanced on the turn's owned GameState (the main loop
    persists it under the optimistic lock). The detached fire-and-forget
    compaction task cannot own it: it writes a separate DB session AND the
    ``game_state`` column is plain ``JSON`` (no mutation tracking), so its
    update is silently dropped and then clobbered by the main loop. That is why
    compaction used to re-fire every round once past the threshold.
    """
    if not should_compress(rounds_played, last_compressed_round, threshold):
        return None
    return rounds_played


# Distinct from the newlines inside any single summary, so a running summary
# can be split back into its append segments to bound its length.
SUMMARY_SEPARATOR = "\n\n---\n\n"


def merge_context_summary(
    previous: str | None, new: str, *, max_segments: int = 6
) -> str:
    """Append ``new`` to the running context summary, keeping only the most
    recent ``max_segments`` segments.

    The running summary lives in the per-turn prompt tail and is never
    prefix-cached, so unbounded ``previous + new`` growth inflates every
    Director call's input. Dropped older history is still recoverable via
    semantic memory recall.
    """
    segments = [s for s in (previous or "").split(SUMMARY_SEPARATOR) if s.strip()]
    new = new.strip()
    if new:
        segments.append(new)
    segments = segments[-max_segments:]
    return SUMMARY_SEPARATOR.join(segments)


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
