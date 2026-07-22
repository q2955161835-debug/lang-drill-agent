// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KnowledgeSettings } from "./KnowledgeSettings";
import type { KnowledgeApi } from "./api";

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
  it("requires explicit confirmation before adding an attachment", () => {
    const api = createApi();
    const file = new File(["# Notes\nconsecutive"], "notes.md", { type: "text/markdown" });

    render(<KnowledgeSettings api={api} />);
    fireEvent.change(screen.getByLabelText("选择知识库文件"), { target: { files: [file] } });

    expect((screen.getByRole("button", { name: "加入知识库" }) as HTMLButtonElement).disabled).toBe(false);
    expect(api.importDocument).not.toHaveBeenCalled();
  });
});
