// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MemorySettings } from "./MemorySettings";
import type { MemoryApi } from "./api";
import type { MemorySettingsState, MemoryStatusResponse } from "./types";

const settings: MemorySettingsState = {
  enabled: true,
  capture_enabled: true,
  recall_enabled: true,
  category_enabled: {
    core: true,
    semantic: true,
    episodic: true,
    procedural: true,
    temporal: true,
    preference: true,
    profile: true,
    learning_weakness: true,
  },
  write_mode: "approval",
  learning_evidence_min: 3,
  confidence_min: 0.7,
  default_ttl_days: 365,
  core_token_budget: 400,
  recall_top_k: 8,
  recall_token_budget: 1200,
  embeddings_enabled: false,
  compaction_flush_enabled: true,
};

const status: MemoryStatusResponse = {
  settings,
  provider: {
    current_primary_id: "builtin",
    providers: { builtin: { healthy: true, detail: "SQLite available" } },
    migration_required: false,
  },
  counts: { active: 1, archived: 0, deleted: 0, candidates: 1 },
};

function createApi(): MemoryApi {
  return {
    status: vi.fn().mockResolvedValue(status),
    listItems: vi.fn().mockResolvedValue([
      {
        id: "memory-1",
        category: "preference",
        scope: "global",
        content: "User prefers concise examples",
        normalized_key: "preference:examples",
        confidence: 0.9,
        importance: 0.8,
        status: "active",
        valid_from: null,
        valid_to: null,
        expires_at: null,
        supersedes_id: null,
        pinned: false,
        metadata: {},
        created_at: "2026-07-22",
        updated_at: "2026-07-22",
      },
    ]),
    itemDetail: vi.fn().mockResolvedValue({ item: {}, evidence: [], revisions: [] }),
    listCandidates: vi.fn().mockResolvedValue([
      {
        id: "candidate-1",
        category: "learning_weakness",
        scope: "global",
        content: "User repeatedly struggles with conditionals",
        normalized_key: "weakness:conditionals",
        confidence: 0.9,
        importance: 0.8,
        status: "staged",
        reason: "approval_required",
        evidence_ids: ["attempt:1", "attempt:2", "attempt:3"],
        evidence_count: 3,
        metadata: {},
        created_at: "2026-07-22",
        updated_at: "2026-07-22",
      },
    ]),
    saveSettings: vi.fn().mockResolvedValue(settings),
    reviewCandidate: vi.fn().mockResolvedValue({}),
    updateItem: vi.fn().mockResolvedValue({}),
    actOnItem: vi.fn().mockResolvedValue({}),
    exportMemory: vi.fn().mockResolvedValue({ schema_version: 1, settings, records: [] }),
    importMemory: vi.fn().mockResolvedValue({ imported_count: 0, skipped_count: 0 }),
    reindex: vi.fn().mockResolvedValue({ indexed_count: 1 }),
    prepareProvider: vi.fn().mockResolvedValue({
      requested_provider_id: "builtin",
      current_primary_id: "builtin",
      switched: false,
      migration_required: false,
      migration_verified: false,
      verification_token: "",
      source_count: 0,
      destination_count: 0,
      detail: "already primary",
    }),
    commitProvider: vi.fn().mockResolvedValue({
      requested_provider_id: "builtin",
      current_primary_id: "builtin",
      switched: true,
      migration_required: false,
      migration_verified: true,
      verification_token: "",
      source_count: 0,
      destination_count: 0,
      detail: "switched",
    }),
  };
}

describe("MemorySettings", () => {
  it("shows pending memory evidence before approval", async () => {
    const api = createApi();

    render(<MemorySettings api={api} />);

    expect(await screen.findByText("等待审核")).toBeTruthy();
    expect(screen.getByText("3 次独立错题")).toBeTruthy();
    expect(screen.getByText("User repeatedly struggles with conditionals")).toBeTruthy();
    expect(api.reviewCandidate).not.toHaveBeenCalled();
  });

  it("requires explicit confirmation before permanent purge", async () => {
    const api = createApi();
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<MemorySettings api={api} />);
    const purge = await screen.findByRole("button", { name: "永久删除记忆" });
    fireEvent.click(purge);

    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    expect(api.actOnItem).not.toHaveBeenCalledWith("memory-1", "purge", true);
  });
});
