import { apiGet, apiPost } from "../../api";
import type {
  EmbeddingJob,
  EmbeddingModelDetail,
  EmbeddingModelSummary,
  EmbeddingReindexResults,
  EmbeddingReindexTarget,
  EmbeddingStatusResponse,
} from "./types";

export type EmbeddingSettingsPatch = {
  mode?: "off" | "local" | "huggingface_cloud" | "openai_compatible";
  model_id?: string;
  revision?: string;
  dimensions?: number;
  model_dir?: string;
  base_url?: string;
  api_key?: string;
  activate?: boolean;
};

export type EmbeddingApi = {
  status(): Promise<EmbeddingStatusResponse>;
  saveSettings(patch: EmbeddingSettingsPatch): Promise<EmbeddingStatusResponse>;
  listModels(query: string): Promise<{
    recommendations: EmbeddingModelSummary[];
    search_results: EmbeddingModelSummary[];
  }>;
  modelDetail(modelId: string, revision?: string): Promise<{ detail: EmbeddingModelDetail }>;
  startDownload(payload: {
    model_id: string;
    revision: string;
    target_dir?: string;
    confirmed: boolean;
  }): Promise<{ job: EmbeddingJob }>;
  downloadStatus(jobId: string): Promise<{ job: EmbeddingJob }>;
  cancelDownload(jobId: string): Promise<{ job: EmbeddingJob | null }>;
  installRuntime(confirmed: boolean): Promise<{ job: EmbeddingJob }>;
  reindex(
    targets: EmbeddingReindexTarget[],
    confirmed: boolean,
  ): Promise<{ results: EmbeddingReindexResults }>;
  testConnection(): Promise<{
    healthy: boolean;
    identity?: EmbeddingModelSummary;
    error?: string;
  }>;
};

export const embeddingApi: EmbeddingApi = {
  status() {
    return apiGet<EmbeddingStatusResponse>("/api/embeddings/status");
  },
  saveSettings(patch) {
    return apiPost<EmbeddingStatusResponse>("/api/embeddings/settings", patch);
  },
  listModels(query) {
    const trimmed = query.trim();
    const path = trimmed
      ? `/api/embeddings/models?q=${encodeURIComponent(trimmed)}`
      : "/api/embeddings/models";
    return apiGet(path);
  },
  modelDetail(modelId, revision) {
    const params = revision ? `?revision=${encodeURIComponent(revision)}` : "";
    return apiGet(
      `/api/embeddings/models/${encodeURIComponent(modelId)}${params}`,
    );
  },
  startDownload(payload) {
    return apiPost("/api/embeddings/downloads", payload);
  },
  downloadStatus(jobId) {
    return apiGet(`/api/embeddings/downloads/${encodeURIComponent(jobId)}`);
  },
  cancelDownload(jobId) {
    return apiPost(
      `/api/embeddings/downloads/${encodeURIComponent(jobId)}/cancel`,
      {},
    );
  },
  installRuntime(confirmed) {
    return apiPost("/api/embeddings/runtime/install", { confirmed });
  },
  reindex(targets, confirmed) {
    return apiPost("/api/embeddings/reindex", { targets, confirmed });
  },
  testConnection() {
    return apiPost("/api/embeddings/test", {});
  },
};
