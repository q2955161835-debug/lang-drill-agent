import { apiGet, apiPost } from "../../api";
import type {
  MemoryCandidate,
  MemoryExport,
  MemoryItem,
  MemoryItemDetail,
  MemorySettingsState,
  MemoryStatusResponse,
  ProviderSwitchResult,
} from "./types";

export type MemoryApi = {
  status(): Promise<MemoryStatusResponse>;
  listItems(query?: string): Promise<MemoryItem[]>;
  itemDetail(memoryId: string): Promise<MemoryItemDetail>;
  listCandidates(): Promise<MemoryCandidate[]>;
  saveSettings(settings: Partial<MemorySettingsState>): Promise<MemorySettingsState>;
  reviewCandidate(candidateId: string, action: "approve" | "reject"): Promise<unknown>;
  updateItem(memoryId: string, patch: Partial<MemoryItem>): Promise<MemoryItem>;
  actOnItem(memoryId: string, action: string, confirmed?: boolean): Promise<unknown>;
  exportMemory(): Promise<MemoryExport>;
  importMemory(records: Array<Record<string, unknown>>): Promise<{ imported_count: number; skipped_count: number }>;
  reindex(): Promise<{ indexed_count: number }>;
  prepareProvider(providerId: string): Promise<ProviderSwitchResult>;
  commitProvider(providerId: string, verificationToken: string): Promise<ProviderSwitchResult>;
};

export const memoryApi: MemoryApi = {
  status() {
    return apiGet("/api/memory/status");
  },
  async listItems(query = "") {
    const params = new URLSearchParams({ status: "all" });
    if (query.trim()) params.set("query", query.trim());
    const response = await apiGet<{ items: MemoryItem[] }>(`/api/memory/items?${params.toString()}`);
    return response.items;
  },
  itemDetail(memoryId) {
    return apiGet(`/api/memory/items/${encodeURIComponent(memoryId)}`);
  },
  async listCandidates() {
    const response = await apiGet<{ candidates: MemoryCandidate[] }>("/api/memory/candidates");
    return response.candidates;
  },
  async saveSettings(settings) {
    const response = await apiPost<{ settings: MemorySettingsState }>("/api/memory/settings", settings);
    return response.settings;
  },
  reviewCandidate(candidateId, action) {
    return apiPost(`/api/memory/candidates/${encodeURIComponent(candidateId)}/review`, { action });
  },
  async updateItem(memoryId, patch) {
    const response = await apiPost<{ item: MemoryItem }>(`/api/memory/items/${encodeURIComponent(memoryId)}`, patch);
    return response.item;
  },
  actOnItem(memoryId, action, confirmed = false) {
    return apiPost(`/api/memory/items/${encodeURIComponent(memoryId)}/action`, { action, confirmed });
  },
  exportMemory() {
    return apiGet("/api/memory/export");
  },
  importMemory(records) {
    return apiPost("/api/memory/import", { records });
  },
  reindex() {
    return apiPost("/api/memory/reindex", {});
  },
  async prepareProvider(providerId) {
    const response = await apiPost<{ result: ProviderSwitchResult }>("/api/memory/provider/prepare", { provider_id: providerId });
    return response.result;
  },
  async commitProvider(providerId, verificationToken) {
    const response = await apiPost<{ result: ProviderSwitchResult }>("/api/memory/provider/commit", {
      provider_id: providerId,
      verification_token: verificationToken,
    });
    return response.result;
  },
};
