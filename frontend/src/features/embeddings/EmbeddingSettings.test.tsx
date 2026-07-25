// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EmbeddingSettings } from "./EmbeddingSettings";
import type { EmbeddingApi } from "./api";
import type {
  EmbeddingModelSummary,
  EmbeddingStatusResponse,
} from "./types";

afterEach(() => {
  cleanup();
});

function buildStatus(
  overrides: {
    settings?: Partial<EmbeddingStatusResponse["settings"]>;
    effective_mode?: EmbeddingStatusResponse["effective_mode"];
    runtime?: Partial<EmbeddingStatusResponse["runtime"]>;
    indexes?: EmbeddingStatusResponse["indexes"];
  } = {},
): EmbeddingStatusResponse {
  const base: EmbeddingStatusResponse = {
    settings: {
      mode: "off",
      model_id: "",
      revision: "",
      dimensions: 0,
      model_dir: "/tmp/embeddings",
      base_url: "",
      api_key_configured: false,
      enabled_identity: null,
    },
    effective_mode: "fts",
    runtime: { mode: "off", loaded: false, healthy: false, identity: null },
    indexes: [],
  };
  return {
    ...base,
    ...overrides,
    settings: { ...base.settings, ...overrides.settings },
    runtime: { ...base.runtime, ...overrides.runtime },
  };
}

function createApi(
  statusResponse: EmbeddingStatusResponse,
  recommendations: EmbeddingModelSummary[] = [],
): EmbeddingApi {
  return {
    status: vi.fn().mockResolvedValue(statusResponse),
    saveSettings: vi.fn().mockResolvedValue(statusResponse),
    listModels: vi
      .fn()
      .mockResolvedValue({ recommendations, search_results: [] }),
    modelDetail: vi.fn().mockResolvedValue({ detail: null as never }),
    startDownload: vi.fn().mockResolvedValue({ job: null as never }),
    downloadStatus: vi.fn().mockResolvedValue({ job: null as never }),
    cancelDownload: vi.fn().mockResolvedValue({ job: null }),
    installRuntime: vi.fn().mockResolvedValue({ job: null as never }),
    reindex: vi.fn().mockResolvedValue({ results: {} as never }),
    testConnection: vi.fn().mockResolvedValue({ healthy: true }),
  };
}

describe("EmbeddingSettings", () => {
  it("shows FTS5 and performs no download while off", async () => {
    const api = createApi(buildStatus({ settings: { mode: "off" } }));
    render(<EmbeddingSettings api={api} />);

    const matches = await screen.findAllByText(/FTS5 全文检索/);
    expect(matches.length).toBeGreaterThan(0);
    expect(api.startDownload).not.toHaveBeenCalled();
  });

  it("requires confirmation before downloading a recommended model", async () => {
    const status = buildStatus({ settings: { mode: "local" } });
    const recommendations: EmbeddingModelSummary[] = [
      {
        model_id: "Qwen/Qwen3-Embedding-0.6B",
        revision: "main",
        license: "apache-2.0",
        library: "sentence-transformers",
        pipeline_tag: "feature-extraction",
        downloads: 0,
        likes: 0,
        size_bytes: 0,
        compatible: true,
        blockers: [],
        recommended: true,
      },
    ];
    const api = createApi(status, recommendations);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<EmbeddingSettings api={api} />);

    const button = await screen.findByRole("button", { name: /下载 Qwen/ });
    fireEvent.click(button);

    expect(confirmSpy).toHaveBeenCalled();
    expect(api.startDownload).not.toHaveBeenCalled();

    confirmSpy.mockRestore();
  });

  it("requires confirmation before rebuilding stale indexes", async () => {
    const identity = {
      provider: "local",
      model_id: "Qwen/Qwen3-Embedding-0.6B",
      revision: "main",
      dimensions: 1024,
    };
    const status = buildStatus({
      settings: { mode: "local", enabled_identity: identity },
      effective_mode: "hybrid",
      runtime: { mode: "local", loaded: true, healthy: true, identity },
      indexes: [
        {
          target: "knowledge",
          identity_key: "",
          status: "stale",
          indexed_count: 0,
          error_code: "",
          updated_at: "",
        },
      ],
    });
    const api = createApi(status);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<EmbeddingSettings api={api} />);

    const button = await screen.findByRole("button", { name: "重新建立向量索引" });
    fireEvent.click(button);

    expect(confirmSpy).toHaveBeenCalled();
    expect(api.reindex).not.toHaveBeenCalled();

    confirmSpy.mockRestore();
  });
});
