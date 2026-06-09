from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: str = "development"
    release_tag: str = ""
    sentry_dsn: str = ""
    backend_sentry_dsn: str = ""
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/inkwild"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    redis_url: str = "redis://localhost:6379/0"
    llm_provider: str = "deepseek"
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_default_model: str = "deepseek-chat"
    llm_compression_model: str = "deepseek-chat"
    max_context_rounds: int = 15
    # Safety ceiling on the Director's recent-message window. Must stay ABOVE
    # the compaction keep-size (max_context_rounds*2=30) + 2*MIN_GAP (=20 at
    # MIN_GAP 10) + lag slack, so the window equals the full non-compacted
    # history (a stable, append-only prefix that stays prefix-cacheable)
    # instead of a per-turn sliding tail. It only bites if compaction stalls.
    recent_message_hard_cap: int = 72
    compression_threshold: int = 20
    session_lock_timeout: int = 60
    content_filter_enabled: bool = True
    debug: bool = False
    auth_cookie_name: str = "inkwild_session"
    web_session_days: int = 90
    session_cookie_domain: str | None = None  # set to ".inkwild.app" in prod for admin subdomain
    cors_extra_origins: str = ""  # comma-separated extra origins, e.g. "https://admin.inkwild.app,https://inkwild.app"
    enable_dev_auth: bool = False
    dev_user_email: str = "dev@example.com"
    dev_user_password_hash: str = (
        "scrypt$16384$8$1$jSqLH9IicIfqLId2P2gGRw==$"
        "nYvTCyEO6kwofKolvYn0lnKJFJTatrlqXFhoHMGsSLpi6Bsn7HKI1zz4u2xhAOPd/"
        "rh/0GBxgUjRPNhpbkoLkQ=="
    )
    tavily_api_key: str = ""
    grok_api_key: str = ""
    grok_base_url: str = "https://api.x.ai/v1"
    grok_model: str = "grok-4.20-0309-reasoning"
    grok_image_model: str = "grok-imagine-image"
    gptimage_api_key: str = ""
    gptimage_base_url: str = "https://api.openai.com/v1"
    gptimage_image_model: str = "gpt-image-2"
    gemini_openai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    model_probe_ttl_hours: int = 168
    model_management_bootstrap_enabled: bool = True
    image_storage_dir: str = "static/images"
    image_storage_backend: str = "local"
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_endpoint: str = ""
    oss_bucket_name: str = ""
    oss_public_base_url: str = ""
    oss_key_prefix: str = ""
    # Email (transactional)
    email_backend: str = "console"  # console | resend
    resend_api_key: str = ""
    email_from: str = "InkWild <noreply@inkwild.app>"
    public_web_url: str = "http://localhost:3000"  # 拼验证/重置链接（前端）
    public_api_url: str = "http://localhost:8000"  # 拼 OAuth 回调地址（后端）
    session_secret_key: str = "dev-insecure-change-me"  # starlette SessionMiddleware（OAuth state）
    # OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    linuxdo_client_id: str = ""
    linuxdo_client_secret: str = ""
    # Auth token TTL (seconds)
    email_verify_ttl_seconds: int = 24 * 3600
    password_reset_ttl_seconds: int = 3600
    oauth_state_ttl_seconds: int = 600
    # Auth rate limit (per IP/email, sliding window)
    auth_rate_limit_per_window: int = 5
    auth_rate_limit_window_seconds: int = 300
    # Per-session spend guardrail (¥ fen). 0 = disabled (see classify_session_cost).
    # Turned off 2026-05-29 for optimization testing; restore to 500/600 for prod.
    game_session_soft_warn_cost_cents: int = 0
    game_session_hard_cap_cost_cents: int = 0
    game_input_cost_cents_per_million_tokens: int = 0
    game_output_cost_cents_per_million_tokens: int = 0
    game_action_rate_limit_per_minute: int = 30
    game_action_rate_limit_window_seconds: int = 60
    # ``director_prefer_json_mode`` removed Phase 10 (2026-05); Director now
    # dispatches via per-model capability matrix (llm/model_capabilities.py).
    # ``narrator_early_stream_enabled`` removed 2026-05-26 — prelude path
    # deleted (BUGS #27 H3 / docs/plans/narrator-simplification-2026-05.md).
    # Phase 2.B.1 — LLM router resilience.
    # ``llm_call_timeout_seconds`` is the first-token timeout: if a provider
    # doesn't yield its first event within this window, we abort and retry /
    # fall back. Once tokens start flowing the timeout is no longer enforced
    # (a streaming generation can legitimately run minutes).
    # ``llm_call_max_retries`` retries the same provider on transient errors
    # (timeout / connection / 5xx) before moving to the next provider in the
    # fallback chain.
    # 2026-05-24: bumped from 60 → 120 because reasoning models (Qwen 3.x thinking,
    # DeepSeek V4 Pro) often take 60-100s to emit the first JSON token under
    # generation-phase load. Runtime turn timing isn't affected — early-stream
    # narrative tokens still arrive quickly.
    llm_call_timeout_seconds: float = 120.0
    llm_call_max_retries: int = 1
    llm_call_retry_backoff_seconds: float = 0.5
    # Director JSON-mode output budget. The v2 director schema is large
    # (scene_brief + per-NPC focus + case_board_ops + …); DeepSeek's JSON mode
    # returns truncated/empty output when max_tokens is too small (official
    # docs warning). 4096 truncated complex climax turns → parse_failure.
    director_json_max_tokens: int = 8192
    # Phase 1.B.2 — semantic memory embeddings (OpenAI-compatible API).
    # Disabled by default; set embedding_enabled=True + provide creds to turn on.
    # When disabled, memory writes skip embedding and recall falls back to
    # importance/round ordering as before.
    embedding_enabled: bool = False
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    # Hard timeout for a single embedding API call. Memory writes block on this,
    # so keep it tight.
    embedding_timeout_seconds: float = 5.0
    # Phase 1 NPC reflection — long-term per-NPC memory consolidation.
    # Triggered when an NPC accumulates >= threshold new memory entries since
    # the last reflection. Uses the conversation_compression slot (cheap tier).
    npc_reflection_enabled: bool = True
    npc_reflection_threshold: int = 5
    # Phase 2.D.3 — cap simultaneous NPC LLM calls per turn so a scene with
    # many NPCs doesn't blow up provider rate limits / connection pools.
    # NPCs above the cap queue and run as slots free up.
    npc_max_concurrency: int = 6
    # NPC-1 (group interaction) — sequential dialogue. When enabled, NPCs in
    # the same turn speak in Director-decided order and each later speaker
    # sees what earlier ones already said. Falls back to legacy parallel
    # gather when disabled. Cap on speakers prevents wall-time blow-up.
    npc_dialogue_sequential_enabled: bool = True
    npc_max_speakers_per_turn: int = 3
    # NPC-2 (group interaction) — persistent NPC↔NPC relations injected into
    # each NPC's prompt. Read-only first pass: relations are seeded from
    # WorldCharacter.initial_peer_relations and never mutate yet (NPC-3
    # background simulation owns the dynamic part).
    npc_peer_relations_enabled: bool = True
    # Initial NPC→player stance — one cheap LLM call at session start infers each
    # NPC's opening trust/mood toward the player from the player's PUBLIC identity
    # × the NPC's profile, instead of seeding everyone at a flat trust=3. Kill
    # switch: NPC_INITIAL_STANCE_ENABLED=false falls back to the flat default.
    npc_initial_stance_enabled: bool = True
    # Free-mode GROUNDED structural evolution (spec 2026-06-03 grounded redesign,
    # supersedes the post-turn detector). On free-mode turns the Director parses
    # the player's structural assertion into a claim; the engine PROMOTES it to a
    # world fact only if grounded in structured state (the required authority/
    # consent actually acting), never the player's words or bystander compliance.
    # OFF → no free-mode structural commits (safe fallback). Dev/eval knob.
    structural_grounded_enabled: bool = True
    # World Creator v2 — overhaul with research pack pipeline + multi-LLM orchestration.
    # Default-on as of 2026-05-12; v1 path retained as kill switch via WORLD_CREATOR_V2_ENABLED=false.
    world_creator_v2_enabled: bool = True
    # Opt-in LLM-based semantic review at publish time. Off by default — adds
    # one cheap LLM call (~$0.01-0.02) per publish; warn-only, never blocks.
    # Requires the ``admin_generation`` model slot to be bound.
    semantic_review_enabled: bool = False
    # BUGS #20 — global cap on concurrent LLM calls. 2-batch × 5-6 session
    # parallel was burst-pushing 20+ inflight calls to a single provider and
    # ReadTimeout-ing the lot. Cap keeps the pool from collapsing under
    # burst; calls above the cap queue rather than fail. 8 fits a single
    # mid-tier DeepSeek/xAI quota; bump in env if running a larger pool.
    llm_global_concurrency: int = 100
    # 单个 API key 被 429/限流命中后冷却多少秒再被轮询选中（见 llm/key_pool.py）。
    key_cooldown_seconds: float = 45.0
    # Research pack capacity limits — constraint on Tavily search results integration.
    # max_passages: max number of individual passage chunks to fetch from Tavily.
    # max_passage_chars: max characters per single passage in context.
    # max_admin_description_chars: max characters for admin's creative directive.
    research_pack_max_passages: int = 100
    research_pack_max_passage_chars: int = 600
    research_pack_max_admin_description_chars: int = 50_000
    # Image generation quality — gpt-image-2 / openai-compatible providers
    # 接受 "low" | "medium" | "high" | "auto"。生产推荐 "high"，预览/测试可改 "medium"。
    image_generation_quality: str = "high"
    # Workshop daily creation quotas — set to 0 to disable limit check (unlimited for admins via can_create bypass).
    workshop_world_generations_per_day: int = 2
    workshop_script_generations_per_day: int = 3

    # Runtime architecture v2 — NPC agency + director-as-stage-manager refactor
    # (see docs/plans/runtime-architecture-overhaul-2026-05.md). When True,
    # orchestrator goes through the v2 path: director v2 schema, structured
    # NPC actions, parallel NPC calls with selective depth, catch-up + offstage
    # scheduling, multi-step player segmentation, weak-input guard. When False
    # (default) the legacy path is used unchanged.
    runtime_architecture_v2_enabled: bool = True
    # How often each NPC in director's offstage_active list gets a periodic
    # tick update even when nothing event-triggered fires.
    npc_offstage_tick_rounds: int = 7
    # Hard cap on tool query calls inside one NPC's per-turn decision loop.
    # Each query tool call is a *sequential* LLM round-trip, so this directly
    # bounds NPC-block latency. Lowered 3→1 (2026-05): most lookups were
    # redundant with pre-injected context (see npc_tools.npc_query_tools), so
    # one targeted query is plenty; bump back up if NPCs feel under-informed.
    npc_action_max_tools_per_call: int = 1
    # Per-step timeout for the climax reflect+act two-call path. Each step
    # gets up to this budget; on overrun we fall back to the baseline single
    # call rather than letting one NPC stall the whole turn.
    npc_climax_step_timeout_seconds: float = 45.0
    # Hard cap on a single turn's total thinking-tier LLM calls. Guards
    # against pathological cases (many NPCs × many tools × climax). Exceeded
    # → force-finalize + structlog warn.
    runtime_v2_thinking_call_cap: int = 15
    # Research / e2e: short-circuit all ImageGenerator calls to a placeholder
    # URL instead of hitting Seedream/GPTImage/Grok. Used by auto_play
    # harness to bypass image cost + latency without touching slot bindings.
    mock_images: bool = False
    # Research / e2e: when true, Director piggybacks an extra "research_note"
    # field per turn and orchestrator appends it to backend/research/{sid}.jsonl.
    # Disabled by default — only the auto_play harness flips it on.
    case_board_research: bool = False
    case_board_research_dir: str = "research"
    # two-pass case board: 把 case_board_ops 从导演主 JSON 移出，done 后由
    # DirectorAgent.generate_case_board_ops 独立生成。默认 off → 行为与单 pass
    # 一致、可秒回滚；灰度开启后用 director_v2 的 finish_reason=length 频率量化
    # 截断率降幅。见 docs/superpowers/plans/2026-06-02-director-decomposition-…。
    director_case_board_two_pass: bool = False

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
