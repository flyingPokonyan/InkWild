export interface ApiEnvelope<T> {
  code: number;
  data: T;
  message?: string;
}

export interface ApiErrorDetail {
  code?: number;
  message?: string;
}

export interface AuthIdentitySummary {
  provider: string;
  email: string | null;
  phone: string | null;
}

export interface CurrentUserDTO {
  id: string;
  nickname: string | null;
  avatar_url: string | null;
  is_admin: boolean;
  can_create: boolean;
  identities: AuthIdentitySummary[];
}

export interface CurrentUser extends CurrentUserDTO {
  isAdmin: boolean;
  canCreate: boolean;
}

export function normalizeCurrentUser(user: CurrentUserDTO): CurrentUser {
  return {
    ...user,
    isAdmin: user.is_admin,
    canCreate: user.can_create,
  };
}

export interface ClueDTO {
  id: string;
  content: string;
  found_at: string;
}

export interface NpcRelationDTO {
  trust: number;
  mood: string;
  last_interaction: string;
}

export interface GameState {
  current_time: string;
  current_location: string;
  player_inventory: string[];
  discovered_clues: ClueDTO[];
  npc_relations: Record<string, NpcRelationDTO>;
  triggered_events: string[];
  visited_locations: string[];
  time_index?: number;
  round_number?: number;
  rounds_since_last_clue?: number;
  narrative_arc?: { current_act?: string; [k: string]: unknown };
  case_board?: CaseBoard;
}

// --- Case Board types (2026-05 lean refactor) ---
//
// Case board is the player's working memory aid. Every field below must
// drive a player decision; everything else lives in narrative / game_state.

export type TimePressure = "low" | "medium" | "high" | "critical";

// Tier 1 — always present regardless of script_type.

export interface UnresolvedQuestion {
  question: string;
  status: "open" | "answered";
  answer?: string;
}

export interface NpcDynamicEntry {
  trust?: number;
  mood?: string;
  current_stance?: string;
  last_shift_reason?: string;
}

// Tier 2 — mystery only.

export interface Suspect {
  name: string;
  suspicion_level: "low" | "medium" | "high";
  reason: string;
}

// Tier 3 — emotional only.

export interface MoralDilemma {
  round: number;
  dilemma: string;
  options?: string[];
  choice?: string;
  fallout_hint?: string;
}

export interface PersonalCostMeter {
  trust_with_npcs?: Record<string, number>;
  exposure?: number;
  transformation?: number;
}

export interface UnrecoveredHook {
  round_raised: number;
  hook_text: string;
  status: "open" | "recovered" | "abandoned";
}

export interface CaseBoard {
  // Tier 1
  current_objective?: string;
  unresolved_questions?: UnresolvedQuestion[];
  npc_dynamic?: Record<string, NpcDynamicEntry>;
  time_pressure?: TimePressure;

  // Tier 2 mystery
  suspects?: Suspect[];

  // Tier 3 emotional
  moral_dilemma_log?: MoralDilemma[];
  personal_cost_meter?: PersonalCostMeter;
  unrecovered_hooks?: UnrecoveredHook[];

  // Derived: GET /case-board injects it; client also derives from narrative_arc.
  progress_phase?: string;
}

// --- Ending Summary types ---

export interface PathNode {
  time: string;
  event: string;
  summary: string;
  impact: "positive" | "negative" | "neutral";
}

export interface EvidenceReview {
  found: string[];
  missed: string[];
  accuracy: number;
}

export interface GameSummary {
  ending_narrative: string;
  path_review: PathNode[];
  evidence_review: EvidenceReview | null;
}

export interface WorldListItem {
  id: string;
  name: string;
  description: string;
  genre: string;
  era: string;
  difficulty: number;
  estimated_time: string;
  cover_image: string;
  hero_image?: string;
  play_count: number;
  has_script: boolean;
}

export interface CharacterDTO {
  id: string;
  name: string;
  description: string;
  abilities: string[];
  starting_location: string;
  starting_inventory: string[];
  avatar: string | null;
}

export interface ScriptDTO {
  id: string;
  name: string;
  description: string;
  difficulty: number;
  estimated_time: string;
  cover_image: string | null;
  // WorldCharacter id 列表。非空 = 该剧本仅这些角色可玩；空 = 放行世界全部可玩角色。
  playable_character_ids: string[];
}

