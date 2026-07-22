// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PastPaperLibrary } from "./PastPaperLibrary";
import type { PastPaperLibraryApi } from "./api";

function createApi(): PastPaperLibraryApi {
  return {
    catalog: vi.fn().mockResolvedValue({
      exam_id: "cet4",
      remote_count: 1,
      installed_count: 0,
      sources: [
        {
          id: "cet4-2025-06-1",
          exam_id: "cet4",
          title: "CET-4 2025 June Set 1",
          source_url: "https://source.test/2025-06-set1.pdf",
          year: 2025,
          session: "june",
          set_number: 1,
          installed: false,
        },
      ],
      documents: [],
      imports: [],
      settings: {
        exam_id: "cet4",
        auto_sync: false,
        sync_cadence_hours: 24,
        recent_count: 3,
        allowed_sources: [],
        parser: "auto",
        auto_distill: false,
        verified_answers_only: true,
        long_tail_min_ratio: 0.1,
        max_question_type_ratio: 0.35,
        coverage_window: 20,
      },
    }),
    sync: vi.fn().mockResolvedValue({}),
    search: vi.fn().mockResolvedValue({ mode: "fts", items: [] }),
    distill: vi.fn().mockResolvedValue({ status: "insufficient_evidence", findings: [] }),
    reparse: vi.fn().mockResolvedValue({}),
    reindex: vi.fn().mockResolvedValue({}),
    saveSettings: vi.fn().mockResolvedValue({}),
  };
}

describe("PastPaperLibrary（真题库）", () => {
  it("labels a discovered paper as not downloaded（将发现的试卷标记为尚未下载）", async () => {
    render(<PastPaperLibrary examId="cet4" api={createApi()} />);

    expect(await screen.findByText("尚未下载")).toBeTruthy();
    expect(screen.getByText("本地真题 0")).toBeTruthy();
    expect(screen.getByText("远程目录 1")).toBeTruthy();
  });
});
