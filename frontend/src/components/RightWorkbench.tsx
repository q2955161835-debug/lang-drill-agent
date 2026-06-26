import { useState } from "react";
import {
  Books,
  CaretLeft,
  CaretRight,
  ChatsCircle,
  GitBranch,
  ImageSquare,
  MicrophoneStage,
  PuzzlePiece
} from "@phosphor-icons/react";
import type { Message } from "../types";
import { apiGet, apiPost } from "../api";

type WorkbenchTab = "branch" | "composer" | "vocab" | "screenshot" | "voice";

type RightWorkbenchProps = {
  open: boolean;
  branchMessages: Message[];
  onToggle: () => void;
  onSendToChat: (content: string) => void;
};

const tabs: Array<{ id: WorkbenchTab; label: string; icon: typeof GitBranch; disabled?: boolean }> = [
  { id: "branch", label: "分支", icon: GitBranch },
  { id: "composer", label: "组词器", icon: PuzzlePiece },
  { id: "vocab", label: "背词同步", icon: Books },
  { id: "screenshot", label: "截图导入", icon: ImageSquare },
  { id: "voice", label: "语音预留", icon: MicrophoneStage, disabled: true }
];

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
          {activeTab === "composer" && <ComposerPanel onSendToChat={onSendToChat} />}
          {activeTab === "vocab" && <VocabSyncPanel />}
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

function ComposerPanel({ onSendToChat }: { onSendToChat: (content: string) => void }) {
  const [goal, setGoal] = useState("CET-4 vocabulary and grammar practice");
  const [selected, setSelected] = useState<string[]>(["A", "B"]);
  const [extra, setExtra] = useState("");
  const [result, setResult] = useState<{ composed_prompt: string; assistant_message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const optionLabels = [
    ["A", "词汇辨析"],
    ["B", "语法纠错"],
    ["C", "阅读理解"],
    ["D", "翻译写作"]
  ];
  const toggle = (key: string) => {
    setSelected((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]);
  };
  const compose = async () => {
    setBusy(true);
    try {
      const data = await apiPost<{ composed_prompt: string; assistant_message: string }>("/api/composer/next", {
        goal,
        selected_options: selected,
        extra_content: extra
      });
      setResult(data);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="coming-panel workbench-form">
      <span className="eyebrow">Composer</span>
      <h3>对话式组词器</h3>
      <label>学习目标<input value={goal} onChange={(event) => setGoal(event.target.value)} /></label>
      <div className="option-pills">
        {optionLabels.map(([key, label]) => (
          <button key={key} className={selected.includes(key) ? "active" : ""} onClick={() => toggle(key)}>{key}. {label}</button>
        ))}
      </div>
      <label>额外内容<textarea value={extra} onChange={(event) => setExtra(event.target.value)} placeholder="例如：题目稍难一点，解释要包含中文对照。" /></label>
      <button className="workbench-primary" onClick={() => void compose()} disabled={busy}>{busy ? "组入中..." : "组入下一轮提示词"}</button>
      {result && (
        <div className="preview-card">
          <p>{result.assistant_message}</p>
          <pre>{result.composed_prompt}</pre>
          <button className="workbench-primary" onClick={() => onSendToChat(result.composed_prompt)}>发送到主聊天</button>
        </div>
      )}
    </section>
  );
}

function VocabSyncPanel() {
  const [deck, setDeck] = useState("LangDrill::CET4");
  const [status, setStatus] = useState("尚未检查 AnkiConnect。");
  const check = async () => {
    const data = await apiGet<{ connected: boolean; decks: string[]; error?: string }>("/api/anki/status");
    setStatus(data.connected ? `已连接。检测到 ${data.decks.length} 个牌组。` : data.error || "未连接");
  };
  const exportDeck = async () => {
    const data = await apiPost<{ ok: boolean; created?: number; total_candidates: number; error?: string }>("/api/anki/export", { deck_name: deck });
    setStatus(data.ok ? `已导出 ${data.created || 0}/${data.total_candidates} 个词条到 ${deck}。` : data.error || "导出失败");
  };
  return (
    <section className="coming-panel workbench-form">
      <span className="eyebrow">Anki Sync</span>
      <h3>手机背词同步</h3>
      <p>打开 Anki + AnkiConnect 后，可导出本地词表到 Anki，再通过 AnkiWeb 同步到手机端。</p>
      <label>目标牌组<input value={deck} onChange={(event) => setDeck(event.target.value)} /></label>
      <div className="workbench-actions">
        <button onClick={() => void check()}>检查连接</button>
        <button className="workbench-primary" onClick={() => void exportDeck()}>导出词表</button>
      </div>
      <p className="status-line">{status}</p>
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
      <span className="eyebrow">Screenshot</span>
      <h3>截图导入</h3>
      <p>当前版本支持粘贴 OCR 文本；桌面版会接入截图/图片选择和本地 OCR。</p>
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
