import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import {
  Brain,
  CaretDown,
  ChatCircleText,
  CheckCircle,
  GearSix,
  GitBranch,
  ListBullets,
  Moon,
  PaperPlaneRight,
  Plus,
  ShieldCheck,
  Sidebar,
  Sparkle,
  Sun,
  Target,
  UserCircle,
  X
} from "@phosphor-icons/react";
import { apiGet, apiPost } from "./api";
import { RightWorkbench } from "./components/RightWorkbench";
import type {
  DailyPanel,
  ExamOption,
  Message,
  ModelConfig,
  Profile,
  ProviderOption,
  Question,
  SessionItem,
  SyllabusStatus,
  ThemeMode,
  ThinkingLevel,
  TokenUsage
} from "./types";

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

function ThinkingBubble() {
  return (
    <article className="message assistant thinking-message" aria-live="polite" aria-label="模型正在思考">
      <div className="avatar"><Sparkle size={18} /></div>
      <div className="bubble thinking-bubble">
        <span>模型正在思考</span>
        <span className="thinking-dots" aria-hidden="true"><i /> <i /> <i /></span>
      </div>
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
  knowledge_total: 0,
  knowledge_done: 0,
  knowledge_terms: [],
  exam_id: "cet4",
  exam_name: "大学英语四级",
  accuracy: 0,
  summary: ""
};

const MOCK_PROFILE: Profile = {
  display_name: "boss",
  target_language: "英语",
  exam_id: "cet4",
  exam_name: "大学英语四级",
  learning_goal: "",
  learning_background: "",
  persona: "professional",
  global_user_prompt: ""
};

const FALLBACK_PROVIDERS: ProviderOption[] = [
  { id: "deepseek", label: "DeepSeek（深度求索）", kind: "openai-compatible", base_url: "https://api.deepseek.com", model: "deepseek-chat", model_options: ["deepseek-chat", "deepseek-reasoner"] },
  { id: "mimo", label: "Xiaomi MiMo（小米 MiMo）", kind: "openai-compatible", base_url: "https://api.xiaomimimo.com/v1", model: "mimo-v2.5-pro", model_options: ["mimo-v2.5-pro", "mimo-v2-pro"] },
  { id: "custom", label: "Custom OpenAI-compatible（自定义 OpenAI 兼容）", kind: "openai-compatible", base_url: "", model: "", model_options: [] }
];

const DEFAULT_MODEL_CONFIG: ModelConfig = {
  provider_id: "mimo",
  base_url: "https://api.xiaomimimo.com/v1",
  model: "mimo-v2.5-pro",
  thinking_level: "auto",
  thinking_level_options: [
    { id: "auto", label: "自动", api_value: "" },
    { id: "low", label: "低", api_value: "low" },
    { id: "medium", label: "中", api_value: "medium" },
    { id: "high", label: "高", api_value: "high" }
  ],
  has_api_key: false
};

const DEFAULT_EXAM_OPTIONS: ExamOption[] = [
  {
    id: "cet4",
    name: "英语四级",
    target_language: "英语",
    official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
    default_year: 2016,
    description: "大学英语四级，默认考试。"
  },
  {
    id: "cjt4",
    name: "日语四级",
    target_language: "日语",
    official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
    default_year: 2024,
    description: "大学日语四级，新版考纲 2024 年启用。"
  },
  {
    id: "ielts",
    name: "雅思",
    target_language: "英语",
    official_url: "https://ielts.org/take-a-test/test-types/ielts-academic-test",
    default_year: 2026,
    description: "雅思学术类考试结构，官方页面持续维护。"
  },
  {
    id: "toefl",
    name: "托福",
    target_language: "英语",
    official_url: "https://www.ets.org/toefl/test-takers/ibt/about/content.html",
    default_year: 2026,
    description: "托福网考考试结构，官方页面持续维护。"
  },
  {
    id: "gaokao-english",
    name: "高考英语",
    target_language: "英语",
    official_url: "https://www.moe.gov.cn/srcsite/A26/s8001/202006/t20200603_462199.html",
    default_year: 2020,
    description: "普通高中英语课程标准，按高考英语能力框架使用。"
  },
  {
    id: "custom",
    name: "添加自定义",
    target_language: "",
    official_url: "",
    default_year: null,
    description: "可配置考纲网址自动下载或手动导入。"
  }
];

const DEFAULT_SYLLABUS_STATUS: SyllabusStatus = {
  exam_id: "cet4",
  current_source_id: "",
  current_year: 2016,
  current_title: "全国大学英语四、六级考试大纲（2016年修订版）",
  official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
  sources: []
};

function isOptionAnswer(content: string) {
  return /^(?:选择?\s*)?[A-D]$/i.test(content.trim()) || /^答案是\s*[A-D]$/i.test(content.trim());
}

function cleanQuestionPrompt(question: Question) {
  return question.prompt.replace(/^第\s*\d+\s*题\s*\/\s*共\s*\d+\s*题\s*\n?/, "").trim();
}

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
    ...(config || {}),
    thinking_level: (config?.thinking_level || DEFAULT_MODEL_CONFIG.thinking_level) as ThinkingLevel,
    thinking_level_options: config?.thinking_level_options?.length
      ? config.thinking_level_options
      : DEFAULT_MODEL_CONFIG.thinking_level_options
  };
}