export interface StartStageRelation {
  npc: string;
  standing: string;
}

export interface StartStage {
  id: string;
  milestone: string; // 进度里程碑（炼气期 / 熹贵妃）—— 行标题主体
  subtitle: string; // 情境定位（七玄门少年）
  tagline: string; // 节奏取向（爽感流，开局就有分量）
  order: number;
  start_location: string;
  opening_framing: string;
  known_relations: StartStageRelation[];
}

export interface CharacterStartStages {
  // 这套阶段属于哪个可玩角色。一个世界可有多个弧线角色各配一套阶段。
  character_id: string;
  stages: StartStage[];
}

export interface FreeStartStages {
  characters: CharacterStartStages[];
}

export interface WorldDetail {
  id: string;
  name: string;
  description: string;
  genre: string;
  era: string;
  difficulty: number;
  estimated_time: string;
  cover_image: string;
  hero_image?: string | null;
  free_setting: string | null;
  has_script_mode: boolean;
  characters: CharacterDTO[];
  scripts: ScriptDTO[];
  free_start_stages?: FreeStartStages | null;
}

export interface LocationDraft {
  name: string;
  description: string;
}

export interface NPCDraft {
  name: string;
  personality: string;
  secret?: string | null;
  knowledge: string[];
  schedule: Record<string, string>;
  initial_location: string;
}

export interface CharacterDraft {
  name: string;
  description: string;
  abilities: string[];
  starting_location: string;
  starting_inventory: string[];
}

export interface WorldCharacterDraft {
  name: string;
  personality: string;
  secret?: string | null;
  knowledge: string[];
  schedule: Record<string, string>;
  initial_location: string;
  playable: boolean;
  description?: string | null;
  abilities: string[];
  starting_inventory: string[];
  avatar?: string | null;
}

export interface VisualStyleDraft {
  version?: number;
  genre_category?: string;
  culture?: string;
  art_style?: string;
  style_scores?: Array<{
    style: string;
    score: number;
    reason?: string;
  }>;
}

export interface WorldDraftPayload {
  name: string;
  description: string;
  genre: string;
  era: string;
  difficulty: number;
  estimated_time: string;
  base_setting: string;
  free_setting: string;
  locations: LocationDraft[];
  world_characters: WorldCharacterDraft[];
  cover_image?: string | null;
  hero_image?: string | null;
  visual_style?: VisualStyleDraft | null;
}

export interface GenerateProgressEvent {
  phase: string;
  message: string;
}

export interface EventDraft {
  name: string;
  trigger_type: string;
  trigger_condition: Record<string, unknown>;
  description: string;
  effects: Record<string, unknown>;
  priority?: number;
}

export interface EndingDraft {
  ending_type: string;
  title: string;
  description: string;
  hard_conditions?: Record<string, unknown> | null;
  soft_conditions?: string | null;
  priority?: number;
}

export interface ScriptDraftPayload {
  name: string;
  description: string;
  difficulty: number;
  estimated_time: string;
  script_setting: string;
  events: EventDraft[];
  clues: Record<string, unknown>;
  endings: EndingDraft[];
  cover_image?: string | null;
  // WorldCharacter id 列表。空 = 放行世界全部可玩角色。生成时由 AI 预填，可在编辑器调整。
  playable_character_ids: string[];
}

export interface WorldPlayableCharacterRef {
  id: string;
  name: string;
  avatar: string | null;
}

export interface AdminGenerationTaskEvent {
  id: string;
  seq: number;
  event: "progress" | "warning" | "result" | "error" | "done";
  payload: Record<string, unknown>;
}

export interface AdminGenerationTaskSummary {
  id: string;
  kind: "world" | "script";
  draft_type: "world_draft" | "script_draft";
  draft_id: string;
  generation_run_id?: string | null;
  root_task_id?: string | null;
  parent_task_id?: string | null;
  world_spec?: Record<string, unknown> | null;
  world_spec_version?: number;
  payload_revision?: number;
  payload_hash?: string | null;
  status: "pending" | "running" | "succeeded" | "failed" | "cancel_requested" | "cancelled";
  current_phase: string | null;
  current_code: string | null;
  current_message: string | null;
  last_event_seq: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  events: AdminGenerationTaskEvent[];
}

export interface AdminGenerationTaskCreateResponse {
  draft_id: string;
  task_id: string;
  draft_url: string;
}

