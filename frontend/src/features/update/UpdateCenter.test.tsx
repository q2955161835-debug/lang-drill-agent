// 更新中心状态机测试。
// 验证 idle/checking/available/downloading/ready_to_restart/up_to_date/failed 状态流转，
// 以及 Web 模式下返回 desktop-only 状态而非调用不可用的 Tauri API。
// @vitest-environment jsdom

import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import {
  createUpdaterMachine,
  DesktopOnlyUpdateAdapter,
  type UpdateAdapter,
  type UpdateInfo,
} from "./updater";

function makeInfo(overrides: Partial<UpdateInfo> = {}): UpdateInfo {
  return {
    version: "1.0.0-alpha.2",
    currentVersion: "0.1.2",
    releaseNotes: "",
    downloadSize: 0,
    isPrerelease: true,
    ...overrides,
  };
}

describe("update state machine", () => {
  it("starts in idle state", () => {
    const adapter: UpdateAdapter = {
      isDesktopSupported: () => true,
      check: vi.fn(),
      downloadAndInstall: vi.fn(),
      restart: vi.fn(),
    };
    const { result } = renderHook(() => createUpdaterMachine(adapter));
    expect(result.current.state).toBe("idle");
  });

  it("transitions to checking then up_to_date when no update available", async () => {
    const adapter: UpdateAdapter = {
      isDesktopSupported: () => true,
      check: vi.fn().mockResolvedValue({ available: false }),
      downloadAndInstall: vi.fn(),
      restart: vi.fn(),
    };
    const { result } = renderHook(() => createUpdaterMachine(adapter));
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.state).toBe("up_to_date");
  });

  it("transitions to available when a prerelease update exists", async () => {
    const info = makeInfo();
    const adapter: UpdateAdapter = {
      isDesktopSupported: () => true,
      check: vi.fn().mockResolvedValue({ available: true, info }),
      downloadAndInstall: vi.fn(),
      restart: vi.fn(),
    };
    const { result } = renderHook(() => createUpdaterMachine(adapter));
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.state).toBe("available");
    expect(result.current.info).toEqual(info);
  });

  it("transitions to failed on signature error", async () => {
    const adapter: UpdateAdapter = {
      isDesktopSupported: () => true,
      check: vi.fn().mockRejectedValue(new Error("signature verification failed")),
      downloadAndInstall: vi.fn(),
      restart: vi.fn(),
    };
    const { result } = renderHook(() => createUpdaterMachine(adapter));
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.state).toBe("failed");
    expect(result.current.error).toContain("signature");
  });

  it("transitions through downloading to ready_to_restart on install", async () => {
    const adapter: UpdateAdapter = {
      isDesktopSupported: () => true,
      check: vi.fn().mockResolvedValue({ available: true, info: makeInfo() }),
      downloadAndInstall: vi.fn().mockResolvedValue(undefined),
      restart: vi.fn(),
    };
    const { result } = renderHook(() => createUpdaterMachine(adapter));
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.state).toBe("available");
    await act(async () => {
      await result.current.downloadAndInstall();
    });
    expect(result.current.state).toBe("ready_to_restart");
    expect(adapter.downloadAndInstall).toHaveBeenCalled();
  });

  it("transitions to failed on install error", async () => {
    const adapter: UpdateAdapter = {
      isDesktopSupported: () => true,
      check: vi.fn().mockResolvedValue({ available: true, info: makeInfo() }),
      downloadAndInstall: vi.fn().mockRejectedValue(new Error("install failed")),
      restart: vi.fn(),
    };
    const { result } = renderHook(() => createUpdaterMachine(adapter));
    await act(async () => {
      await result.current.check();
    });
    await act(async () => {
      await result.current.downloadAndInstall();
    });
    expect(result.current.state).toBe("failed");
  });

  it("calls restart when user confirms restart", async () => {
    const adapter: UpdateAdapter = {
      isDesktopSupported: () => true,
      check: vi.fn().mockResolvedValue({ available: true, info: makeInfo() }),
      downloadAndInstall: vi.fn().mockResolvedValue(undefined),
      restart: vi.fn().mockResolvedValue(undefined),
    };
    const { result } = renderHook(() => createUpdaterMachine(adapter));
    await act(async () => {
      await result.current.check();
    });
    await act(async () => {
      await result.current.downloadAndInstall();
    });
    await act(async () => {
      await result.current.restart();
    });
    expect(adapter.restart).toHaveBeenCalled();
  });

  it("returns desktop-only state in Web mode without calling Tauri APIs", async () => {
    const adapter = new DesktopOnlyUpdateAdapter();
    expect(adapter.isDesktopSupported()).toBe(false);
    const { result } = renderHook(() => createUpdaterMachine(adapter));
    await act(async () => {
      await result.current.check();
    });
    expect(result.current.state).toBe("desktop_only");
  });
});
