import { useEffect, useRef, useState } from "react";
import {
  CaretLeft,
  CaretRight,
  ChatsCircle,
  DeviceMobile,
  GitBranch,
  ImageSquare,
  MicrophoneStage,
} from "@phosphor-icons/react";
import type { DailyPanel, Message, ScreenshotImportResult } from "../types";
import { apiGet, apiPost } from "../api";

export type WorkbenchTab = "branch" | "mirror" | "screenshot" | "voice";

type RightWorkbenchProps = {
  open: boolean;
  branchId: string | null;
  branchMessages: Message[];
  branchSending: boolean;
  sessionId: string | null;
  onToggle: () => void;
  activeTab: WorkbenchTab;
  onTabChange: (tab: WorkbenchTab) => void;
  onSendBranchMessage: (content: string) => void;
  onDailyPanelChange: (panel: DailyPanel) => void;
  onScreenshotImportComplete: (result: ScreenshotImportResult) => void;
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

export function RightWorkbench({
  open,
  branchId,
  branchMessages,
  branchSending,
  sessionId,
  onToggle,
  activeTab,
  onTabChange,
  onSendBranchMessage,
  onDailyPanelChange,
  onScreenshotImportComplete,
}: RightWorkbenchProps) {
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
                  onClick={() => onTabChange(tab.id)}
                  role="tab"
                  aria-selected={activeTab === tab.id}
                >
                  <Icon size={15} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {activeTab === "branch" && (
            <BranchPanel
              branchId={branchId}
              branchMessages={branchMessages}
              branchSending={branchSending}
              onSendBranchMessage={onSendBranchMessage}
            />
          )}
          {activeTab === "mirror" && <PhoneMirrorPanel />}
          {activeTab === "screenshot" && (
            <ScreenshotImportPanel
              sessionId={sessionId}
              onDailyPanelChange={onDailyPanelChange}
              onScreenshotImportComplete={onScreenshotImportComplete}
            />
          )}
          {activeTab === "voice" && <ComingPanel title="语音与听力" body="本阶段只预留入口，后续可接入 Whisper 或 Web Speech API。" />}
        </div>
      )}
    </aside>
  );
}

function BranchPanel({
  branchId,
  branchMessages,
  branchSending,
  onSendBranchMessage
}: {
  branchId: string | null;
  branchMessages: Message[];
  branchSending: boolean;
  onSendBranchMessage: (content: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const branchEndRef = useRef<HTMLDivElement | null>(null);
  const canSend = Boolean(branchId && draft.trim() && !branchSending);

  useEffect(() => {
    branchEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [branchMessages, branchSending]);

  const sendDraft = () => {
    if (!canSend) return;
    onSendBranchMessage(draft);
    setDraft("");
  };

  return (
    <section className="branch-panel workbench-form">
      <div className="panel-title">
        <GitBranch size={18} />
        <span>分支对话</span>
      </div>
      <p className="hint">{branchId ? `当前分支：${branchId}` : "选中主聊天文本后，可以在这里展开解释，不污染主线学习记录。"}</p>
      <div className="branch-thread" aria-live="polite">
        {branchMessages.length === 0 ? (
          <p className="empty-copy">这里会显示分支对话记录。</p>
        ) : (
          branchMessages.map((message) => (
            <div className={`branch-message ${message.role}`} key={message.id}>
              {message.content}
            </div>
          ))
        )}
        {branchSending && (
          <div className="branch-message assistant branch-thinking" aria-label="分支正在思考">
            <span>分支正在思考</span>
            <span className="thinking-dots" aria-hidden="true"><i /> <i /> <i /></span>
          </div>
        )}
        <div ref={branchEndRef} />
      </div>
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendDraft();
          }
        }}
        placeholder="继续追问，或者让分支整理成复习卡片。"
        disabled={branchSending}
      />
      <div className="workbench-actions">
        <button className="workbench-primary" onClick={sendDraft} disabled={!canSend}>{branchSending ? "发送中..." : "发送分支消息"}</button>
      </div>
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

function ScreenshotImportPanel({
  sessionId,
  onDailyPanelChange,
  onScreenshotImportComplete,
}: {
  sessionId: string | null;
  onDailyPanelChange: (panel: DailyPanel) => void;
  onScreenshotImportComplete: (result: ScreenshotImportResult) => void;
}) {
  const [text, setText] = useState("");
  const [imagePath, setImagePath] = useState("");
  const [parsed, setParsed] = useState<ScreenshotImportResult | null>(null);
  const [status, setStatus] = useState("粘贴 OCR（文字识别）文本后可解析；导入后会自动开始考试式练习。");
  const [loading, setLoading] = useState(false);
  const parse = async (startDrill: boolean) => {
    if (loading) return;
    setLoading(true);
    setStatus(startDrill ? "截图解析中，随后会生成题目..." : "截图解析中...");
    const generationTimer = startDrill
      ? window.setTimeout(() => setStatus("题目生成中，请稍等..."), 800)
      : undefined;
    try {
      const data = await apiPost<ScreenshotImportResult>("/api/screenshot/parse", {
        text,
        session_id: sessionId,
        import_to_session: startDrill,
        auto_start_drill: startDrill,
        force_new_session: startDrill,
        source_image_path: imagePath,
      });
      setParsed(data);
      if (data.daily_panel) onDailyPanelChange(data.daily_panel);
      if (startDrill) {
        onScreenshotImportComplete(data);
        setStatus(data.auto_started ? `已导入 ${data.imported_count || 0} 个单词，并自动生成考试式题组。` : `已导入 ${data.imported_count || 0} 个单词，但题组生成失败。`);
      } else {
        setStatus(`已解析 ${data.words?.length || 0} 个单词。`);
      }
    } catch (err) {
      setStatus(`截图处理失败：${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      if (generationTimer !== undefined) window.clearTimeout(generationTimer);
      setLoading(false);
    }
  };
  return (
    <section className="coming-panel workbench-form">
      <span className="eyebrow">Screenshot（截图）</span>
      <h3>截图导入</h3>
      <p>截图导入会把识别出的词表写入学习库，并立即创建一组考试式语境题。</p>
      <label>源图片路径<input value={imagePath} onChange={(event) => setImagePath(event.target.value)} placeholder="可选，例如 D:/.../word-list.png" /></label>
      <label>截图识别文本<textarea value={text} onChange={(event) => setText(event.target.value)} placeholder={"粘贴单词列表或题目文本，例如：collision\nn. 碰撞；冲突"} /></label>
      <div className="workbench-actions">
        <button className="workbench-primary" onClick={() => void parse(false)} disabled={!text.trim() || loading}>解析文本</button>
        <button onClick={() => void parse(true)} disabled={!text.trim() || loading}>{loading ? "处理中..." : "导入并开始练习"}</button>
      </div>
      <p className="status-line">{status}</p>
      {parsed && (
        <div className="preview-card">
          <p>识别类型：{parsed.confidence}</p>
          <strong>{parsed.prompt}</strong>
          {parsed.words?.slice(0, 10).map((word) => <span key={word.term}>{word.term}：{word.meaning}</span>)}
          {parsed.options.map((option, index) => <span key={option}>{String.fromCharCode(65 + index)}. {option}</span>)}
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