// review_status lives on the draft; "editing" when there is no pending review.
export type ReviewStatus = "editing" | "submitted" | "rejected";

export interface AdminWorldPublishedItem {
  id: string;
  name: string;
  description: string;
  genre: string;
  era: string;
  cover_image: string;
  status: string; // private | published | withdrawn
  is_owner: boolean;
  has_draft: boolean;
  draft_id: string | null;
  review_status: ReviewStatus;
  review_note: string | null;
  script_count: number;
}

export interface AdminWorldDraftListItem {
  id: string;
  name: string;
  description: string;
  world_id: string | null;
  cover_image?: string | null;
  hero_image?: string | null;
  updated_at: string;
  generation_status?: AdminGenerationTaskSummary["status"] | null;
  generation_task_id?: string | null;
}

export interface AdminWorldListResponse {
  published: AdminWorldPublishedItem[];
  drafts: AdminWorldDraftListItem[];
}

export interface AdminWorldDraftDetail {
  id: string;
  world_id: string | null;
  payload: WorldDraftPayload;
  payload_revision: number;
  payload_hash: string | null;
  quality_status: "not_requested" | "pending" | "running" | "passed" | "needs_review" | "failed" | "stale" | "waived";
  created_at: string;
  updated_at: string;
  generation_task?: AdminGenerationTaskSummary | null;
  /** 在跑的 AI 精修任务（pending/running）—— 重进草稿页时据此重连精修流恢复 */
  active_refine_task?: { id: string; status: string; last_event_seq: number } | null;
}

export interface AdminScriptPublishedItem {
  id: string;
  name: string;
  description: string;
  difficulty: number;
  estimated_time: string;
  status: string; // private | published | withdrawn
  is_published: boolean;
  is_owner: boolean;
  has_draft: boolean;
  draft_id: string | null;
  review_status: ReviewStatus;
  review_note: string | null;
}

export interface AdminScriptDraftListItem {
  id: string;
  world_id: string;
  name: string;
  description: string;
  updated_at: string;
  generation_status?: AdminGenerationTaskSummary["status"] | null;
  generation_task_id?: string | null;
}

export interface AdminScriptListResponse {
  world: {
    id: string;
    name: string;
  };
  published: AdminScriptPublishedItem[];
  drafts: AdminScriptDraftListItem[];
}

export interface AdminScriptDraftDetail {
  id: string;
  world_id: string;
  script_id: string | null;
  payload: ScriptDraftPayload;
  // 该剧本所属世界的全部可玩角色，供可玩角色多选清单渲染。
  world_playable_characters: WorldPlayableCharacterRef[];
  created_at: string;
  updated_at: string;
  generation_task?: AdminGenerationTaskSummary | null;
}

export type ModelProviderType = "openai_compatible" | "xai" | "gemini" | "seedream_image";
export type ModelKind = "text" | "image";
export type ModelCapability =
  | "chat_basic"
  | "streaming"
  | "tool_use"
  | "json_output"
  | "image_generation"
  | "web_search";
export type ModelProviderStatus = "active" | "disabled" | "invalid";
export type ProviderModelStatus = "unverified" | "partial" | "ready" | "failed" | "disabled";

