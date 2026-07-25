// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
});

import { ResourceImportQueue } from "./ResourceImportQueue";
import type { ResourceImportApi } from "../features/resourceImports/api";
import type { ResourceImportRecord } from "../features/resourceImports/types";

function createRecord(overrides: Partial<ResourceImportRecord> = {}): ResourceImportRecord {
  return {
    id: "import_test",
    target: "knowledge",
    filename: "notes.md",
    status: "staged",
    preview: null,
    error_code: "",
    error_detail: "",
    ...overrides,
  };
}

function createApi(): ResourceImportApi & { calls: { stage: number; parse: number; confirm: number; cancel: number } } {
  const calls = { stage: 0, parse: 0, confirm: 0, cancel: 0 };
  return {
    calls,
    stage: vi.fn(async (_target, file) => {
      calls.stage += 1;
      return createRecord({ filename: file.name });
    }),
    parse: vi.fn(async (id) => {
      calls.parse += 1;
      return createRecord({
        id,
        status: "preview_ready",
        preview: {
          title: "Notes",
          language: "en",
          year: null,
          parser: "text",
          text_preview: "consecutive",
          characters: 11,
          pages: null,
          chunk_count: 1,
          question_count: 0,
          question_types: [],
          answer_confidence: 0,
          warnings: [],
        },
      });
    }),
    confirm: vi.fn(async () => {
      calls.confirm += 1;
      return { document: { id: "doc_1" } };
    }),
    cancel: vi.fn(async () => {
      calls.cancel += 1;
    }),
  } as unknown as ResourceImportApi & { calls: { stage: number; parse: number; confirm: number; cancel: number } };
}

function dropFile(zone: HTMLElement, ...files: File[]) {
  fireEvent.drop(zone, {
    dataTransfer: { files, types: ["Files"] },
  });
}

describe("ResourceImportQueue", () => {
  it("keeps dropped files local until parse is clicked", () => {
    const api = createApi();
    render(
      <ResourceImportQueue
        target="knowledge"
        api={api}
        defaultMetadata={{ language: "en" }}
      />,
    );
    const file = new File(["notes"], "notes.md", { type: "text/markdown" });
    dropFile(screen.getByLabelText("拖拽或选择知识库文件"), file);

    expect(screen.getByText("notes.md")).toBeTruthy();
    expect(api.stage).not.toHaveBeenCalled();
  });

  it("parses before enabling confirmation", async () => {
    const api = createApi();
    render(
      <ResourceImportQueue
        target="past_paper"
        api={api}
        defaultMetadata={{ exam_id: "cet4" }}
      />,
    );
    const file = new File(["paper"], "paper.md", { type: "text/markdown" });
    dropFile(screen.getByLabelText("拖拽或选择真题文件"), file);

    fireEvent.click(screen.getByRole("button", { name: "解析预览" }));

    const confirm = await screen.findByRole("button", { name: "确认入库" }) as HTMLButtonElement;
    await waitFor(() => expect(confirm.disabled).toBe(false));
    expect(api.parse).toHaveBeenCalled();
  });

  it("removes the item after successful confirmation", async () => {
    const api = createApi();
    render(
      <ResourceImportQueue
        target="knowledge"
        api={api}
        defaultMetadata={{ language: "en" }}
      />,
    );
    const file = new File(["notes"], "notes.md", { type: "text/markdown" });
    dropFile(screen.getByLabelText("拖拽或选择知识库文件"), file);

    fireEvent.click(screen.getByRole("button", { name: "解析预览" }));
    await screen.findByRole("button", { name: "确认入库" });
    fireEvent.click(screen.getByRole("button", { name: "确认入库" }));

    await waitFor(() => expect(api.confirm).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText("notes.md")).toBeNull());
  });

  it("rejects more than twenty files at once", () => {
    const api = createApi();
    render(
      <ResourceImportQueue
        target="knowledge"
        api={api}
        defaultMetadata={{ language: "en" }}
      />,
    );
    const zone = screen.getByLabelText("拖拽或选择知识库文件");
    const files = Array.from({ length: 22 }, (_, index) =>
      new File([`note${index}`], `note${index}.md`, { type: "text/markdown" }),
    );
    dropFile(zone, ...files);

    expect(screen.getAllByText(/note\d+\.md/).length).toBe(20);
  });

  it("cancels a staged item on demand", async () => {
    const api = createApi();
    render(
      <ResourceImportQueue
        target="knowledge"
        api={api}
        defaultMetadata={{ language: "en" }}
      />,
    );
    const file = new File(["notes"], "notes.md", { type: "text/markdown" });
    dropFile(screen.getByLabelText("拖拽或选择知识库文件"), file);

    fireEvent.click(screen.getByRole("button", { name: "移除" }));
    await waitFor(() => expect(api.cancel).not.toHaveBeenCalled());
    expect(screen.queryByText("notes.md")).toBeNull();
  });
});
