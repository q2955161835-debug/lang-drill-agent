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

export type MemorySettingsState = {
  enabled: boolean;
  capture_enabled: boolean;
  recall_enabled: boolean;
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