export interface ModelProviderSummary {
  id: string;
  name: string;
  provider_type: ModelProviderType;
  base_url: string | null;
  api_key_env_name: string;
  api_key_available: boolean;
  extra_config: Record<string, unknown>;
  status: ModelProviderStatus;
  last_healthcheck_at: string | null;
  last_healthcheck_error: string | null;
  model_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ModelCapabilityProbeSummary {
  capability: ModelCapability;
  status: "passed" | "failed" | "skipped";
  latency_ms: number;
  error_message: string | null;
  response_sample: string | null;
  verified_at: string | null;
  expires_at: string | null;
}

export interface ProviderModelSummary {
  id: string;
  provider_id: string;
  model_id: string;
  display_name: string;
  model_kind: ModelKind;
  is_enabled: boolean;
  notes: string | null;
  status: ProviderModelStatus;
  binding_slots: string[];
  provider: ModelProviderSummary;
  probes: Partial<Record<ModelCapability, ModelCapabilityProbeSummary | null>>;
  created_at: string | null;
  updated_at: string | null;
}

export interface ModelSlotBoundModelSummary {
  id: string;
  model_id: string;
  display_name: string;
  model_kind: ModelKind;
  provider: {
    id: string;
    name: string;
    provider_type: ModelProviderType;
  } | null;
}

export interface ModelSlotBindingSummary {
  id: string;
  status: string;
  last_verified_at: string | null;
  last_verified_error: string | null;
  model: ModelSlotBoundModelSummary | null;
}

export interface ModelSlotSummary {
  slot_name: string;
  label: string;
  description: string;
  model_kind: ModelKind;
  required_capabilities: ModelCapability[];
  binding: ModelSlotBindingSummary | null;
}

export interface ModelProviderListResponse {
  providers: ModelProviderSummary[];
  provider_types: ModelProviderType[];
}

export interface ProviderModelListResponse {
  models: ProviderModelSummary[];
  providers: ModelProviderSummary[];
  model_kinds: ModelKind[];
  capabilities: ModelCapability[];
}

export interface ModelSlotListResponse {
  slots: ModelSlotSummary[];
}

export interface ModelDashboardResponse {
  providers: ModelProviderSummary[];
  provider_types: ModelProviderType[];
  models: ProviderModelSummary[];
  model_kinds: ModelKind[];
  capabilities: ModelCapability[];
  slots: ModelSlotSummary[];
}

export interface ModelProviderDeleteResponse {
  affected_slots: string[];
}

export interface ProviderModelProbeResponse {
  model_id: string;
  probes: Partial<Record<ModelCapability, ModelCapabilityProbeSummary | null>>;
}

export interface ModelHealthcheckModelResult {
  model_id: string;
  display_name: string;
  capability: ModelCapability;
  status: "passed" | "failed";
  error: string | null;
}

export interface ModelProviderHealthcheckResponse {
  ok: boolean;
  message: string;
  error: string | null;
  model_results: ModelHealthcheckModelResult[];
  provider: ModelProviderSummary;
}

export interface GameHistoryItem {
  session_id: string;
  // start 页查重需要：同 (world_id, script_id) 或 free 模式同 (world_id, character_id)
  // 已有 active 会话时弹「继续 / 放弃旧的开新」。
  world_id: string;
  script_id?: string | null;
  character_id: string;
  world_name: string;
  // 剧本模式下的剧本名/封面（自由模式为 null，回落到世界封面）
  script_name?: string | null;
  script_cover_image?: string | null;
  character_name: string;
  status: string;
  ending_type: string | null;
  started_at: string;
  last_played_at: string;
  cover_image?: string | null;
  rounds_played?: number;
  current_time?: string | null;
  current_location?: string | null;
  mode?: string | null;
  genre?: string | null;
  era?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "narrator";
  content: string;
  timestamp: number;
}

export type PlayStreamPhase = "idle" | "processing" | "streaming" | "done" | "error";

/**
 * 思考态演进进度的阶段（v2）。后端蹭 director 流式真实里程碑发出；
 * 文案在前端按 next-intl 拼装（play.processing.*），数据真实、每回合不同。
 */
export type ProcessingStage = "casting" | "received" | "reasoning" | "npcs_entering" | "writing";

export interface ProcessingEventPayload {
  phase: string;
  focus_npcs: string[];
  flavor: string;
  /** v2 思考态主路径：演进进度阶段，驱动 logo + i18n 文案。缺省 = 呼吸态（仅 logo）。 */
  stage?: ProcessingStage;
  /** stage="reasoning" 携带：玩家这次输入的截断摘要，用于"推演『{input_summary}』"。 */
  input_summary?: string;
  /** stage="npcs_entering" 携带：进场的真实 active NPC 名。 */
  npcs?: string[];
  /**
   * 来源分类：
   *  - "phase"：v1 通用阶段模板（directing / thinking / narrating，走 flavor）
   *  - "per_npc"：v1 per-NPC focus 文本（走 flavor）
   *  - "progress"：v2 思考态演进进度（走 stage）
   * 缺省视为 "phase"。
   */
  kind?: "phase" | "per_npc" | "progress";
}

export interface EndingResult {
  ending_type: string;
  title: string;
  summary?: GameSummary;
}

export interface SessionMessageDetail {
  role: string;
  content: string;
  created_at: string;
}

export interface GameSessionDetail {
  session_id: string;
  status: string;
  world_name: string;
  character_name: string;
  character_description: string;
  character_abilities: string[];
  game_state: GameState;
  messages: SessionMessageDetail[];
  mode?: string;
  script_type?: string;
}
