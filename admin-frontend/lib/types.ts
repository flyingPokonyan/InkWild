export interface IdentitySummary {
  provider: string;
  email: string | null;
  phone: string | null;
  verified_at?: string | null;
}

export interface CurrentUser {
  id: string;
  nickname: string | null;
  avatar_url: string | null;
  is_admin: boolean;
  can_create: boolean;
  identities: IdentitySummary[];
}

export interface AuditLogItem {
  id: string;
  admin_user_id: string | null;
  admin: { id: string; nickname: string | null } | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  payload: Record<string, unknown>;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
  page: number;
  limit: number;
}

// ────────────── Model management ──────────────
export type ModelProviderType =
  | "openai_compatible"
  | "xai"
  | "gemini"
  | "seedream_image";
export type ModelKind = "text" | "image";
export type ModelCapability =
  | "chat_basic"
  | "streaming"
  | "tool_use"
  | "json_output"
  | "image_generation"
  | "web_search";
export type ModelProviderStatus = "active" | "disabled" | "invalid";
export type ProviderModelStatus =
  | "unverified"
  | "partial"
  | "ready"
  | "failed"
  | "disabled";

export interface ModelProviderSummary {
  id: string;
  name: string;
  provider_type: ModelProviderType;
  base_url: string | null;
  api_key_env_name: string | null;
  api_key_available: boolean;
  api_key_count: number;
  api_key_previews: string[];
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
  input_price_cents_per_million_tokens: number | null;
  output_price_cents_per_million_tokens: number | null;
  image_price_cents_per_image: number | null;
  price_updated_at: string | null;
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

export interface ModelDashboardResponse {
  providers: ModelProviderSummary[];
  provider_types: ModelProviderType[];
  models: ProviderModelSummary[];
  model_kinds: ModelKind[];
  capabilities: ModelCapability[];
  slots: ModelSlotSummary[];
}

export interface ModelProviderHealthcheckResponse {
  ok: boolean;
  message: string;
  error: string | null;
  provider: ModelProviderSummary;
}

// ────────────── Analytics ──────────────
export interface CostKpis {
  today_cents: number;
  today_delta_pct: number | null;
  week_cents: number;
  week_delta_pct: number | null;
  month_cents: number;
  month_delta_pct: number | null;
}

export interface CostTrend {
  window_days: number;
  series: { date: string; cost_cents: number }[];
  total_cents: number;
}

export interface CostByProviderItem {
  provider: string;
  cost_cents: number;
  sessions: number;
  share: number;
}

export interface CostByProvider {
  window_days: number;
  items: CostByProviderItem[];
  total_cents: number;
}

export interface CostByModelItem {
  model_id: string;
  display_name: string;
  provider: string;
  input_tokens: number;
  output_tokens: number;
  calls: number;
  cost_cents: number;
  share: number;
}

export interface CostByModel {
  window_days: number;
  items: CostByModelItem[];
  total_cents: number;
}

export interface CostByPurposeItem {
  purpose: string;
  cost_cents: number;
  input_tokens: number;
  output_tokens: number;
  image_count: number;
  calls: number;
  share: number;
}

export interface CostByPurpose {
  window_days: number;
  items: CostByPurposeItem[];
  total_cents: number;
}

export interface ExpensiveSession {
  session_id: string;
  user_id: string;
  user_nickname: string | null;
  world_id: string;
  world_name: string | null;
  rounds_played: number;
  started_at: string | null;
  last_played_at: string | null;
  ended_at: string | null;
  duration_minutes: number;
  cost_cents: number;
}

export interface ExpensiveSessions {
  window_days: number;
  items: ExpensiveSession[];
}

export interface SessionCostSummary {
  window_days: number;
  total_sessions: number;
  total_cost_cents: number;
  avg_cost_cents: number;
  p50_cost_cents: number;
  p90_cost_cents: number;
  max_cost_cents: number;
}

export interface GenerationSummary {
  window_days: number;
  kind: string | null;
  total_tasks: number;
  by_status: Record<string, number>;
}

export interface DashboardKpis {
  spend: CostKpis;
  active_sessions_24h: number;
  failed_generations_24h: number;
  new_users_7d: number;
  new_worlds_7d: number;
  new_scripts_7d: number;
  models_missing_pricing: number;
  pending_reviews: number;
}

// ────────────── User management ──────────────
export type UserStatus = "active" | "banned";
export type UserPermissionFilter = "all" | "admin" | "can_create" | "no_perm";

export interface AdminUserListItem {
  id: string;
  nickname: string | null;
  avatar_url: string | null;
  status: UserStatus | string;
  is_admin: boolean;
  can_create: boolean;
  is_verified: boolean;
  verified_at: string | null;
  created_at: string | null;
  last_login_at: string | null;
  identities: IdentitySummary[];
  drafts_count: number;
  published_worlds_count: number;
  published_scripts_count: number;
}

export interface AdminUserListSummary {
  total: number;
  verified_count: number;
  unverified_count: number;
  admin_count: number;
  can_create_count: number;
  banned_count: number;
}

export interface AdminUserListResponse {
  items: AdminUserListItem[];
  total: number;
  page: number;
  limit: number;
  summary: AdminUserListSummary;
}

export interface UserRecentSession {
  id: string;
  world_id: string;
  world_name: string | null;
  rounds_played: number;
  status: string;
  last_played_at: string | null;
  cost_cents: number;
}

export interface AdminUserDetail extends AdminUserListItem {
  lifetime_cost_cents: number;
  recent_sessions: UserRecentSession[];
}

export interface UpdateUserPayload {
  is_admin?: boolean;
  can_create?: boolean;
  status?: UserStatus;
}

// ────────────── Generation tasks ──────────────
export type GenerationTaskKind = "world" | "script";
export type GenerationTaskStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface GenerationTaskListItem {
  id: string;
  kind: GenerationTaskKind;
  draft_type: string;
  draft_id: string | null;
  status: GenerationTaskStatus;
  current_phase: string | null;
  current_code?: string | null;
  current_message: string | null;
  last_event_seq: number;
  error_message: string | null;
  prompt_preview: string;
  fidelity_mode: string | null;
  ip_name: string | null;
  generated_name: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface GenerationTaskListResponse {
  items: GenerationTaskListItem[];
  total: number;
  page: number;
  limit: number;
}

export interface GenerationTaskEvent {
  id: string;
  seq: number;
  event: string;
  payload: Record<string, unknown>;
}

export interface GenerationTaskDetail extends GenerationTaskListItem {
  events: GenerationTaskEvent[];
  request_payload: Record<string, unknown>;
  phase_kind?: "phase_a" | "phase_b" | string | null;
  companion_task?: (Omit<GenerationTaskDetail, "companion_task"> & {
    phase_kind?: "phase_a" | "phase_b" | string | null;
  }) | null;
}

// ────────────── Content governance ──────────────
export interface PublishedContentItem {
  id: string;
  name: string;
  author: string;
  author_id: string | null;
  status: string;
  created_at: string | null;
}
