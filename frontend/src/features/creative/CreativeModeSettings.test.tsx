// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreativeModeSettings } from "./CreativeModeSettings";
import type { CreativeApi } from "./api";
import type {
  CreativeApprovalRequest,
  CreativeModeSettingsState,
  CreativeRuntimeStatus,
  CreativeStatusResponse,
} from "./types";

const baseSettings: CreativeModeSettingsState = {
  enabled: false,
  permission_profile: "request_approval",
  rules_version: 1,
  rules: [],
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:00:00Z",
};

const enabledSettings: CreativeModeSettingsState = {
  ...baseSettings,
  enabled: true,
  permission_profile: "smart_approval",
};

function makeRuntime(overrides: Partial<CreativeRuntimeStatus> = {}): CreativeRuntimeStatus {
  return {
    state: "ready",
    version: "0.80.10",
    error_code: "",
    details: {},
    updated_at: "2026-07-22T00:00:00Z",
    ready: true,
    log_path: "",
    failure_code: "",
    attempted_steps: [],
    manual_install_command: "",
    ...overrides,
  };
}

function makeStatus(
  settings: CreativeModeSettingsState,
  runtime: CreativeRuntimeStatus,
  approvals: CreativeApprovalRequest[] = [],
): CreativeStatusResponse {
  return { settings, runtime, approvals };
}

function createApi(
  statusResponse: CreativeStatusResponse,
  overrides: Partial<CreativeApi> = {},
): CreativeApi {
  return {
    status: vi.fn().mockResolvedValue(statusResponse),
    runtimeStatus: vi.fn().mockResolvedValue(statusResponse.runtime),
    saveSettings: vi.fn().mockResolvedValue(statusResponse.settings),
    listApprovals: vi.fn().mockResolvedValue(statusResponse.approvals),
    resolveApproval: vi.fn().mockResolvedValue({ ok: true }),
    listAuditEvents: vi.fn().mockResolvedValue([]),
    repairRuntime: vi.fn().mockResolvedValue({
      ok: true,
      log_path: "",
      detail: "",
    }),
    openRuntimeLog: vi.fn().mockResolvedValue({ path: "" }),
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("CreativeModeSettings readiness", () => {
  it("disables enable toggle when runtime install failed and shows repair plan", async () => {
    const runtime = makeRuntime({
      state: "install_failed",
      ready: false,
      failure_code: "npm_failed",
      attempted_steps: ["download node", "npm install"],
      log_path: "C:/logs/pi-runtime.log",
      manual_install_command: "powershell repair-pi-runtime.ps1",
    });
    const api = createApi(makeStatus(baseSettings, runtime));

    render(<CreativeModeSettings api={api} />);

    expect(await screen.findByText(/Pi 运行时未就绪/)).toBeTruthy();
    const toggle = screen.getByRole("checkbox", { name: /启用创造模式/ });
    expect((toggle as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("npm_failed")).toBeTruthy();
    expect(screen.getByText("powershell repair-pi-runtime.ps1")).toBeTruthy();
    expect(screen.getByText("C:/logs/pi-runtime.log")).toBeTruthy();
    expect(screen.getByText("download node")).toBeTruthy();
    expect(screen.getByRole("button", { name: /一键修复/ })).toBeTruthy();
  });

  it("triggers repair when one-click button is clicked", async () => {
    const runtime = makeRuntime({
      state: "corrupt",
      ready: false,
      failure_code: "hash_mismatch",
    });
    const repairSpy = vi.fn().mockResolvedValue({
      ok: true,
      log_path: "C:/logs/pi-runtime.log",
      detail: "repair completed",
    });
    const api = createApi(makeStatus(baseSettings, runtime), {
      repairRuntime: repairSpy,
    });

    render(<CreativeModeSettings api={api} />);
    const button = await screen.findByRole("button", { name: /一键修复/ });
    fireEvent.click(button);

    await waitFor(() => expect(repairSpy).toHaveBeenCalled(), { timeout: 3000 });
    expect(await screen.findByText(/repair completed/)).toBeTruthy();
  });
});

describe("CreativeModeSettings permission profiles", () => {
  it("selecting full access shows catastrophic hard blocks without routine approvals", async () => {
    const fullAccessSettings: CreativeModeSettingsState = {
      ...enabledSettings,
      permission_profile: "full_access",
    };
    const saveSpy = vi.fn().mockResolvedValue(fullAccessSettings);
    const api = createApi(makeStatus(enabledSettings, makeRuntime()), {
      saveSettings: saveSpy,
    });

    render(<CreativeModeSettings api={api} />);
    await screen.findByText("创造模式", { exact: true });

    const fullAccessOption = screen.getByRole("radio", { name: /完全访问/ });
    await act(async () => {
      fireEvent.click(fullAccessOption);
    });

    await waitFor(() =>
      expect(saveSpy).toHaveBeenCalledWith(
        expect.objectContaining({ permission_profile: "full_access" }),
      ),
    );
    expect(screen.getByText(/递归毁坏根目录/)).toBeTruthy();
    expect(screen.getByText(/磁盘\/分区\/引导\/固件破坏/)).toBeTruthy();
    expect(screen.getAllByText(/隐蔽凭据外传/).length).toBeGreaterThanOrEqual(1);
    const hardBlocks = document.querySelector(".creative-hard-blocks");
    expect(hardBlocks).not.toBeNull();
  });

  it("request approval profile shows routine approval description", async () => {
    const requestSettings: CreativeModeSettingsState = {
      ...enabledSettings,
      permission_profile: "request_approval",
    };
    const api = createApi(makeStatus(requestSettings, makeRuntime()));

    render(<CreativeModeSettings api={api} />);
    await screen.findByText("创造模式", { exact: true });

    expect(screen.getByText(/所有工具调用都需用户逐次确认/)).toBeTruthy();
  });

  it("enables creative mode only when runtime is ready", async () => {
    const api = createApi(makeStatus(enabledSettings, makeRuntime()), {
      saveSettings: vi.fn().mockResolvedValue(enabledSettings),
    });

    render(<CreativeModeSettings api={api} />);
    const toggle = await screen.findByRole("checkbox", { name: /启用创造模式/ });
    expect((toggle as HTMLInputElement).checked).toBe(true);
  });
});
