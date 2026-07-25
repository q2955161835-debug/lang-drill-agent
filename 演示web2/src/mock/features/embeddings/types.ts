export type EmbeddingMode =
  | "off"
  | "local"
  | "huggingface_cloud"
  | "openai_compatible";

export type EmbeddingIdentity = {
  provider: string;
  model_id: string;
  revision: string;
  dimensions: number;
};

export type EmbeddingSettings = {
  mode: EmbeddingMode;
  model_id: string;
  revision: string;
  dimensions: number;
  model_dir: string;
  base_url: string;
  api_key_configured: boolean;
  enabled_identity: EmbeddingIdentity | null;
};

export type EmbeddingModelSummary = {
  model_id: string;
  revision: string;
  license: string;
  library: string;
  pipeline_tag: string;
  downloads: number;
  likes: number;
  size_bytes: number;
  compatible: boolean;
  blockers: string[];
  recommended: boolean;
};

export type EmbeddingModelDetail = EmbeddingModelSummary & {
  download_files: string[];
};

export type EmbeddingIndexStatus = {
  target: "knowledge" | "past_papers" | "memory";
  identity_key: string;
  status: "fts_only" | "stale" | "rebuilding" | "indexed" | "failed";
  indexed_count: number;
  error_code: string;
  updated_at: string;
};

export type EmbeddingRuntimeStatus = {
  mode: EmbeddingMode;
  loaded: boolean;
  healthy: boolean;
  identity: EmbeddingIdentity | null;
};

export type EmbeddingStatusResponse = {
  settings: EmbeddingSettings;
  effective_mode: "fts" | "hybrid";
  runtime: EmbeddingRuntimeStatus;
  indexes: EmbeddingIndexStatus[];
};

export type EmbeddingJobKind = "model" | "runtime";

export type EmbeddingJobStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type EmbeddingJob = {
  id: string;
  kind: EmbeddingJobKind;
  model_id: string;
  revision: string;
  target_dir: string;
  status: EmbeddingJobStatus;
  files_total: number;
  files_completed: number;
  bytes_downloaded: number;
  cancel_requested: boolean;
  error_code: string;
  error_detail: string;
  created_at: string;
  updated_at: string;
};

export type EmbeddingReindexTarget =
  | "knowledge"
  | "past_papers"
  | "memory";

export type EmbeddingReindexResults = Record<
  EmbeddingReindexTarget,
  { status: string; indexed_count?: number; error?: string }
>;