function thinkingLevelLabel(config: ModelConfig) {
  const current = config.thinking_level || "auto";
  return config.thinking_level_options?.find((item) => item.id === current)?.label || "自动";
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

export default function App() {
  const appRef = useRef<HTMLDivElement | null>(null);
  const messageEndRef = useRef<HTMLDivElement | null>(null);
  const [profile, setProfile] = useState<Profile>(MOCK_PROFILE);
  const [providers, setProviders] = useState<ProviderOption[]>(FALLBACK_PROVIDERS);
  const [modelConfig, setModelConfig] = useState<ModelConfig>(DEFAULT_MODEL_CONFIG);
  const [examOptions, setExamOptions] = useState<ExamOption[]>(DEFAULT_EXAM_OPTIONS);
  const [syllabusStatus, setSyllabusStatus] = useState<SyllabusStatus>(DEFAULT_SYLLABUS_STATUS);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [dailyPanel, setDailyPanel] = useState<DailyPanel>(DEFAULT_PANEL);
  const [activeQuestion, setActiveQuestion] = useState<Question | null>(null);
  const [tokenUsage, setTokenUsage] = useState({ input: 0, output: 0, total: 0, estimated_current_context: 0 });
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
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
    messageEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, activeQuestion, sending]);

  useEffect(() => {
    apiGet<{
      profile: Profile;
      sessions: SessionItem[];
      token_usage: typeof tokenUsage;
      providers: ProviderOption[];
      model_config: ModelConfig;
      exam_options?: ExamOption[];
      syllabus_status?: SyllabusStatus;
    }>("/api/bootstrap")
      .then((data) => {
        setProfile(data.profile);
        setProviders(normalizeProviders(data.providers));
        setModelConfig(normalizeModelConfig(data.model_config));
        setExamOptions(data.exam_options?.length ? data.exam_options : DEFAULT_EXAM_OPTIONS);
        setSyllabusStatus(data.syllabus_status || DEFAULT_SYLLABUS_STATUS);
        setSessions(data.sessions);
        setTokenUsage(data.token_usage);
        setOnboardingOpen(data.profile.exam_id === "unassigned");
      })
      .catch(() => setOnboardingOpen(true));
  }, []);

  const sendMessage = useCallback(async () => {
    const content = input.trim();
    if (!content || sending) return;
    const userMessage: Message = { id: `local-${Date.now()}`, role: "user", content };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    if (activeQuestion && isOptionAnswer(content)) {
      setActiveQuestion(null);
    }
    setSending(true);
    try {
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
    } catch (err) {
      const errorMsg: Message = {
        id: `error-${Date.now()}`,
        role: "assistant",
        content: `⚠️ 请求失败：${err instanceof Error ? err.message : "未知错误"}。请检查后端是否运行或网络是否正常。`
      };
      setMessages((current) => [...current, errorMsg]);
    } finally {
      setSending(false);
    }
  }, [activeQuestion, activeSessionId, input, sending]);

  const sendQuestionAnswer = useCallback(async (selectedOption: string, extraPrompt: string) => {
    if (!activeQuestion || sending) return;
    const cleanOption = selectedOption.trim().toUpperCase();
    if (!cleanOption) return;
    const visibleContent = extraPrompt.trim()
      ? `${cleanOption}\n补充提问：${extraPrompt.trim()}`
      : cleanOption;
    const userMessage: Message = { id: `local-${Date.now()}`, role: "user", content: visibleContent };
    setMessages((current) => [...current, userMessage]);
    setActiveQuestion(null);
    setSending(true);
    try {
      const data = await apiPost<{
        session_id: string;
        message: Message;
        daily_panel: DailyPanel;
        active_question: Question | null;
        token_usage: typeof tokenUsage;
      }>("/api/chat", {
        content: "",
        session_id: activeSessionId,
        selected_option: cleanOption,
        question_id: activeQuestion.id,
        extra_prompt: extraPrompt
      });
      setActiveSessionId(data.session_id);
      setMessages((current) => [...current, data.message]);
      setDailyPanel(data.daily_panel);
      setActiveQuestion(data.active_question);
      setTokenUsage(data.token_usage);
      const refreshed = await apiGet<{ sessions: SessionItem[] }>("/api/sessions");
      setSessions(refreshed.sessions);
    } catch (err) {
      const errorMsg: Message = {
        id: `error-${Date.now()}`,
        role: "assistant",
        content: `请求失败：${err instanceof Error ? err.message : "未知错误"}。请检查后端是否运行或网络是否正常。`
      };
      setMessages((current) => [...current, errorMsg]);
    } finally {
      setSending(false);
    }
  }, [activeQuestion, activeSessionId, sending]);

  const startNewChat = useCallback(async () => {
    try {
      const data = await apiPost<{
        session_id: string;
        sessions: SessionItem[];
        daily_panel: DailyPanel;
      }>("/api/sessions/new", {});
      setActiveSessionId(data.session_id);
      setSessions(data.sessions);
      setDailyPanel(data.daily_panel);
      setActiveQuestion(null);
      setMessages([]);
      setInput("");
    } catch {
      setActiveSessionId(null);
      setActiveQuestion(null);
      setMessages([]);
      setInput("");
    }
  }, []);

  const saveQuickModelConfig = useCallback(async (nextConfig: ModelConfig) => {
    const data = await apiPost<{ model_config: ModelConfig; providers?: ProviderOption[] }>("/api/model-config", {
      provider_id: nextConfig.provider_id,
      base_url: nextConfig.base_url,
      model: nextConfig.model,
      thinking_level: nextConfig.thinking_level || "auto"
    });
    setModelConfig(normalizeModelConfig(data.model_config));
    if (data.providers) {
      setProviders(normalizeProviders(data.providers));
    }
  }, []);

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
            <button className="new-chat-button" onClick={() => void startNewChat()} title="新建聊天">
              <Plus size={16} />
              <span>新建聊天</span>
            </button>
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
                        onClick={async () => {
                          setActiveSessionId(item.id);
                          try {
                            const detail = await apiGet<{
                              session: Record<string, unknown>;
                              messages: Message[];
                              daily_panel: DailyPanel;
                              active_question: Question | null;
                              token_usage: typeof tokenUsage;
                            }>(`/api/sessions/${item.id}`);
                            if (detail.messages) {
                              setMessages(detail.messages);
                              setDailyPanel(detail.daily_panel);
                              setActiveQuestion(detail.active_question);
                              setTokenUsage(detail.token_usage);
                            }
                          } catch {
                            // 加载失败时保持当前状态
                          }
                        }}
                      >
                        <ChatCircleText size={16} />
                        <span>{item.title}</span>
                      </button>
                    ))}
                </section>
              ))}
            </div>
            <InteractiveButton className="settings-button" onClick={() => setSettingsOpen(true)} title="设置">
              <GearSix size={18} />
            </InteractiveButton>
          </>
        )}
      </aside>

      <main className="chat-main panel-motion">
        <div className="message-stream" onMouseUp={() => setSelectedText(window.getSelection()?.toString() || "")}>
          {emptyContext && <LongTermPanel profile={profile} tokenUsage={tokenUsage} />}
          {messages.map((message) => (
            <MessageItem key={message.id} message={message} />
          ))}
          {sending && <ThinkingBubble />}
          {activeQuestion?.status === "ready" && (
            <QuestionDock
              question={activeQuestion}
              panel={dailyPanel}
              sending={sending}
              onSubmit={(option, extraPrompt) => void sendQuestionAnswer(option, extraPrompt)}
            />
          )}
          <div ref={messageEndRef} />
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
          <div className="chat-config-bar" aria-label="聊天模型快捷配置">
            <select
              value={modelConfig.provider_id}
              onChange={(event) => {
                const nextProvider = selectedProvider(providers, event.target.value);
                const nextModel = nextProvider.model_options?.[0] || nextProvider.model || "";
                void saveQuickModelConfig({
                  ...modelConfig,
                  provider_id: nextProvider.id,
                  base_url: nextProvider.base_url,
                  model: nextModel
                });
              }}
              title="模型供应商"
            >
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>{provider.label}</option>
              ))}
            </select>
            <select
              value={modelConfig.model}
              onChange={(event) => void saveQuickModelConfig({ ...modelConfig, model: event.target.value })}
              title="模型"
            >
              {uniqueModelOptions(selectedProvider(providers, modelConfig.provider_id), modelConfig.model).map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
            <select
              value={modelConfig.thinking_level || "auto"}
              onChange={(event) => void saveQuickModelConfig({ ...modelConfig, thinking_level: event.target.value as ThinkingLevel })}
              title="思考等级"
            >
              {(modelConfig.thinking_level_options || DEFAULT_MODEL_CONFIG.thinking_level_options || []).map((option) => (
                <option key={option.id} value={option.id}>思考：{option.label}</option>
              ))}
            </select>
            <span title="不同模型会自动适配 API 参数或提示词控制">当前：{thinkingLevelLabel(modelConfig)}</span>
          </div>
          <div className="composer">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={sending ? "发送中..." : "输入今日学习内容、答案或任何学习请求"}
              disabled={sending}
              name="langdrill-chat-message"
              autoComplete="off"
              data-lpignore="true"
              data-1p-ignore="true"
              spellCheck={false}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
            />
            <InteractiveButton className={`send-button ${sending ? "sending" : ""}`} onClick={() => void sendMessage()} title="发送">
              {sending ? <span className="spinner" /> : <PaperPlaneRight size={20} weight="fill" />}
            </InteractiveButton>
          </div>
        </div>
      </main>

      <RightWorkbench
        open={rightOpen}
        branchMessages={branchMessages}
        sessionId={activeSessionId}
        onToggle={() => setRightOpen((value) => !value)}
        onSendToChat={(content) => {
          setInput(content);
          setRightOpen(false);
        }}
        onDailyPanelChange={setDailyPanel}
      />

      {settingsOpen && (
        <SettingsDialog
          profile={profile}
          providers={providers}
          modelConfig={modelConfig}
          themeMode={themeMode}
          fontSize={fontSize}
          tokenUsage={tokenUsage}
          sessions={sessions}
          examOptions={examOptions}
          syllabusStatus={syllabusStatus}
          onClose={() => setSettingsOpen(false)}
          onProfileChange={setProfile}
          onSessionsChange={setSessions}
          onSyllabusStatusChange={setSyllabusStatus}
          onModelConfigChange={setModelConfig}
          onAppearanceChange={(nextTheme, nextFontSize) => {
            setThemeMode(nextTheme);
            setFontSize(nextFontSize);
          }}
          onProvidersChange={setProviders}
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
  const knowledgeTotal = panel.knowledge_total || 0;
  const knowledgeDone = panel.knowledge_done || 0;
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
      <div className="word-progress-row">
        <div>
          <strong>{knowledgeDone}/{knowledgeTotal}</strong>
          <span>当日词汇</span>
        </div>
        <div className="thin-progress compact">
          <span style={{ width: `${knowledgeTotal ? (knowledgeDone / knowledgeTotal) * 100 : 8}%` }} />
        </div>
      </div>
      <div className="mini-list">
        {(panel.knowledge_terms?.length ? panel.knowledge_terms : panel.plan.new_content || []).slice(0, 2).map((item) => (
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
          <p>{`${profile.exam_name} · ${profile.target_language}`}</p>
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

function QuestionDock({
  question,
  panel,
  sending,
  onSubmit
}: {
  question: Question;
  panel: DailyPanel;
  sending: boolean;
  onSubmit: (option: string, extraPrompt: string) => void;
}) {
  const [selectedOption, setSelectedOption] = useState("");
  const [extraPrompt, setExtraPrompt] = useState("");
  const total = Math.max(panel.questions_total || 0, question.sequence || 1);
  return (
    <section className="question-dock">
      <div className="question-head">
        <CheckCircle size={18} />
        <span>当前题目：第 {question.sequence || 1} 题 / 共 {total} 题</span>
      </div>
      <p>{cleanQuestionPrompt(question)}</p>
      <div className="options">
        {question.options.map((option, index) => (
          <button
            key={option}
            className={selectedOption === String.fromCharCode(65 + index) ? "selected" : ""}
            onClick={() => setSelectedOption(String.fromCharCode(65 + index))}
          >
            {String.fromCharCode(65 + index)}. {option}
          </button>
        ))}
      </div>
      <div className="question-followup">
        <textarea
          value={extraPrompt}
          onChange={(event) => setExtraPrompt(event.target.value)}
          placeholder="额外提问，可为空。例如：顺便讲一下为什么其他选项不对。"
          name="langdrill-question-followup"
          autoComplete="off"
          data-lpignore="true"
          data-1p-ignore="true"
          spellCheck={false}
        />
        <button
          className="inline-action primary-inline"
          disabled={!selectedOption || sending}
          onClick={() => onSubmit(selectedOption, extraPrompt)}
        >
          提交
        </button>
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
  sessions,
  examOptions,
  syllabusStatus,
  onClose,
  onProfileChange,
  onSessionsChange,
  onSyllabusStatusChange,
  onModelConfigChange,
  onAppearanceChange,
  onProvidersChange,
  onOpenOnboarding
}: {
  profile: Profile;
  providers: ProviderOption[];
  modelConfig: ModelConfig;
  themeMode: ThemeMode;
  fontSize: number;
  tokenUsage: Record<string, number>;
  sessions: SessionItem[];
  examOptions: ExamOption[];
  syllabusStatus: SyllabusStatus;
  onClose: () => void;
  onProfileChange: (profile: Profile) => void;
  onSessionsChange: (sessions: SessionItem[]) => void;
  onSyllabusStatusChange: (status: SyllabusStatus) => void;
  onModelConfigChange: (config: ModelConfig) => void;
  onAppearanceChange: (themeMode: ThemeMode, fontSize: number) => void;
  onProvidersChange: (providers: ProviderOption[]) => void;
  onOpenOnboarding: () => void;
}) {
  const [draft, setDraft] = useState(profile);
  const [modelDraft, setModelDraft] = useState<ModelConfig>({ ...modelConfig, api_key: "" });
  const [customModel, setCustomModel] = useState("");
  const [appearanceDraft, setAppearanceDraft] = useState({ themeMode, fontSize });
  const [reviewIntensity, setReviewIntensity] = useState(3);
  const [saveState, setSaveState] = useState("");
  const [activeSettingsTab, setActiveSettingsTab] = useState("model");
  const [syllabusDraft, setSyllabusDraft] = useState(syllabusStatus);
  const [syllabusMessage, setSyllabusMessage] = useState("");
  const [customExam, setCustomExam] = useState({
    name: "",
    target_language: "",
    syllabus_mode: "auto",
    syllabus_url: "",
    local_path: "",
    notes: ""
  });
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
  const chooseExam = async (examId: string) => {
    const option = examOptions.find((item) => item.id === examId) || examOptions[0];
    if (option.id === "custom") {
      setDraft({
        ...draft,
        exam_id: "custom",
        exam_name: customExam.name || "自定义考试",
        target_language: customExam.target_language || draft.target_language
      });
      return;
    }
    setDraft({
      ...draft,
      exam_id: option.id,
      exam_name: option.name,
      target_language: option.target_language || draft.target_language
    });
    try {
      const status = await apiGet<SyllabusStatus>(`/api/syllabus/status?exam_id=${encodeURIComponent(option.id)}`);
      setSyllabusDraft(status);
      onSyllabusStatusChange(status);
    } catch {
      setSyllabusMessage("考纲状态读取失败，请确认后端已启动。");
    }
  };
  const checkSyllabus = async () => {
    setSyllabusMessage("正在检查官方考纲...");
    try {
      const data = await apiPost<{ changed: boolean; message: string; status: SyllabusStatus }>("/api/syllabus/check", {
        exam_id: draft.exam_id
      });
      setSyllabusDraft(data.status);
      onSyllabusStatusChange(data.status);
      setSyllabusMessage(data.message);
    } catch (err) {
      setSyllabusMessage(err instanceof Error ? err.message : "检查失败");
    }
  };
  const selectSyllabus = async (sourceId: string) => {
    if (!sourceId) return;
    try {
      const status = await apiPost<SyllabusStatus>("/api/syllabus/select", {
        exam_id: draft.exam_id,
        source_id: sourceId
      });
      setSyllabusDraft(status);
      onSyllabusStatusChange(status);
      setSyllabusMessage("已切换考纲版本。");
    } catch (err) {
      setSyllabusMessage(err instanceof Error ? err.message : "切换失败");
    }
  };
  const saveModelConfig = async () => {
    const finalModel = customModel.trim() || modelDraft.model;
    const data = await apiPost<{ model_config: ModelConfig; providers?: ProviderOption[] }>("/api/model-config", {
      ...modelDraft,
      model: finalModel
    });
    onModelConfigChange(data.model_config);
    if (data.providers) {
      onProvidersChange(normalizeProviders(data.providers));
    }
    setSaveState("模型配置已保存。如有自定义 URL/模型将永久应用于此提供商。");
  };
  const saveSettings = async () => {
    // 持久化 profile 到后端
    try {
      const profileData = await apiPost<{ profile: Profile; sessions?: SessionItem[]; syllabus_status?: SyllabusStatus }>("/api/profile", {
        display_name: draft.display_name,
        target_language: draft.target_language,
        exam_id: draft.exam_id,
        exam_name: draft.exam_name,
        learning_goal: draft.learning_goal,
        learning_background: draft.learning_background,
        persona: draft.persona,
        global_user_prompt: draft.global_user_prompt,
      });
      onProfileChange(profileData.profile);
      if (profileData.sessions) onSessionsChange(profileData.sessions);
      if (profileData.syllabus_status) {
        onSyllabusStatusChange(profileData.syllabus_status);
        setSyllabusDraft(profileData.syllabus_status);
      }
    } catch {
      // 后端不可用时仅更新本地
      onProfileChange(draft);
    }
    onAppearanceChange(appearanceDraft.themeMode, appearanceDraft.fontSize);
    try {
      await saveModelConfig();
    } finally {
      onClose();
    }
  };
  const handleAddCustomProvider = async () => {
    const name = window.prompt("请输入新的自定义提供商名称（例如：MyProvider）：");
    if (!name) return;
    try {
      await apiPost("/api/config/providers/custom", { name, base_url: "", default_model: "" });
      const data = await apiGet<{ providers: ProviderOption[] }>("/api/bootstrap");
      onProvidersChange(normalizeProviders(data.providers));
      setSaveState(`提供商 [${name}] 添加成功，请在下拉列表中选择。`);
    } catch (e) {
      setSaveState(`添加失败: ${e instanceof Error ? e.message : e}`);
    }
  };
  const resetDefaults = async () => {
    if (!window.confirm("确认恢复默认设置？模型、个性化、学习目标和自定义提供商会恢复默认，学习会话不会删除。")) return;
    const data = await apiPost<{ profile: Profile; model_config: ModelConfig; providers: ProviderOption[] }>("/api/settings/defaults", {});
    const nextProfile = data.profile;
    const nextModel = normalizeModelConfig(data.model_config);
    const nextProviders = normalizeProviders(data.providers);
    setDraft(nextProfile);
    setModelDraft({ ...nextModel, api_key: "" });
    setCustomModel("");
    setReviewIntensity(3);
    setAppearanceDraft({ themeMode: "system", fontSize: 16 });
    onProfileChange(nextProfile);
    onModelConfigChange(nextModel);
    onProvidersChange(nextProviders);
    onAppearanceChange("system", 16);
    setSaveState("已恢复默认设置。");
  };
  const currentExamOption = examOptions.find((item) => item.id === draft.exam_id) || examOptions[0];
  const tokenMax = Math.max(tokenUsage.total || 0, 1);
  const settingTabs = [
    { id: "model", label: "模型", icon: GearSix },
    { id: "exam", label: "考试", icon: Target },
    { id: "syllabus", label: "考纲", icon: ListBullets },
    { id: "tokens", label: "令牌", icon: Brain },
    { id: "study", label: "学习", icon: ShieldCheck },
    { id: "appearance", label: "外观", icon: Moon }
  ];
  return (
    <div className="modal-backdrop">
      <div className="settings-modal">
        <div className="modal-head">
          <h2>设置</h2>
          <button className="icon-button" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="settings-layout">
          <nav className="settings-tabs" aria-label="设置分类">
            {settingTabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  className={activeSettingsTab === tab.id ? "active" : ""}
                  onClick={() => setActiveSettingsTab(tab.id)}
                >
                  <Icon size={18} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>
          <div className="settings-content">
            {activeSettingsTab === "model" && (
              <SettingSection title="模型提供商">
                <div className="inline-row">
                  <select value={modelDraft.provider_id} onChange={(event) => chooseProvider(event.target.value)}>
                    {providers.map((provider) => (
                      <option key={provider.id} value={provider.id}>{provider.label}</option>
                    ))}
                  </select>
                  <button className="inline-action square-action" onClick={() => void handleAddCustomProvider()} title="新增自定义提供商">+</button>
                </div>
                <input
                  value={modelDraft.base_url}
                  onChange={(event) => setModelDraft({ ...modelDraft, base_url: event.target.value })}
                  placeholder={provider.base_url || "Mock Provider（本地模拟）不需要 Base URL（基础网址）"}
                />
                <input
                  value={modelDraft.api_key || ""}
                  onChange={(event) => setModelDraft({ ...modelDraft, api_key: event.target.value })}
                  placeholder={provider.kind === "mock" ? "Mock Provider（本地模拟）不需要 API Key（接口密钥）" : modelDraft.has_api_key ? "API Key（接口密钥）已配置，留空则不覆盖" : "API Key（接口密钥）"}
                  type="password"
                  autoComplete="off"
                />
                <select value={modelDraft.model} onChange={(event) => setModelDraft({ ...modelDraft, model: event.target.value })}>
                  {modelOptions.map((model) => (
                    <option key={model} value={model}>{model}</option>
                  ))}
                </select>
                <select
                  value={modelDraft.thinking_level || "auto"}
                  onChange={(event) => setModelDraft({ ...modelDraft, thinking_level: event.target.value as ThinkingLevel })}
                >
                  {(modelDraft.thinking_level_options || DEFAULT_MODEL_CONFIG.thinking_level_options || []).map((option) => (
                    <option key={option.id} value={option.id}>思考等级：{option.label}</option>
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
            )}
            {activeSettingsTab === "exam" && (
              <SettingSection title="考试选择">
                <select value={draft.exam_id} onChange={(event) => void chooseExam(event.target.value)}>
                  {examOptions.map((option) => (
                    <option key={option.id} value={option.id}>{option.name}</option>
                  ))}
                </select>
                <p className="hint">{currentExamOption?.description}</p>
                <input value={draft.exam_name} onChange={(event) => setDraft({ ...draft, exam_name: event.target.value })} placeholder="考试名称" />
                <input value={draft.target_language} onChange={(event) => setDraft({ ...draft, target_language: event.target.value })} placeholder="目标语言" />
                {draft.exam_id === "custom" && (
                  <div className="custom-exam-grid">
                    <input value={customExam.name} onChange={(event) => setCustomExam({ ...customExam, name: event.target.value })} placeholder="自定义考试名称" />
                    <input value={customExam.target_language} onChange={(event) => setCustomExam({ ...customExam, target_language: event.target.value })} placeholder="目标语言" />
                    <select value={customExam.syllabus_mode} onChange={(event) => setCustomExam({ ...customExam, syllabus_mode: event.target.value })}>
                      <option value="auto">考纲网址自动下载</option>
                      <option value="manual">手动导入本地文件</option>
                    </select>
                    <input value={customExam.syllabus_url} onChange={(event) => setCustomExam({ ...customExam, syllabus_url: event.target.value })} placeholder="官方考纲网址" />
                    <input value={customExam.local_path} onChange={(event) => setCustomExam({ ...customExam, local_path: event.target.value })} placeholder="本地考纲文件路径" />
                    <textarea value={customExam.notes} onChange={(event) => setCustomExam({ ...customExam, notes: event.target.value })} placeholder="题型、分值、考试时间、评分偏好等补充设置" />
                  </div>
                )}
                <div className="settings-summary-line">当前考试会切换会话列表、题库统计、知识点和考纲选择。</div>
                <div className="settings-summary-line">当前考试会话数：{sessions.length}</div>
              </SettingSection>
            )}
            {activeSettingsTab === "syllabus" && (
              <SettingSection title="考纲管理">
                <div className="syllabus-current">
                  <strong>{syllabusDraft.current_year || "未记录"} 年</strong>
                  <span>{syllabusDraft.current_title || "暂无考纲"}</span>
                </div>
                <div className="inline-row">
                  <button className="inline-action" onClick={() => void checkSyllabus()}>手动检查并更新</button>
                  <a className="inline-link" href={syllabusDraft.official_url} target="_blank" rel="noreferrer">打开官方来源</a>
                </div>
                <select value={syllabusDraft.current_source_id} onChange={(event) => void selectSyllabus(event.target.value)}>
                  {syllabusDraft.sources.map((source) => (
                    <option key={source.id} value={source.id}>{source.year || "未知年份"} - {source.title}</option>
                  ))}
                </select>
                <p className="hint">若官方内容没有变化，会提示已是最新考纲；若发现新年份，会保留旧年份并加入可切换列表。</p>
                {syllabusMessage && <p className="hint strong-hint">{syllabusMessage}</p>}
              </SettingSection>
            )}
            {activeSettingsTab === "tokens" && (
              <SettingSection title="令牌统计">
                <div className="token-dashboard">
                  <div className="token-hero"><strong>{tokenUsage.total}</strong><span>累计 token（令牌）</span></div>
                  {[
                    ["输入", tokenUsage.input],
                    ["输出", tokenUsage.output],
                    ["当前上下文估算", tokenUsage.estimated_current_context]
                  ].map(([label, value]) => (
                    <div className="token-meter" key={label}>
                      <div><span>{label}</span><strong>{value}</strong></div>
                      <div className="thin-progress compact"><span style={{ width: `${Math.max(8, (Number(value) / tokenMax) * 100)}%` }} /></div>
                    </div>
                  ))}
                </div>
              </SettingSection>
            )}
            {activeSettingsTab === "study" && (
              <SettingSection title="学习设置">
                <input value={draft.learning_goal} onChange={(event) => setDraft({ ...draft, learning_goal: event.target.value })} placeholder="目标考试、分数或能力目标" />
                <textarea value={draft.learning_background} onChange={(event) => setDraft({ ...draft, learning_background: event.target.value })} placeholder="当前水平、弱项、已学内容" />
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
                <button className="inline-action" onClick={onOpenOnboarding}>重新打开初始化设置</button>
              </SettingSection>
            )}
            {activeSettingsTab === "appearance" && (
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
            )}
          </div>
        </div>
        <div className="modal-actions">
          <button onClick={() => void resetDefaults()}>恢复默认设置</button>
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
    target_language: "英语",
    exam_id: "cet4",
    exam_name: "大学英语四级",
    learning_goal: "",
    learning_background: "",
    search_years: 3
  });
  const [customModel, setCustomModel] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
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
    setErrorMsg("");
    setIsSubmitting(true);
    try {
      const data = await apiPost<{ profile: Profile }>("/api/initialize", {
        ...draft,
        model: customModel.trim() || draft.model
      });
      onDone(data.profile);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSubmitting(false);
    }
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
        {errorMsg && <div className="error-message" style={{ color: "var(--color-danger, #ff4444)", marginTop: "8px", fontSize: "14px" }}>{errorMsg}</div>}
        <div className="modal-actions">
          <button onClick={onClose} disabled={isSubmitting}>稍后</button>
          <button className="primary" onClick={() => void submit()} disabled={isSubmitting}>
            {isSubmitting ? "保存中..." : "进入日常使用"}
          </button>
        </div>
      </div>
    </div>
  );
}
