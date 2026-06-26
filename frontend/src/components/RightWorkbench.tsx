import { useState } from "react";
import {
  CaretLeft,
  CaretRight,
  ChatsCircle,
  DeviceMobile,
  GitBranch,
  ImageSquare,
  MicrophoneStage,
} from "@phosphor-icons/react";
import type { Message } from "../types";
import { apiGet, apiPost } from "../api";

type WorkbenchTab = "branch" | "mirror" | "screenshot" | "voice";

type RightWorkbenchProps = {
  open: boolean;
  branchMessages: Message[];
  onToggle: () => void;
  onSendToChat: (content: string) => void;
};

const tabs: Array<{ id: WorkbenchTab; label: string; icon: typeof GitBranch; disabled?: boolean }> = [
  { id: "branch", label: "分支", icon: GitBranch },
  { id: "mirror", label: "手机映像", icon: DeviceMobile },
  { id: "screenshot", label: "截图导入", icon: ImageSquare },
  { id: "voice", label: "语音预留", icon: MicrophoneStage, disabled: true }
];

type PhoneMirrorStatus = {
  adb_available: boolean;
  scrcpy_available: boolean;
  adb_path: string;
  scrcpy_path: string;
  devices: Array<{ id: string; status: string }>;
  error?: string;
  recommended_project?: { name: string; url: string; reason: string };
};

export function RightWorkbench({ open, branchMessages, onToggle, onSendToChat }: RightWorkbenchProps) {
  const [activeTab, setActiveTab] = useState<WorkbenchTab>("branch");

  return (
    <aside className={`right-rail panel-motion ${open ? "open" : "closed"}`}>
      <button className="right-toggle" onClick={onToggle} title="展开右侧工作台">
        {open ? <CaretRight size={18} /> : <CaretLeft size={18} />}
      </button>
      {open && (
        <div className="workbench-panel">
          <div className="workbench-head">
            <div>
              <span className="eyebrow">Workspace</span>
              <h2>学习工作台</h2>
            </div>
            <ChatsCircle size={22} />
          </div>
          <div className="workbench-tabs" role="tablist" aria-label="右侧工作台">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  className={activeTab === tab.id ? "active" : ""}
                  disabled={tab.disabled}
                  onClick={() => setActiveTab(tab.id)}
                  role="tab"
                  aria-selected={activeTab === tab.id}
                >
                  <Icon size={15} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {activeTab === "branch" && <BranchPanel branchMessages={branchMessages} />}
          {activeTab === "mirror" && <PhoneMirrorPanel />}
          {activeTab === "screenshot" && <ScreenshotImportPanel onSendToChat={onSendToChat} />}
          {activeTab === "voice" && <ComingPanel title="语音与听力" body="本阶段只预留入口，后续可接入 Whisper 或 Web Speech API。" />}
        </div>
      )}
    </aside>
  );
}

function BranchPanel({ branchMessages }: { branchMessages: Message[] }) {
  return (
    <section className="branch-panel">
      <div className="panel-title">
        <GitBranch size={18} />
        <span>分支对话</span>
      </div>
      {branchMessages.length === 0 ? (
        <p className="empty-copy">选中主聊天里的文本后，可以在这里展开解释，不污染主线学习记录。</p>
      ) : (
        branchMessages.map((message) => (
          <div className={`branch-message ${message.role}`} key={message.id}>
            {message.content}
          </div>
        ))
      )}
    </section>
  );
}

function PhoneMirrorPanel() {
  const [status, setStatus] = useState<PhoneMirrorStatus | null>(null);
  const [selectedDevice, setSelectedDevice] = useState("");
  const [message, setMessage] = useState("尚未检查手机映像环境。");
  const check = async () => {
    const data = await apiGet<PhoneMirrorStatus>("/api/phone-mirror/status");
    setStatus(data);
    setSelectedDevice(data.devices[0]?.id || "");
    if (!data.adb_available || !data.scrcpy_available) {
      setMessage("需要安装 Android Platform Tools（安卓平台工具）和 scrcpy（手机映像工具）后才能启动。");
      return;
    }
    setMessage(data.devices.length ? `检测到 ${data.devices.length} 台设备。` : "已检测到工具，但尚未发现已授权手机。");
  };
  const start = async () => {
    const data = await apiPost<{ ok: boolean; command?: string; error?: string }>("/api/phone-mirror/start", { device_id: selectedDevice });
    setMessage(data.ok ? `已启动：${data.command}` : data.error || "启动失败");
  };
  return (
    <section className="coming-panel workbench-form">
      <span className="eyebrow">Phone Mirror（手机映像）</span>
      <h3>手机投屏与操控</h3>
      <p>这里按 scrcpy（开源手机映像工具）路线集成：电脑连接手机后，可投屏、鼠标操控，再把手机上的背词或题目画面带回学习流程。</p>
      {status && (
        <div className="preview-card">
          <span>adb（安卓调试桥）：{status.adb_available ? "已检测" : "未检测"}</span>
          <span>scrcpy（手机映像工具）：{status.scrcpy_available ? "已检测" : "未检测"}</span>
          <span>推荐项目：{status.recommended_project?.name}</span>
        </div>
      )}
      <label>设备<select value={selectedDevice} onChange={(event) => setSelectedDevice(event.target.value)}>
        <option value="">自动选择</option>
        {status?.devices.map((device) => <option key={device.id} value={device.id}>{device.id} - {device.status}</option>)}
      </select></label>
      <div className="workbench-actions">
        <button onClick={() => void check()}>检查环境</button>
        <button className="workbench-primary" onClick={() => void start()} disabled={!status?.scrcpy_available}>启动映像</button>
      </div>
      <p className="status-line">{message}</p>
    </section>
  );
}

function ScreenshotImportPanel({ onSendToChat }: { onSendToChat: (content: string) => void }) {
  const [text, setText] = useState("");
  const [parsed, setParsed] = useState<{ prompt: string; options: string[]; confidence: string; raw_text: string } | null>(null);
  const parse = async () => {
    const data = await apiPost<{ prompt: string; options: string[]; confidence: string; raw_text: string }>("/api/screenshot/parse", { text });
    setParsed(data);
  };
  const composed = parsed ? `请根据以下截图导入内容生成一道英语练习题：\n\n题干：${parsed.prompt}\n选项：${parsed.options.join(" / ")}\n\n请先确认题意，再给出适合 CET-4 的练习。` : "";
  return (
    <section className="coming-panel workbench-form">
      <span className="eyebrow">Screenshot（截图）</span>
      <h3>截图导入</h3>
      <p>截图导入会配合手机映像使用：先把手机画面投到电脑，再粘贴 OCR（文字识别）文本或后续接入本地截图识别。</p>
      <label>截图识别文本<textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="粘贴题目文本，例如：...\nA. ...\nB. ..." /></label>
      <button className="workbench-primary" onClick={() => void parse()} disabled={!text.trim()}>解析文本</button>
      {parsed && (
        <div className="preview-card">
          <p>识别类型：{parsed.confidence}</p>
          <strong>{parsed.prompt}</strong>
          {parsed.options.map((option, index) => <span key={option}>{String.fromCharCode(65 + index)}. {option}</span>)}
          <button className="workbench-primary" onClick={() => onSendToChat(composed)}>发送到主聊天</button>
        </div>
      )}
    </section>
  );
}

function ComingPanel({ title, body }: { title: string; body: string }) {
  return (
    <section className="coming-panel">
      <span className="eyebrow">Planned</span>
      <h3>{title}</h3>
      <p>{body}</p>
    </section>
  );
}
