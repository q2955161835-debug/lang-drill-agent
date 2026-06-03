import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import {
  Brain,
  CaretDown,
  CaretLeft,
  CaretRight,
  ChatCircleText,
  CheckCircle,
  GearSix,
  GitBranch,
  ListBullets,
  Moon,
  PaperPlaneRight,
  ShieldCheck,
  Sidebar,
  Sparkle,
  Sun,
  Target,
  UserCircle,
  X
} from "@phosphor-icons/react";

gsap.registerPlugin(useGSAP);

function MessageItem({ message }: { message: Message }) {
  const container = useRef<HTMLElement>(null);
  
  useGSAP(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) return;
    
    // 卡通果冻弹跳效果
    gsap.from(container.current, {
      opacity: 0,
      y: 50,
      rotationZ: gsap.utils.random(-5, 5),
      scale: 0.8,
      duration: 0.8,
      ease: "elastic.out(1, 0.4)"
    });
  }, { scope: container, dependencies: [] });

  return (
    <article className={`message ${message.role}`} ref={container}>
      <div className="avatar">{message.role === "user" ? <UserCircle size={18} /> : <Sparkle size={18} />}</div>
      <div className="bubble">{message.content}</div>
    </article>
  );
}

function InteractiveButton({ 
  children, 
  className = "", 
  onClick, 
  title 
}: { 
  children: ReactNode; 
  className?: string; 
  onClick?: () => void; 
  title?: string;
}) {
  const btnRef = useRef<HTMLButtonElement>(null);
  const { contextSafe } = useGSAP({ scope: btnRef });
  
  const onEnter = contextSafe(() => gsap.to(btnRef.current, { scale: 1.1, rotationZ: 3, duration: 0.4, ease: "elastic.out(1.2, 0.4)" }));
  const onLeave = contextSafe(() => gsap.to(btnRef.current, { scale: 1, rotationZ: 0, duration: 0.3, ease: "power2.out" }));
  const onDown = contextSafe(() => gsap.to(btnRef.current, { scale: 0.9, duration: 0.1, ease: "power1.inOut" }));
  const onUp = contextSafe(() => gsap.to(btnRef.current, { scale: 1.15, rotationZ: -3, duration: 0.5, ease: "elastic.out(1.5, 0.3)" }));

  return (
    <button 
      ref={btnRef}
      className={className}
      onClick={onClick}
      title={title}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onMouseDown={onDown}
      onMouseUp={onUp}
    >
      {children}
    </button>
  );
}

const API = "";

type Profile = {
  display_name: string;
  target_language: string;
  exam_id: string;
  exam_name: string;
  learning_goal: string;
  learning_background: string;
  persona: string;
  global_user_prompt: string;
};

type ThemeMode = "system" | "light" | "dark";

type ProviderOption = {
  id: string;
  label: string;
  kind: string;
  base_url: string;
  model: string;
  model_options: string[];
};

type ModelConfig = {
  provider_id: string;
  base_url: string;
  model: string;
  api_key?: string;
  has_api_key?: boolean;
};

type SessionItem = {
  id: string;
  title: string;
  folder_date: string;
  status: string;
};

type DailyPanel = {
  date: string;
  title: string;
  status: string;
  plan: {
    new_content?: string[];
    review_content?: string[];
    target_minutes?: number;
    status?: string;
  };
  questions_total: number;
  questions_done: number;
  accuracy: number;
  summary: string;
};

