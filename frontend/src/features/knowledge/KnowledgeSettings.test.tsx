// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KnowledgeSettings } from "./KnowledgeSettings";
import type { KnowledgeApi } from "./api";

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

describe("KnowledgeSettings", () => {
  it("renders the shared staged import queue without writing formal rows", () => {
    const api = createApi();
    render(<KnowledgeSettings api={api} />);
    expect(screen.getByLabelText("拖拽或选择知识库文件")).toBeTruthy();
    expect(api.listDocuments).toHaveBeenCalled();
    expect(api.importDocument).not.toHaveBeenCalled();
  });
});
