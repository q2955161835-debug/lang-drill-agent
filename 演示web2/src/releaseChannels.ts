/**
 * 演示站下载渠道清单。
 *
 * 仅在 `演示web2` 内部使用：把稳定版 (v0.1.2) 与实验版 (v1.0.0-alpha.2) 两个
 * GitHub Release 安装包分别暴露给桌面版下载区。在线体验入口仍只指向实验版
 * (`#/app`)，本文件不修改 GitHub Release 元数据。
 */

export type DemoReleaseChannel = {
  id: "stable" | "experimental";
  label: "稳定版" | "实验版";
  version: string;
  description: string;
  downloadUrl: string;
};

export const releaseChannels = {
  stable: {
    id: "stable",
    label: "稳定版",
    version: "v0.1.2",
    description: "适合优先考虑稳定性的本地安装。",
    downloadUrl:
      "https://github.com/q2955161835-debug/lang-drill-agent/releases/download/v0.1.2/Lang.Drill.Agent_0.1.2_x64-setup.exe",
  },
  experimental: {
    id: "experimental",
    label: "实验版",
    version: "v1.0.0-alpha.2",
    description: "包含最新 Agent、记忆、知识库与创造模式能力。",
    downloadUrl:
      "https://github.com/q2955161835-debug/lang-drill-agent/releases/download/v1.0.0-alpha.2/Lang.Drill.Agent_1.0.0-alpha.2_x64-setup.exe",
  },
} satisfies Record<"stable" | "experimental", DemoReleaseChannel>;

export const onlineExperience = {
  channel: "experimental" as const,
  href: "#/app",
  label: "在线体验（实验版）",
};
