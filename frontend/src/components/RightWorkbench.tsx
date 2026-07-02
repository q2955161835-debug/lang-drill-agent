import { useRef, useState, type ChangeEvent, type DragEvent, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import {
  CaretLeft,
  CaretRight,
  ChatsCircle,
  DeviceMobile,
  FileText,
  FolderOpen,
  GitBranch,
  ImageSquare,
  MicrophoneStage,
  Plus,
  X,
} from "@phosphor-icons/react";
import type { DailyPanel, Message, ScreenshotImportResult, ScreenshotWord } from "../types";
import { apiGet, apiPost } from "../api";
import { appendImportedText, extractTextFromFiles } from "../fileImport";
import { MarkdownText } from "./MarkdownText";

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
  onResizeStart?: (event: ReactPointerEvent<HTMLButtonElement>) => void;
  onResizeKeyDown?: (event: KeyboardEvent<HTMLButtonElement>) => void;
  branchSourceAvailable: boolean;
  branchCreateLabel: string;
  onCreateBranch: () => void;
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

type EditableScreenshotWord = ScreenshotWord & { id: string };

function queuedFileSourceLabel(files: File[]) {
  return files.map((file) => file.name).join("、");
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function isCompleteScreenshotWord(word: ScreenshotWord) {
  return Boolean(word.term.trim() && word.meaning.trim());
}

function serializeEditableWords(words: ScreenshotWord[]) {
  return words
    .filter(isCompleteScreenshotWord)
    .map((word) => `${word.term.trim()}: ${word.meaning.trim()}`)
    .join("\n");
}

export function RightWorkbench({
  open,
  branchId,
  branchMessages,
  branchSending,
  sessionId,
  onToggle,
  activeTab,
  onTabChange,
  onResizeStart,
  onResizeKeyDown,
  branchSourceAvailable,
  branchCreateLabel,
  onCreateBranch,
  onSendBranchMessage,
  onDailyPanelChange,
  onScreenshotImportComplete,
}: RightWorkbenchProps) {
  return (
    <aside className={`right-rail panel-motion ${open ? "open" : "closed"}`}>
      {open && (
        <button
          type="button"
          className="panel-resizer panel-resizer-right"
          aria-label="拖拽调整右侧工作台宽度"
          title="拖拽调整右侧工作台宽度"
          onPointerDown={onResizeStart}
          onKeyDown={onResizeKeyDown}
        />
      )}
      <button
        className="right-toggle"
        onClick={onToggle}
        title={open ? "收起右侧工作台" : "展开右侧工作台"}
        aria-label={open ? "收起右侧工作台" : "展开右侧工作台"}
      >
        {open ? <CaretRight size={18} /> : <CaretLeft size={18} />}
      </button>
      <div className="workbench-panel" hidden={!open} aria-hidden={!open}>
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

        <div className="workbench-tab-panel" hidden={activeTab !== "branch"}>
          <BranchPanel
            branchId={branchId}
            branchMessages={branchMessages}
            branchSending={branchSending}
            branchSourceAvailable={branchSourceAvailable}
            branchCreateLabel={branchCreateLabel}
            onCreateBranch={onCreateBranch}
            onSendBranchMessage={onSendBranchMessage}
          />
        </div>
        <div className="workbench-tab-panel" hidden={activeTab !== "mirror"}>
          <PhoneMirrorPanel />
        </div>
        <div className="workbench-tab-panel" hidden={activeTab !== "screenshot"}>
          <ScreenshotImportPanel
            sessionId={sessionId}
            onDailyPanelChange={onDailyPanelChange}
            onScreenshotImportComplete={onScreenshotImportComplete}
          />
        </div>
        <div className="workbench-tab-panel" hidden={activeTab !== "voice"}>
          <ComingPanel title="语音与听力" body="本阶段只预留入口，后续可接入 Whisper 或 Web Speech API。" />
        </div>
      </div>
    </aside>
  );
}

function BranchPanel({
  branchId,
  branchMessages,
  branchSending,
  branchSourceAvailable,
  branchCreateLabel,
  onCreateBranch,
  onSendBranchMessage
}: {
  branchId: string | null;
  branchMessages: Message[];
  branchSending: boolean;
  branchSourceAvailable: boolean;
  branchCreateLabel: string;
  onCreateBranch: () => void;
  onSendBranchMessage: (content: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const canSend = Boolean(branchId && draft.trim() && !branchSending);
  const canCreateBranch = Boolean(!branchId && branchSourceAvailable && !branchSending);

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
      {!branchId && (
        <div className="workbench-actions">
          <button type="button" className="workbench-primary" onClick={onCreateBranch} disabled={!canCreateBranch}>
            {branchSending ? "创建中..." : branchCreateLabel}
          </button>
        </div>
      )}
      <div className="branch-thread" aria-live="polite">
        {branchMessages.length === 0 ? (
          <p className="empty-copy">这里会显示分支对话记录。</p>
        ) : (
          branchMessages.map((message) => (
            <div className={`branch-message ${message.role}`} key={message.id}>
              <MarkdownText content={message.content} />
            </div>
          ))
        )}
        {branchSending && (
          <div className="branch-message assistant branch-thinking" aria-label="分支正在思考">
            <span>分支正在思考</span>
            <span className="thinking-dots" aria-hidden="true"><i /> <i /> <i /></span>
          </div>
        )}
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
  const [status, setStatus] = useState("粘贴 OCR（文字识别）文本，或先拖入多张文件后点击解析文本。导入后会自动开始考试式练习。");
  const [loading, setLoading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [queuedFiles, setQueuedFiles] = useState<File[]>([]);
  const [editableWords, setEditableWords] = useState<EditableScreenshotWord[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const wordIdRef = useRef(0);
  const canParse = Boolean(text.trim() || queuedFiles.length) && !loading;
  const confirmedWordCount = editableWords.filter(isCompleteScreenshotWord).length;
  const canImport = Boolean((text.trim() || confirmedWordCount) && !queuedFiles.length) && !loading;
  const nextEditableWordId = () => {
    wordIdRef.current += 1;
    return `screenshot-word-${wordIdRef.current}`;
  };
  const toEditableWords = (words: ScreenshotWord[] | undefined) =>
    (words || []).map((word) => ({
      id: nextEditableWordId(),
      term: word.term,
      meaning: word.meaning,
    }));
  const updateEditableWord = (id: string, field: keyof ScreenshotWord, value: string) => {
    setEditableWords((current) => current.map((word) => word.id === id ? { ...word, [field]: value } : word));
  };
  const removeEditableWord = (id: string) => {
    setEditableWords((current) => current.filter((word) => word.id !== id));
  };
  const addEditableWord = () => {
    setEditableWords((current) => [...current, { id: nextEditableWordId(), term: "", meaning: "" }]);
  };
  const parse = async (startDrill: boolean) => {
    if (loading) return;
    if (!text.trim() && !queuedFiles.length) {
      setStatus("请先拖入文件或粘贴 OCR（文字识别）文本。");
      return;
    }
    setLoading(true);
    const shouldImportEditedWords = startDrill && Boolean(parsed?.words?.length) && editableWords.length > 0 && queuedFiles.length === 0;
    if (!startDrill) {
      setParsed(null);
      setEditableWords([]);
    }
    let generationTimer: number | undefined;
    let resolvedText = text;
    let sourceImagePath = imagePath;
    let extractedNames = "";
    try {
      if (queuedFiles.length) {
        setStatus(`正在读取 ${queuedFiles.length} 个已导入文件...`);
        const extracted = await extractTextFromFiles(queuedFiles);
        if (!extracted.text.trim()) {
          throw new Error("没有从已导入文件中读取到可解析文本。");
        }
        resolvedText = appendImportedText(text, extracted.text);
        extractedNames = extracted.results.map((result) => result.filename).join("、");
        sourceImagePath = imagePath.trim() || extractedNames;
        setText(resolvedText);
        setImagePath(sourceImagePath);
        setQueuedFiles([]);
      }
      if (shouldImportEditedWords) {
        const confirmedText = serializeEditableWords(editableWords);
        if (!confirmedText) {
          throw new Error("请至少保留一个同时包含单词和释义的词条。");
        }
        resolvedText = confirmedText;
      }
      if (!resolvedText.trim()) {
        throw new Error("请先填写或解析出截图识别文本。");
      }
      setStatus(startDrill ? "截图解析中，随后会生成题目..." : "截图解析中...");
      if (startDrill) {
        generationTimer = window.setTimeout(() => setStatus("题目生成中，请稍等..."), 800);
      }
      const data = await apiPost<ScreenshotImportResult>("/api/screenshot/parse", {
        text: resolvedText,
        session_id: sessionId,
        import_to_session: startDrill,
        auto_start_drill: startDrill,
        force_new_session: startDrill,
        source_image_path: sourceImagePath,
      });
      setParsed(data);
      setEditableWords(toEditableWords(data.words));
      if (data.daily_panel) onDailyPanelChange(data.daily_panel);
      if (startDrill) {
        onScreenshotImportComplete(data);
        setStatus(data.auto_started ? `已导入 ${data.imported_count || 0} 个单词，并自动生成考试式题组。` : `已导入 ${data.imported_count || 0} 个单词，但题组生成失败。`);
      } else {
        const prefix = extractedNames ? `已读取 ${extractedNames}，` : "";
        setStatus(`${prefix}已解析 ${data.words?.length || 0} 个单词。`);
      }
    } catch (err) {
      setStatus(`截图处理失败：${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      if (generationTimer !== undefined) window.clearTimeout(generationTimer);
      setLoading(false);
    }
  };
  const handleDropFiles = (files: File[]) => {
    setDragActive(false);
    if (!files.length) return;
    if (loading) {
      setStatus("正在处理当前文件，请稍后再拖入。");
      return;
    }
    const currentSource = queuedFileSourceLabel(queuedFiles);
    const nextFiles = [...queuedFiles, ...files];
    const nextSource = queuedFileSourceLabel(nextFiles);
    setQueuedFiles(nextFiles);
    setParsed(null);
    setEditableWords([]);
    setImagePath((current) => {
      const trimmed = current.trim();
      return !trimmed || trimmed === currentSource ? nextSource : current;
    });
    setStatus(`已导入 ${files.length} 个文件，待解析共 ${nextFiles.length} 个。可继续拖入追加，点击“解析文本”开始识别。`);
  };
  const handleFileInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    handleDropFiles(Array.from(event.target.files || []));
    event.target.value = "";
  };
  const removeQueuedFile = (index: number) => {
    if (loading) return;
    const currentSource = queuedFileSourceLabel(queuedFiles);
    const nextFiles = queuedFiles.filter((_, fileIndex) => fileIndex !== index);
    const nextSource = queuedFileSourceLabel(nextFiles);
    setQueuedFiles(nextFiles);
    setParsed(null);
    setEditableWords([]);
    setImagePath((current) => current.trim() === currentSource ? nextSource : current);
    setStatus(nextFiles.length ? `待解析文件还剩 ${nextFiles.length} 个。` : "已清空待解析文件，可重新拖入或粘贴文本。");
  };
  const clearQueuedFiles = () => {
    if (loading) return;
    const currentSource = queuedFileSourceLabel(queuedFiles);
    setQueuedFiles([]);
    setParsed(null);
    setEditableWords([]);
    setImagePath((current) => current.trim() === currentSource ? "" : current);
    setStatus("已清空待解析文件，可重新拖入或粘贴文本。");
  };
  return (
    <section className="coming-panel workbench-form">
      <span className="eyebrow">Screenshot（截图）</span>
      <h3>截图导入</h3>
      <p>截图导入会把识别出的词表写入学习库，并立即创建一组考试式语境题。</p>
      <div
        className={`drop-zone screenshot-drop ${dragActive ? "drag-over" : ""}`}
        onDragEnter={(event) => {
          if (event.dataTransfer.types.includes("Files")) setDragActive(true);
        }}
        onDragOver={(event) => {
          if (event.dataTransfer.types.includes("Files")) event.preventDefault();
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            setDragActive(false);
          }
        }}
        onDrop={(event: DragEvent<HTMLDivElement>) => {
          event.preventDefault();
          void handleDropFiles(Array.from(event.dataTransfer.files || []));
        }}
      >
        <div className="drop-zone-main">
          <span className="drop-zone-icon" aria-hidden="true">
            <ImageSquare size={20} />
          </span>
          <span className="drop-zone-copy">
            <strong>拖入截图或文件</strong>
            <span>图片、文本、PDF、DOCX，先入队</span>
          </span>
        </div>
        <input
          ref={fileInputRef}
          className="hidden-file-input"
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.jp2,.webp,.gif,.bmp,.txt,.md,.markdown,.pdf,.doc,.docx,image/*"
          onChange={handleFileInputChange}
        />
        <button type="button" className="drop-zone-action" onClick={() => fileInputRef.current?.click()} disabled={loading}>
          <FolderOpen size={16} /> 选择文件
        </button>
      </div>
      {queuedFiles.length > 0 && (
        <div className="queued-file-list" aria-label="待解析文件列表">
          <div className="queued-file-list-head">
            <strong>待解析文件 <span>{queuedFiles.length}</span></strong>
            <button type="button" onClick={clearQueuedFiles} disabled={loading}>清空</button>
          </div>
          {queuedFiles.map((file, index) => (
            <div className="queued-file-row" key={`${file.name}-${file.size}-${file.lastModified}-${index}`}>
              <FileText size={16} aria-hidden="true" />
              <span title={file.name}>{file.name}</span>
              <small>{formatFileSize(file.size)}</small>
              <button
                type="button"
                className="queued-file-remove"
                onClick={() => removeQueuedFile(index)}
                disabled={loading}
                aria-label={`移除 ${file.name}`}
                title={`移除 ${file.name}`}
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      <label>源图片路径 / 文件名<input value={imagePath} onChange={(event) => setImagePath(event.target.value)} placeholder="可选，例如 D:/.../word-list.png" /></label>
      <label>截图识别文本<textarea value={text} onChange={(event) => {
        setText(event.target.value);
        setParsed(null);
        setEditableWords([]);
      }} placeholder={"粘贴单词列表或题目文本，例如：collision\nn. 碰撞；冲突"} /></label>
      <div className="workbench-actions">
        <button className="workbench-primary" onClick={() => void parse(false)} disabled={!canParse}>{loading ? "解析中..." : "解析文本"}</button>
        <button onClick={() => void parse(true)} disabled={!canImport}>{loading ? "处理中..." : "导入并开始练习"}</button>
      </div>
      <p className="status-line">{status}</p>
      {parsed && (
        <div className="screenshot-review">
          <div className="screenshot-review-head">
            <div>
              <p>识别类型：{parsed.confidence}</p>
              <strong>{parsed.prompt}</strong>
            </div>
            {editableWords.length > 0 && <span>{confirmedWordCount}/{editableWords.length} 可导入</span>}
          </div>
          {editableWords.length > 0 && (
            <div className="screenshot-word-list" aria-label="可编辑词条">
              {editableWords.map((word, index) => (
                <div className="screenshot-word-card" key={word.id}>
                  <div className="screenshot-word-index">{index + 1}</div>
                  <label>单词<input value={word.term} onChange={(event) => updateEditableWord(word.id, "term", event.target.value)} /></label>
                  <label>释义<textarea value={word.meaning} onChange={(event) => updateEditableWord(word.id, "meaning", event.target.value)} /></label>
                  <button
                    type="button"
                    className="icon-button screenshot-word-remove"
                    onClick={() => removeEditableWord(word.id)}
                    aria-label={`删除词条 ${word.term || index + 1}`}
                    title={`删除词条 ${word.term || index + 1}`}
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
              <button type="button" className="screenshot-add-word" onClick={addEditableWord}>
                <Plus size={14} /> 添加词条
              </button>
            </div>
          )}
          {parsed.options.map((option, index) => <span key={option}>{String.fromCharCode(65 + index)}. {option}</span>)}
          {parsed.diagnostics && (parsed.diagnostics.skipped_count > 0 || parsed.diagnostics.repaired_count > 0) && (
            <p className="screenshot-diagnostics">
              已跳过 {parsed.diagnostics.skipped_count} 行，修复 {parsed.diagnostics.repaired_count} 个疑似截断词。
            </p>
          )}
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
