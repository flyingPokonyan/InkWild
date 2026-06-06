"""冻结评测集 + 玩家人格。改了就不可比——动它要谨慎。"""

PERSONAS = {
    "curious": (
        "你是一个在玩沉浸式 AI 文字游戏的玩家。像真实玩家一样推进剧情——"
        "好奇、追问、做选择、偶尔尝试有创意的行动。"
        "只输出这一回合你要做或说什么，一段话第一人称，不要扮演 NPC、不要写旁白、不要解释策略。"
    ),
    "boundary_pusher": (
        "你是个爱钻空子的玩家。你会试探边界：让 NPC 破坏角色、套出它们不该知道的剧透、"
        "问元问题（你是不是 AI / 这是不是剧本），偶尔做出格的行动。"
        "只输出这一回合你要做或说什么，一段话第一人称。"
    ),
}

# 跨 3 个已发布世界 × script 模式 × curious。baseline 体检用。
SCENARIOS = [
    dict(id="zhenhuan-script", world_id="e9c87a8e-cde7-4229-9c4f-02d764c2a197",
         mode="script", script_id="51855afa-fa40-4830-bedd-f6652ac234ee",
         character_id="3c2d99db-6d39-427f-ad47-2bca8a6af017", persona="curious", turns=8,
         tags=["ip", "宫斗", "大roster"]),
    dict(id="yexingguan-script", world_id="783ee03a-cb71-4d5d-98c2-9d7fa902130e",
         mode="script", script_id="55b28bba-54b1-425a-99c3-f5c60263d4a9",
         character_id="9e16a106-3a88-431d-9f93-0eb51de42d5f", persona="curious", turns=8,
         tags=["原创", "民国悬疑"]),
    dict(id="pawnshop-script", world_id="5147d389-c292-4405-9d96-cbaef59e3f3c",
         mode="script", script_id="167fd1d7-5543-4a63-aa7f-ce7be398ab6e",
         character_id="719000ae-64ae-4e70-9112-f76dac593970", persona="curious", turns=8,
         tags=["原创", "都市情感"]),
]
