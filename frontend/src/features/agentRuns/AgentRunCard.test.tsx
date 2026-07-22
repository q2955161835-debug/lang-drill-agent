// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentRunCard } from "./AgentRunCard";
import type { AgentRunApi, AgentRunDetail } from "./types";

const pausedDetail: AgentRunDetail = {
  run: {
    id: "run-1",
    session_id: "session-1",
    task_type: "agentic_task",
    status: "paused",
    goal: "整理目录并生成报告",
    completion_criteria: ["report.md exists", "verification passed"],
    plan_version: 1,
    error_code: "",
  },
  steps: [
    {
      id: "step-1",
      run_id: "run-1",
      plan_version: 1,
      sequence: 1,
      title: "读取目录",
      description: "读取输入目录",
      tool_names: ["documents.read"],
      completion_criteria: ["目录清单已记录"],
      status: "completed",
      attempts: 1,
      max_attempts: 2,
      lease_owner: "",
      lease_expires_at: null,
      evidence: { files: ["a.md"] },
      error_code: "",
    },
    {
      id: "step-2",
      run_id: "run-1",
      plan_version: 1,
      sequence: 2,
      title: "生成报告",
      description: "写入报告",
      tool_names: ["reports.write"],
      completion_criteria: ["report.md exists"],
      status: "pending",
      attempts: 0,
      max_attempts: 2,
      lease_owner: "",
      lease_expires_at: null,
      evidence: {},
      error_code: "",
    },
    {
      id: "step-3",
      run_id: "run-1",
      plan_version: 1,
      sequence: 3,
      title: "验证报告",
      description: "验证报告内容",
      tool_names: ["reports.verify"],
      completion_criteria: ["verification passed"],
      status: "pending",
      attempts: 0,
      max_attempts: 2,
      lease_owner: "",
      lease_expires_at: null,
      evidence: {},
      error_code: "",
    },
    {
      id: "step-4",
      run_id: "run-1",
      plan_version: 1,
      sequence: 4,
      title: "完成",
      description: "记录结果",
      tool_names: ["runtime.review"],
      completion_criteria: ["run completed"],
      status: "pending",
      attempts: 0,
      max_attempts: 2,
      lease_owner: "",
      lease_expires_at: null,
      evidence: {},
      error_code: "",
    },
  ],
  tool_calls: [],
  approvals: [],
};

function createApi(): AgentRunApi {
  return {
    getDetail: vi.fn().mockResolvedValue(pausedDetail),
    pause: vi.fn().mockResolvedValue(pausedDetail.run),
    resume: vi.fn().mockResolvedValue({ ...pausedDetail.run, status: "queued" }),
    cancel: vi.fn().mockResolvedValue({ ...pausedDetail.run, status: "cancelled" }),
    subscribe: vi.fn().mockReturnValue(() => undefined),
  };
}

afterEach(() => cleanup());

describe("AgentRunCard", () => {
  it("shows resume for a paused persisted run", async () => {
    const api = createApi();

    render(<AgentRunCard run={pausedDetail.run} api={api} />);

    const resume = await screen.findByRole("button", { name: "继续" }) as HTMLButtonElement;
    expect(resume.disabled).toBe(false);
    expect(screen.getByText("步骤 2 / 4")).toBeTruthy();
    expect(screen.getByText("生成报告")).toBeTruthy();
    expect(screen.getByText("documents.read")).toBeTruthy();
    expect(screen.getByText(/a.md/)).toBeTruthy();
  });

  it("invokes resume and refreshes persisted detail", async () => {
    const api = createApi();

    render(<AgentRunCard run={pausedDetail.run} api={api} />);
    fireEvent.click(await screen.findByRole("button", { name: "继续" }));

    await waitFor(() => expect(api.resume).toHaveBeenCalledWith("run-1"));
    await waitFor(() => expect(api.getDetail).toHaveBeenCalledTimes(2));
  });
});