type Question = {
  id: string;
  sequence: number;
  type: string;
  prompt: string;
  options: string[];
  answer?: { correct?: string; letter?: string };
  explanation?: string;
  knowledge_tags: string[];
  status: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

const DEFAULT_PANEL: DailyPanel = {
  date: new Date().toISOString().slice(0, 10),
  title: "长期学习记录",
  status: "idle",
  plan: {
    new_content: ["等待今日输入"],
    review_content: ["到期复习", "错题回流", "考纲兜底"],
    target_minutes: 35,
    status: "empty_context"
  },
  questions_total: 0,
  questions_done: 0,
  accuracy: 0,
  summary: ""
};

const MOCK_PROFILE: Profile = {
  display_name: "boss",
  target_language: "未设置",
  exam_id: "unassigned",
  exam_name: "未设置",
  learning_goal: "",
  learning_background: "",
  persona: "professional",
  global_user_prompt: ""
};

const FALLBACK_PROVIDERS: ProviderOption[] = [
  { id: "mock", label: "Mock Provider（本地模拟）", kind: "mock", base_url: "", model: "mock-tutor-v1", model_options: ["mock-tutor-v1"] },
  { id: "openai", label: "OpenAI（官方）", kind: "openai-compatible", base_url: "https://api.openai.com/v1", model: "gpt-5.2", model_options: ["gpt-5.2", "gpt-5.1", "gpt-5", "gpt-5-mini", "gpt-4.1-mini"] },
  { id: "deepseek", label: "DeepSeek（深度求索）", kind: "openai-compatible", base_url: "https://api.deepseek.com", model: "deepseek-v4-flash", model_options: ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"] },
  { id: "qwen", label: "Qwen（通义千问）", kind: "openai-compatible", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus", model_options: ["qwen-plus", "qwen-turbo", "qwen-max", "qwen3-plus", "qwen3-max"] },
  { id: "zhipu", label: "Zhipu AI（智谱）", kind: "openai-compatible", base_url: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash", model_options: ["glm-4-flash", "glm-4-plus", "glm-4-air", "glm-4.5"] },
  { id: "moonshot", label: "Moonshot（月之暗面）", kind: "openai-compatible", base_url: "https://api.moonshot.cn/v1", model: "kimi-k2-turbo-preview", model_options: ["kimi-k2-turbo-preview", "kimi-k2-thinking", "moonshot-v1-8k", "moonshot-v1-32k"] },
  { id: "mimo", label: "Xiaomi MiMo（小米 MiMo）", kind: "openai-compatible", base_url: "https://api.xiaomimimo.com/v1", model: "mimo-v2.5-pro", model_options: ["mimo-v2.5-pro", "mimo-v2-pro", "mimo-v2-flash", "mimo-v2-omni"] },
  { id: "local", label: "Local Model（本地模型）", kind: "openai-compatible", base_url: "http://localhost:11434/v1", model: "qwen2.5:7b", model_options: ["qwen2.5:7b", "deepseek-r1:8b", "llama3.1:8b"] },
  { id: "custom", label: "Custom OpenAI-compatible（自定义 OpenAI 兼容）", kind: "openai-compatible", base_url: "", model: "", model_options: [] }
];

const DEFAULT_MODEL_CONFIG: ModelConfig = {
  provider_id: "mock",
  base_url: "",
  model: "mock-tutor-v1",
  has_api_key: false
};

function selectedProvider(providers: ProviderOption[], providerId: string) {
  return providers.find((item) => item.id === providerId) || FALLBACK_PROVIDERS[0];
}

function uniqueModelOptions(provider: ProviderOption, currentModel: string) {
  return Array.from(new Set([...(provider.model_options || []), provider.model, currentModel].filter(Boolean)));
}

function normalizeProviders(providers: ProviderOption[] | undefined) {
  if (!providers?.length) return FALLBACK_PROVIDERS;
  return providers.map((provider) => ({
    ...(FALLBACK_PROVIDERS.find((item) => item.id === provider.id) || {}),
    ...provider,
    base_url: provider.base_url || FALLBACK_PROVIDERS.find((item) => item.id === provider.id)?.base_url || "",
    model: provider.model || FALLBACK_PROVIDERS.find((item) => item.id === provider.id)?.model || "",
    model_options: provider.model_options?.length
      ? provider.model_options
      : FALLBACK_PROVIDERS.find((item) => item.id === provider.id)?.model_options || [provider.model].filter(Boolean)
  }));
}

function normalizeModelConfig(config: ModelConfig | undefined) {
  return {
    ...DEFAULT_MODEL_CONFIG,
    ...(config || {})
  };
}

const personalityOptions = [
  { id: "none", label: "空", prompt: "不额外注入人格提示词。" },
  { id: "warm", label: "热情开朗", prompt: "反馈积极，语气明亮，不夸张。" },
  { id: "professional", label: "专业靠谱", prompt: "结论清晰，建议具体可执行。" },
  { id: "humorous", label: "幽默风趣", prompt: "轻松但不影响学习严谨性。" },
  { id: "custom", label: "自定义", prompt: "使用用户自定义人格提示词。" }
];

function groupSessions(sessions: SessionItem[]) {
  return sessions.reduce<Record<string, SessionItem[]>>((acc, session) => {
    acc[session.folder_date] = acc[session.folder_date] || [];
    acc[session.folder_date].push(session);
    return acc;
  }, {});
}

async function apiGet<T>(url: string): Promise<T> {
  const response = await fetch(`${API}${url}`);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(`${API}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

export default function App() {
  const appRef = useRef<HTMLDivElement | null>(null);
  const [profile, setProfile] = useState<Profile>(MOCK_PROFILE);
  const [providers, setProviders] = useState<ProviderOption[]>(FALLBACK_PROVIDERS);
  const [modelConfig, setModelConfig] = useState<ModelConfig>(DEFAULT_MODEL_CONFIG);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [dailyPanel, setDailyPanel] = useState<DailyPanel>(DEFAULT_PANEL);
  const [activeQuestion, setActiveQuestion] = useState<Question | null>(null);
  const [tokenUsage, setTokenUsage] = useState({ input: 0, output: 0, total: 0, estimated_current_context: 0 });
  const [input, setInput] = useState("");
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [leftOpen, setLeftOpen] = useState(() => localStorage.getItem("leftOpen") !== "false");
  const [rightOpen, setRightOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => (localStorage.getItem("themeMode") as ThemeMode | null) || "system");
  const [fontSize, setFontSize] = useState(() => Number(localStorage.getItem("fontSize") || 16));
  const [expandedDates, setExpandedDates] = useState<Record<string, boolean>>(() => {
    const saved = localStorage.getItem("expandedDates");
    return saved ? JSON.parse(saved) : { [new Date().toISOString().slice(0, 10)]: true };
  });
  const [selectedText, setSelectedText] = useState("");
  const [branchMessages, setBranchMessages] = useState<Message[]>([]);

  const sessionsByDate = useMemo(() => groupSessions(sessions), [sessions]);
  const emptyContext = messages.length === 0;

  useGSAP(
    () => {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduceMotion) return;
      
      const tl = gsap.timeline({
        defaults: { clearProps: "transform" }
      });
      tl.from(".panel-motion", {
        y: 40,
        scale: 0.9,
        duration: 0.7,
        ease: "elastic.out(1, 0.6)",
        stagger: 0.08
      });
      
      gsap.from(".memory-strip span", {
        scale: 0,
        rotationZ: -10,
        duration: 0.6,
        ease: "back.out(1.7)",
        stagger: 0.05,
        delay: 0.3,
        clearProps: "transform"
      });
      
      gsap.from(".score-stack .stat", {
        y: 30,
        duration: 0.6,
        ease: "back.out(1.5)",
        stagger: 0.1,
        delay: 0.2,
        clearProps: "transform"
      });
    },
    { scope: appRef }
  );

  useEffect(() => {
    localStorage.setItem("leftOpen", String(leftOpen));
  }, [leftOpen]);

  useEffect(() => {
    localStorage.setItem("expandedDates", JSON.stringify(expandedDates));
  }, [expandedDates]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const applyTheme = () => {
      const resolvedTheme = themeMode === "system" ? (media.matches ? "dark" : "light") : themeMode;
      document.documentElement.dataset.theme = resolvedTheme;
      document.documentElement.dataset.themeMode = themeMode;
      document.documentElement.style.fontSize = `${fontSize}px`;
      localStorage.setItem("themeMode", themeMode);
      localStorage.setItem("fontSize", String(fontSize));
    };
    applyTheme();
    media.addEventListener("change", applyTheme);
    return () => media.removeEventListener("change", applyTheme);
  }, [fontSize, themeMode]);

  useEffect(() => {
    apiGet<{
      profile: Profile;
      sessions: SessionItem[];
      token_usage: typeof tokenUsage;
      providers: ProviderOption[];
      model_config: ModelConfig;
    }>("/api/bootstrap")
      .then((data) => {
        setProfile(data.profile);
        setProviders(normalizeProviders(data.providers));
        setModelConfig(normalizeModelConfig(data.model_config));
        setSessions(data.sessions);
        setTokenUsage(data.token_usage);
        setOnboardingOpen(data.profile.exam_id === "unassigned");
      })
      .catch(() => setOnboardingOpen(true));
  }, []);

  const sendMessage = useCallback(async () => {
    const content = input.trim();
    if (!content) return;
    const userMessage: Message = { id: `local-${Date.now()}`, role: "user", content };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    const data = await apiPost<{
      session_id: string;
      message: Message;
      daily_panel: DailyPanel;
      active_question: Question | null;
      token_usage: typeof tokenUsage;
    }>("/api/chat", { content, session_id: activeSessionId });
    setActiveSessionId(data.session_id);
    setMessages((current) => [...current, data.message]);
    setDailyPanel(data.daily_panel);
    setActiveQuestion(data.active_question);
    setTokenUsage(data.token_usage);
    const refreshed = await apiGet<{ sessions: SessionItem[] }>("/api/sessions");
    setSessions(refreshed.sessions);
  }, [activeSessionId, input]);

  const toggleDate = useCallback((date: string) => {
    setExpandedDates((current) => ({ ...current, [date]: !current[date] }));
  }, []);

  const startBranch = useCallback(async () => {
    if (!activeSessionId || !selectedText.trim()) return;
    const data = await apiPost<{ branch_id: string; message: string }>("/api/branch", {
      session_id: activeSessionId,
      selected_text: selectedText,
      message: "解释这段内容，并指出是否应写回复习卡片。"
    });
    setRightOpen(true);
    setBranchMessages([
      { id: `${data.branch_id}-u`, role: "user", content: selectedText },
      { id: `${data.branch_id}-a`, role: "assistant", content: data.message }
    ]);
  }, [activeSessionId, selectedText]);

  return (
    <div className="app-shell" ref={appRef}>
      <aside className={`left-rail panel-motion ${leftOpen ? "open" : "closed"}`}>
        <div className="rail-top">
          <InteractiveButton className="icon-button" onClick={() => setLeftOpen((value) => !value)} title="折叠侧栏">
            <Sidebar size={20} />
          </InteractiveButton>
          {leftOpen && <span className="brand">Lang Drill</span>}
        </div>
        {leftOpen && (
          <>
            <DailyStudyPanel panel={dailyPanel} />
            <div className="session-list">
              {Object.entries(sessionsByDate).map(([date, items]) => (
                <section className="date-group" key={date}>
                  <button className="date-toggle" onClick={() => toggleDate(date)}>
                    <CaretDown className={expandedDates[date] ? "rotated" : ""} size={14} />
                    <span>{date}</span>
                  </button>
                  {expandedDates[date] &&
                    items.map((item) => (
                      <button
                        className={`session-link ${item.id === activeSessionId ? "active" : ""}`}
                        key={item.id}
                        onClick={() => setActiveSessionId(item.id)}
                      >
                        <ChatCircleText size={16} />
                        <span>{item.title}</span>
                      </button>
                    ))}
                </section>
              ))}
            </div>
            <InteractiveButton className="settings-button" onClick={() => setSettingsOpen(true)}>
              <GearSix size={18} />
              <span>设置</span>
            </InteractiveButton>
          </>
        )}
      </aside>

      <main className="chat-main panel-motion">
        {emptyContext && <LongTermPanel profile={profile} tokenUsage={tokenUsage} />}
        {activeQuestion && <QuestionDock question={activeQuestion} />}
        <div className="message-stream" onMouseUp={() => setSelectedText(window.getSelection()?.toString() || "")}>
          {messages.map((message) => (
            <MessageItem key={message.id} message={message} />
          ))}
        </div>
        {selectedText && (
          <InteractiveButton className="branch-fab" onClick={startBranch}>
            <GitBranch size={16} />
            开启分支对话
          </InteractiveButton>
        )}
        <div className="composer-wrap">
          {emptyContext && (
            <div className="first-prompt">
              {profile.display_name}，今天打算从哪里开始？
            </div>
          )}
          <div className="composer">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="输入今日学习内容、答案或任何学习请求"
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
            />
            <InteractiveButton className="send-button" onClick={() => void sendMessage()} title="发送">
              <PaperPlaneRight size={20} weight="fill" />
            </InteractiveButton>
          </div>
        </div>
      </main>

      <aside className={`right-rail panel-motion ${rightOpen ? "open" : "closed"}`}>
        <InteractiveButton className="right-toggle" onClick={() => setRightOpen((value) => !value)} title="展开分支对话">
          {rightOpen ? <CaretRight size={18} /> : <CaretLeft size={18} />}
        </InteractiveButton>
        {rightOpen && (
          <div className="branch-panel">
            <div className="panel-title">
              <GitBranch size={18} />
              <span>分支对话</span>
            </div>
            {branchMessages.length === 0 ? (
              <p className="empty-copy">目前没有分支对话。</p>
            ) : (
              branchMessages.map((message) => (
                <div className={`branch-message ${message.role}`} key={message.id}>
                  {message.content}
                </div>
              ))
            )}
          </div>
        )}
      </aside>

      {settingsOpen && (
        <SettingsDialog
          profile={profile}
          providers={providers}
          modelConfig={modelConfig}
          themeMode={themeMode}
          fontSize={fontSize}
          tokenUsage={tokenUsage}
          onClose={() => setSettingsOpen(false)}
          onProfileChange={setProfile}
          onModelConfigChange={setModelConfig}
          onAppearanceChange={(nextTheme, nextFontSize) => {
            setThemeMode(nextTheme);
            setFontSize(nextFontSize);
          }}
          onOpenOnboarding={() => {
            setSettingsOpen(false);
            setOnboardingOpen(true);
          }}
        />
      )}
      {onboardingOpen && (
        <OnboardingDialog
          profile={profile}
          providers={providers}
          modelConfig={modelConfig}
          onClose={() => setOnboardingOpen(false)}
          onDone={(nextProfile) => {
            setProfile(nextProfile);
            void apiGet<{ model_config?: ModelConfig }>("/api/bootstrap").then((data) => setModelConfig(normalizeModelConfig(data.model_config)));
            setOnboardingOpen(false);
          }}
        />
      )}
    </div>
  );
}

function DailyStudyPanel({ panel }: { panel: DailyPanel }) {
  return (
    <section className="daily-panel">
      <div className="panel-title">
        <Target size={18} />
        <span>当日学习</span>
      </div>
      <div className="metric-row">
        <div>
          <strong>{panel.date}</strong>
          <span>{panel.status}</span>
        </div>
        <div>
          <strong>{panel.questions_done}/{panel.questions_total}</strong>
          <span>题目</span>
        </div>
      </div>
      <div className="thin-progress">
        <span style={{ width: `${panel.questions_total ? (panel.questions_done / panel.questions_total) * 100 : 8}%` }} />
      </div>
      <div className="mini-list">
        {(panel.plan.new_content || []).slice(0, 2).map((item) => (
          <p key={item}>{item}</p>
        ))}
      </div>
    </section>
  );
}

function LongTermPanel({ profile, tokenUsage }: { profile: Profile; tokenUsage: Record<string, number> }) {
  return (
    <section className="long-panel">
      <div className="long-grid">
        <div>
          <span className="kicker">Learning Memory（学习记忆）</span>
          <h1>长期学习记录总面板</h1>
          <p>{profile.exam_name === "未设置" ? "完成首次设置后，这里会显示目标考试、弱项、复习到期和最近表现。" : `${profile.exam_name} · ${profile.target_language}`}</p>
        </div>
        <div className="score-stack">
          <Stat label="Token（令牌）" value={String(tokenUsage.total)} />
          <Stat label="到期复习" value="3" />
          <Stat label="掌握度" value="V1" />
        </div>
      </div>
      <div className="memory-strip">
        <span><ShieldCheck size={16} /> 数据库为事实来源</span>
        <span><Brain size={16} /> 动态提示词组装</span>
        <span><ListBullets size={16} /> 三 Agent 协作</span>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function QuestionDock({ question }: { question: Question }) {
  return (
    <section className="question-dock">
      <div className="question-head">
        <CheckCircle size={18} />
        <span>当前题目</span>
      </div>
      <p>{question.prompt}</p>
      <div className="options">
        {question.options.map((option, index) => (
          <span key={option}>{String.fromCharCode(65 + index)}. {option}</span>
        ))}
      </div>
    </section>
  );
}

function SettingsDialog({
  profile,
  providers,
  modelConfig,
  themeMode,
  fontSize,
  tokenUsage,
  onClose,
  onProfileChange,
  onModelConfigChange,
  onAppearanceChange,
  onOpenOnboarding
}: {
  profile: Profile;
  providers: ProviderOption[];
  modelConfig: ModelConfig;
  themeMode: ThemeMode;
  fontSize: number;
  tokenUsage: Record<string, number>;
  onClose: () => void;
  onProfileChange: (profile: Profile) => void;
  onModelConfigChange: (config: ModelConfig) => void;
  onAppearanceChange: (themeMode: ThemeMode, fontSize: number) => void;
  onOpenOnboarding: () => void;
}) {
  const [draft, setDraft] = useState(profile);
  const [modelDraft, setModelDraft] = useState<ModelConfig>({ ...modelConfig, api_key: "" });
  const [customModel, setCustomModel] = useState("");
  const [appearanceDraft, setAppearanceDraft] = useState({ themeMode, fontSize });
  const [reviewIntensity, setReviewIntensity] = useState(3);
  const [saveState, setSaveState] = useState("");
  const provider = selectedProvider(providers, modelDraft.provider_id);
  const modelOptions = uniqueModelOptions(provider, modelDraft.model);
  const chooseProvider = (providerId: string) => {
    const nextProvider = selectedProvider(providers, providerId);
    const nextModel = nextProvider.model_options?.[0] || nextProvider.model || "";
    setModelDraft({
      ...modelDraft,
      provider_id: nextProvider.id,
      base_url: nextProvider.base_url,
      model: nextModel
    });
    setCustomModel("");
  };
  const saveModelConfig = async () => {
    const finalModel = customModel.trim() || modelDraft.model;
    const data = await apiPost<{ model_config: ModelConfig }>("/api/model-config", {
      ...modelDraft,
      model: finalModel
    });
    onModelConfigChange(data.model_config);
    setSaveState("模型配置已保存到本地 .env。");
  };
  const saveSettings = async () => {
    onProfileChange(draft);
    onAppearanceChange(appearanceDraft.themeMode, appearanceDraft.fontSize);
    try {
      await saveModelConfig();
    } finally {
      onClose();
    }
  };
  return (
    <div className="modal-backdrop">
      <div className="settings-modal">
        <div className="modal-head">
          <h2>设置</h2>
          <button className="icon-button" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="settings-grid">
          <SettingSection title="模型提供商">
            <select value={modelDraft.provider_id} onChange={(event) => chooseProvider(event.target.value)}>
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>{provider.label}</option>
              ))}
            </select>
            <input
              value={modelDraft.base_url}
              onChange={(event) => setModelDraft({ ...modelDraft, base_url: event.target.value })}
              placeholder={provider.base_url || "Mock Provider（本地模拟）不需要 Base URL"}
            />
            <input
              value={modelDraft.api_key || ""}
              onChange={(event) => setModelDraft({ ...modelDraft, api_key: event.target.value })}
              placeholder={provider.kind === "mock" ? "Mock Provider（本地模拟）不需要 API Key" : modelDraft.has_api_key ? "API Key（接口密钥）已配置，留空则不覆盖" : "API Key（接口密钥）"}
              type="password"
              autoComplete="off"
            />
            <select value={modelDraft.model} onChange={(event) => setModelDraft({ ...modelDraft, model: event.target.value })}>
              {modelOptions.map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
            <input
              value={customModel}
              onChange={(event) => setCustomModel(event.target.value)}
              placeholder="自定义模型名称，填写后优先使用"
            />
            <button className="inline-action" onClick={() => void saveModelConfig()}>保存模型配置</button>
            {saveState && <p className="hint">{saveState}</p>}
          </SettingSection>
          <SettingSection title="Token 使用">
            <div className="token-card"><strong>{tokenUsage.total}</strong><span>累计 token（令牌）</span></div>
          </SettingSection>
          <SettingSection title="学习目标">
            <input value={draft.learning_goal} onChange={(event) => setDraft({ ...draft, learning_goal: event.target.value })} placeholder="目标考试、分数或能力目标" />
          </SettingSection>
          <SettingSection title="学习背景">
            <textarea value={draft.learning_background} onChange={(event) => setDraft({ ...draft, learning_background: event.target.value })} placeholder="当前水平、弱项、已学内容" />
          </SettingSection>
          <SettingSection title="个性化">
            <select value={draft.persona} onChange={(event) => setDraft({ ...draft, persona: event.target.value })}>
              {personalityOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
            </select>
            <p className="hint">{personalityOptions.find((item) => item.id === draft.persona)?.prompt}</p>
            {draft.persona === "custom" && (
              <textarea
                value={draft.global_user_prompt || ""}
                onChange={(event) => setDraft({ ...draft, global_user_prompt: event.target.value })}
                placeholder="填写自定义人格提示词，例如：语气冷静、少废话、每次先给结论。"
              />
            )}
          </SettingSection>
          <SettingSection title="功能设置">
            <label><input type="checkbox" defaultChecked /> 联网检查考纲最新版</label>
            <label><input type="checkbox" defaultChecked /> 分支默认不写回主会话</label>
            <label><input type="checkbox" defaultChecked /> 简单选择题程序判定</label>
            <button className="inline-action" onClick={onOpenOnboarding}>重新打开初始化设置</button>
          </SettingSection>
          <SettingSection title="学习算法">
            <select><option>mastery_score V1（掌握度 V1）</option><option>FSRS-ready（FSRS 预留）</option></select>
            <label className="range-field">
              <span>复习强度：{reviewIntensity}</span>
              <input
                type="range"
                min="1"
                max="5"
                value={reviewIntensity}
                onChange={(event) => setReviewIntensity(Number(event.target.value))}
              />
              <small>控制到期复习和错题回流的占比，1 更轻，5 更密集。</small>
            </label>
          </SettingSection>
          <SettingSection title="外观">
            <div className="theme-row">
              <button className={appearanceDraft.themeMode === "system" ? "active" : ""} onClick={() => setAppearanceDraft({ ...appearanceDraft, themeMode: "system" })}><GearSix size={16} /> 跟随系统</button>
              <button className={appearanceDraft.themeMode === "light" ? "active" : ""} onClick={() => setAppearanceDraft({ ...appearanceDraft, themeMode: "light" })}><Sun size={16} /> 浅色</button>
              <button className={appearanceDraft.themeMode === "dark" ? "active" : ""} onClick={() => setAppearanceDraft({ ...appearanceDraft, themeMode: "dark" })}><Moon size={16} /> 深色</button>
            </div>
            <label className="range-field">
              <span>字体大小：{appearanceDraft.fontSize}px</span>
              <input
                type="range"
                min="14"
                max="20"
                value={appearanceDraft.fontSize}
                onChange={(event) => setAppearanceDraft({ ...appearanceDraft, fontSize: Number(event.target.value) })}
              />
              <small>调整聊天、设置和侧栏文字的整体显示大小。</small>
            </label>
          </SettingSection>
        </div>
        <div className="modal-actions">
          <button onClick={onClose}>取消</button>
          <button className="primary" onClick={() => void saveSettings()}>保存</button>
        </div>
      </div>
    </div>
  );
}

function SettingSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="setting-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function OnboardingDialog({
  profile,
  providers,
  modelConfig,
  onClose,
  onDone
}: {
  profile: Profile;
  providers: ProviderOption[];
  modelConfig: ModelConfig;
  onClose: () => void;
  onDone: (profile: Profile) => void;
}) {
  const [draft, setDraft] = useState({
    provider_id: modelConfig.provider_id || "mock",
    base_url: modelConfig.base_url || "",
    api_key: "",
    model: modelConfig.model || "mock-tutor-v1",
    display_name: profile.display_name,
    target_language: "日语",
    exam_id: "cjt4",
    exam_name: "大学日语四级",
    learning_goal: "",
    learning_background: "",
    search_years: 3
  });
  const [customModel, setCustomModel] = useState("");
  const provider = selectedProvider(providers, draft.provider_id);
  const modelOptions = uniqueModelOptions(provider, draft.model);
  const chooseProvider = (providerId: string) => {
    const nextProvider = selectedProvider(providers, providerId);
    const nextModel = nextProvider.model_options?.[0] || nextProvider.model || "";
    setDraft({
      ...draft,
      provider_id: nextProvider.id,
      base_url: nextProvider.base_url,
      model: nextModel
    });
    setCustomModel("");
  };

  const submit = async () => {
    const data = await apiPost<{ profile: Profile }>("/api/initialize", {
      ...draft,
      model: customModel.trim() || draft.model
    });
    onDone(data.profile);
  };

  return (
    <div className="modal-backdrop">
      <div className="onboarding-modal">
        <div className="modal-head">
          <h2>初始化设置</h2>
          <button className="icon-button" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="onboarding-flow">
          <label>供应商<select value={draft.provider_id} onChange={(event) => chooseProvider(event.target.value)}>{providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}</select></label>
          <label>Base URL（基础网址）<input value={draft.base_url} onChange={(event) => setDraft({ ...draft, base_url: event.target.value })} placeholder={provider.base_url || "Mock Provider（本地模拟）不需要 Base URL"} /></label>
          <label>API Key（接口密钥）<input value={draft.api_key} onChange={(event) => setDraft({ ...draft, api_key: event.target.value })} placeholder={provider.kind === "mock" ? "Mock Provider（本地模拟）不需要 API Key" : "留空则不覆盖已有密钥"} type="password" autoComplete="off" /></label>
          <label>模型选项<select value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })}>{modelOptions.map((model) => <option key={model} value={model}>{model}</option>)}</select></label>
          <label>自定义模型<input value={customModel} onChange={(event) => setCustomModel(event.target.value)} placeholder="填写后优先使用，例如厂商新模型名" /></label>
          <label>称呼<input value={draft.display_name} onChange={(event) => setDraft({ ...draft, display_name: event.target.value })} /></label>
          <label>目标语言<input value={draft.target_language} onChange={(event) => setDraft({ ...draft, target_language: event.target.value })} /></label>
          <label>目标考试<input value={draft.exam_name} onChange={(event) => setDraft({ ...draft, exam_name: event.target.value })} /></label>
          <label>学习目标<textarea value={draft.learning_goal} onChange={(event) => setDraft({ ...draft, learning_goal: event.target.value })} /></label>
          <label>学习背景<textarea value={draft.learning_background} onChange={(event) => setDraft({ ...draft, learning_background: event.target.value })} /></label>
          <label>真题参考年限<input type="number" min="1" max="10" value={draft.search_years} onChange={(event) => setDraft({ ...draft, search_years: Number(event.target.value) })} /></label>
        </div>
        <div className="source-note">
          系统会先检查内置考纲；缺失或不是最新版时，再按官方与可靠公开来源检索。冷门语种会走规则化搜索。
        </div>
        <div className="modal-actions">
          <button onClick={onClose}>稍后</button>
          <button className="primary" onClick={() => void submit()}>进入日常使用</button>
        </div>
      </div>
    </div>
  );
}
