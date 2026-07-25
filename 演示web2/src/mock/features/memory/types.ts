export type MemoryCategory =
  | "core"
  | "semantic"
  | "episodic"
  | "procedural"
  | "temporal"
  | "preference"
  | "profile"
  | "learning_weakness";

export type MemoryStatus = "active" | "archived" | "superseded" | "deleted";

// Plan 3 Task 1: 三档记忆模式与三个用户可见组。后端 backend/langdrill_agent/memory/presets.py
// 是权威定义；这里必须与 MODE_LIMITS / GROUP_CATEGORIES 保持一致。
export type MemoryMode = "economy" | "standard" | "deep";

export type MemoryGroup = "about_me" | "learning_history" | "usage_habits";

export type MemoryBudget = {
  mode: MemoryMode;
  configured_limit: number | null;
  available_context_tokens: number;
  reserved_tokens: number;
  effective_tokens: number;
  constrained_by_context: boolean;
};

export type MemorySettingsState = {
  enabled: boolean;
  capture_enabled: boolean;
  recall_enabled: boolean;
  // Plan 3 Task 1: 用户可见的三档模式与三组开关；category_enabled 保留为开发者选项。
  mode: MemoryMode;
  group_enabled: Record<MemoryGroup, boolean>;
  category_enabled: Record<MemoryCategory, boolean>;
  write_mode: "explicit" | "approval" | "balanced" | "proactive";
  learning_evidence_min: number;
  confidence_min: number;
  default_ttl_days: number;
  core_token_budget: number;
  recall_top_k: number;
  recall_token_budget: number;
  embeddings_enabled: boolean;
  compaction_flush_enabled: boolean;
};

export type MemoryItem = {
  id: string;
  category: MemoryCategory;
  scope: string;
  content: string;
  normalized_key: string;
  confidence: number;
  importance: number;
  status: MemoryStatus;
  valid_from: string | null;
  valid_to: string | null;
  expires_at: string | null;
  supersedes_id: string | null;
  pinned: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type MemoryCandidate = {
  id: string;
  category: MemoryCategory;
  scope: string;
  content: string;
  normalized_key: string;
  confidence: number;
  importance: number;
  status: string;
  reason: string;
  evidence_ids: string[];
  evidence_count: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type MemoryEvidence = {
  id: string;
  candidate_id: string | null;
  memory_id: string | null;
  evidence_type: string;
  evidence_ref: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type MemoryRevision = {
  id: number;
  memory_id: string;
  operation: string;
  content: string;
  snapshot: Record<string, unknown>;
  created_at: string;
};

export type MemoryItemDetail = {
  item: MemoryItem;
  evidence: MemoryEvidence[];
  revisions: MemoryRevision[];
};

export type ProviderHealth = {
  healthy: boolean;
  detail: string;
};

export type MemoryStatusResponse = {
  settings: MemorySettingsState;
  provider: {
    current_primary_id: string;
    providers: Record<string, ProviderHealth>;
    migration_required: boolean;
  };
  counts: Record<string, number>;
  // Plan 3 Task 3: 后端 /api/memory/status 已返回 effective_budget 与 group_counts。
  effective_budget?: MemoryBudget;
  group_counts?: Record<MemoryGroup, number>;
};

export type ProviderSwitchResult = {
  requested_provider_id: string;
  current_primary_id: string;
  switched: boolean;
  migration_required: boolean;
  migration_verified: boolean;
  verification_token: string;
  source_count: number;
  destination_count: number;
  detail: string;
};

export type MemoryExport = {
  schema_version: number;
  settings: MemorySettingsState;
  records: Array<Record<string, unknown>>;
};
