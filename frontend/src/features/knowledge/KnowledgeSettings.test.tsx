// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KnowledgeSettings } from "./KnowledgeSettings";
import type { KnowledgeApi } from "./api";
import type { EmbeddingApi } from "../embeddings/api";

afterEach(() => {
  cleanup();
});

function createApi(): KnowledgeApi {
  return {
    listDocuments: vi.fn().mockResolvedValue([]),
    importDocument: vi.fn().mockResolvedValue({}),
    search: vi.fn().mockResolvedValue({ mode: "fts", items: [] }),
    reindex: vi.fn().mockResolvedValue({}),
    deleteDocument: vi.fn().mockResolvedValue({ deleted: true }),
  };
}

function createEmbeddingApi(): EmbeddingApi {
  return {
    status: vi.fn().mockResolvedValue({
      settings: {
        mode: "off",
        model_id: "",
        revision: "",
        dimensions: 0,
        model_dir: "",
        base_url: "",
        api_key_configured: false,
        enabled_identity: null,
      },
      effective_mode: "fts",
      runtime: { mode: "off", loaded: false, healthy: false, identity: null },
      indexes: [],
    }),
    saveSettings: vi.fn().mockResolvedValue({}),
    listModels: vi.fn().mockResolvedValue({ recommendations: [], search_results: [] }),
    modelDetail: vi.fn().mockResolvedValue({ detail: null }),
    startDownload: vi.fn().mockResolvedValue({ job: null }),
    downloadStatus: vi.fn().mockResolvedValue({ job: null }),
    cancelDownload: vi.fn().mockResolvedValue({ job: null }),
    installRuntime: vi.fn().mockResolvedValue({ job: null }),
    reindex: vi.fn().mockResolvedValue({ results: {} }),
    testConnection: vi.fn().mockResolvedValue({ healthy: true }),
  };
}

describe("KnowledgeSettings", () => {
  it("renders the shared staged import queue without writing formal rows", () => {
    const api = createApi();
    render(<KnowledgeSettings api={api} embeddingApi={createEmbeddingApi()} />);
    expect(screen.getByLabelText("拖拽或选择知识库文件")).toBeTruthy();
    expect(api.listDocuments).toHaveBeenCalled();
    expect(api.importDocument).not.toHaveBeenCalled();
  });

  it("mounts EmbeddingSettings inside the knowledge panel", async () => {
    const api = createApi();
    const embeddingApi = createEmbeddingApi();
    render(<KnowledgeSettings api={api} embeddingApi={embeddingApi} />);
    expect(await screen.findByLabelText("嵌入模型设置")).toBeTruthy();
    expect(embeddingApi.status).toHaveBeenCalled();
  });
});
