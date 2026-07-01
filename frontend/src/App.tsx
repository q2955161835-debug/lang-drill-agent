import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ChangeEvent, type DragEvent, type KeyboardEvent, type MouseEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import {
  ArrowClockwise,
  Brain,
  CaretDown,
  ChatCircleText,
  CheckCircle,
  CircleNotch,
  Database,
  Eye,
  EyeSlash,
  FolderOpen,
  GearSix,
  GitBranch,
  ImageSquare,
  ListBullets,
  Moon,
  PaperPlaneRight,
  PlayCircle,
  Plus,
  ShieldCheck,
  Sidebar,
  Sparkle,
  Sun,
  Target,
  UserCircle,
  X
} from "@phosphor-icons/react";
import { apiDelete, apiGet, apiPost } from "./api";
import { ContextMenu, type ContextMenuItem } from "./components/ContextMenu";
import { appendImportedText, extractTextFromFiles, fileTitle, fileToDataUrl, isImageFile, uploadPastPaperDraftFile, uploadPastPaperFile } from "./fileImport";
import { MarkdownText } from "./components/MarkdownText";
import { RightWorkbench, type WorkbenchTab } from "./components/RightWorkbench";
import type {
  AnsweredQuestion,
  AgentSettingsPermissionsStatus,
  ChatImageAttachment,
  DataPathsStatus,
  DailyPanel,
  ExamOption,
  LearningStats,
  Message,
  MinerUConfig,
  ModelConfig,
  ModelOption,
  PastPaperDraft,
  PastPaperStatus,
  Profile,
  ProviderOption,
  Question,
  ScreenshotImportResult,
  SessionItem,
  SettingsAction,
  SyllabusStatus,
  ThemeMode,
  ThinkingLevel,
  ThinkingLevelOption,
  TokenUsage
} from "./types";

gsap.registerPlugin(useGSAP);

function MessageItem({
  message,
  onContextMenu,
  onConfirmSettingsAction
}: {
  message: Message;
  onContextMenu: (event: MouseEvent, message: Message) => void;
  onConfirmSettingsAction: (action: SettingsAction) => void;
}) {
  const container = useRef<HTMLElement>(null);
  const answeredQuestion = message.payload?.answered_question;
  const settingsAction = message.payload?.settings_action;
  
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
    <article className={`message ${message.role}`} ref={container} onContextMenu={(event) => onContextMenu(event, message)}>
      <div className="avatar">{message.role === "user" ? <UserCircle size={18} /> : <Sparkle size={18} />}</div>
      <div className="message-stack">
        {answeredQuestion && <QuestionReviewCard question={answeredQuestion} />}
        {settingsAction && <SettingsActionCard action={settingsAction} onConfirm={onConfirmSettingsAction} />}
        <div className="bubble"><MarkdownText content={message.content} /></div>
      </div>
    </article>
  );
}

function SettingsActionCard({ action, onConfirm }: { action: SettingsAction; onConfirm: (action: SettingsAction) => void }) {
  const draft = action.draft;
  return (
    <div className="settings-action-card">
      <div>
        <strong>{action.label}</strong>
        <span>{draft.title || "未识别标题"}</span>
      </div>
      <dl>
        <div>
          <dt>年份</dt>
          <dd>{draft.year || "待补充"}</dd>
        </div>
        <div>
          <dt>题型</dt>
          <dd>{draft.question_types?.length ? draft.question_types.join("、") : "待补充"}</dd>
        </div>
        <div>
          <dt>解析</dt>
          <dd>{action.parser || "草稿"}</dd>
        </div>
      </dl>
      <button className="inline-action primary-inline" type="button" onClick={() => onConfirm(action)}>
        确认填入设置
      </button>
    </div>
  );
}

function ThinkingBubble({ label }: { label: string }) {
  return (
    <article className="message assistant thinking-message" aria-live="polite" aria-label={label}>
      <div className="avatar"><Sparkle size={18} /></div>
      <div className="bubble thinking-bubble">
        <span>{label}</span>
        <span className="thinking-dots" aria-hidden="true"><i /> <i /> <i /></span>
      </div>
    </article>
  );
}

function InteractiveButton({ 
  children, 
  className = "", 
  onClick, 
  onPointerDown,
  title 
}: { 
  children: ReactNode; 
  className?: string; 
  onClick?: () => void;
  onPointerDown?: (event: MouseEvent<HTMLButtonElement>) => void;
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
      onPointerDown={onPointerDown}
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


function localDateString(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function hasDailyImportedContent(panel: DailyPanel) {
  return (panel.knowledge_total || 0) > 0
    || panel.questions_total > 0
    || panel.questions_done > 0
    || (panel.knowledge_terms?.length || 0) > 0;
}

const DEFAULT_PANEL: DailyPanel = {
  date: localDateString(),
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
  deadline: null,
  learning_goal: "",
  learning_background: "",
  persona: "professional",
  global_user_prompt: ""
};

const FALLBACK_PROVIDERS: ProviderOption[] = [
  { id: "openai", label: "OpenAI GPT", kind: "openai-compatible", api_format: "openai-chat-completions", api_key_required: true, enabled: true, has_api_key: false, visible_in_picker: false, base_url: "https://api.openai.com/v1", model: "gpt-5.5", model_options: [{ id: "gpt-5.5", label: "gpt-5.5", vision: true }, { id: "gpt-5.4", label: "gpt-5.4", vision: true }] },
  { id: "claude", label: "Claude", kind: "anthropic", api_format: "anthropic-messages", api_key_required: true, enabled: true, has_api_key: false, visible_in_picker: false, base_url: "https://api.anthropic.com", model: "claude-sonnet-4.7", model_options: [{ id: "claude-sonnet-4.7", label: "claude-sonnet-4.7", vision: true }, { id: "claude-opus-4.7", label: "claude-opus-4.7", vision: true }] },
  { id: "deepseek", label: "DeepSeek", kind: "openai-compatible", api_format: "openai-chat-completions", api_key_required: true, enabled: true, has_api_key: false, visible_in_picker: false, base_url: "https://api.deepseek.com", model: "deepseek-v4-pro", model_options: [{ id: "deepseek-v4-pro", label: "deepseek-v4-pro", vision: false }, { id: "deepseek-v4-flash", label: "deepseek-v4-flash", vision: false }] },
  { id: "mimo", label: "Xiaomi MiMo", kind: "anthropic", api_format: "anthropic-messages", api_key_required: true, enabled: true, has_api_key: false, visible_in_picker: false, base_url: "https://api.xiaomimimo.com/anthropic", model: "mimo-v2.5-pro", model_options: [{ id: "mimo-v2.5", label: "mimo-v2.5", vision: false }, { id: "mimo-v2.5-pro", label: "mimo-v2.5-pro", vision: false }] },
  { id: "mock", label: "Mock Provider", kind: "mock", api_format: "mock", api_key_required: false, enabled: true, has_api_key: false, visible_in_picker: false, base_url: "", model: "mock-tutor-v1", model_options: [{ id: "mock-tutor-v1", label: "mock-tutor-v1", vision: false }] }
];

const DEFAULT_MODEL_CONFIG: ModelConfig = {
  provider_id: "mimo",
  base_url: "https://api.xiaomimimo.com/anthropic",
  model: "mimo-v2.5-pro",
  thinking_level: "enabled",
  thinking_level_options: [
    { id: "off", label: "关闭", api_value: "" },
    { id: "enabled", label: "开启", api_value: "enabled" }
  ],
  api_format: "anthropic-messages",
  vision: false,
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
    id: "cet6",
    name: "英语六级",
    target_language: "英语",
    official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
    default_year: 2016,
    description: "大学英语六级，按六级题型和难度组织。"
  },
  {
    id: "cft4",
    name: "法语四级",
    target_language: "法语",
    official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
    default_year: 2023,
    description: "大学法语四级，官方 2023 版考纲。"
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
    id: "cjt6",
    name: "日语六级",
    target_language: "日语",
    official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
    default_year: 2024,
    description: "大学日语六级，按更高难度日语题型和表达能力组织。"
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

const DEFAULT_PAST_PAPER_STATUS: PastPaperStatus = {
  exam_id: "cet4",
  description: "CET-4（大学英语四级）真题按听力、阅读、翻译和写作组织。",
  source_website: "https://cet.neea.edu.cn/",
  papers: [],
  selected_paper_ids: [],
  current_papers: [],
  question_types: [
    { id: "listening", label: "听力理解", description: "短篇新闻、长对话和听力篇章。" },
    { id: "reading", label: "阅读理解", description: "选词填空、长篇匹配和仔细阅读。" },
    { id: "translation", label: "汉译英翻译", description: "段落翻译，偏中国文化与社会话题。" },
    { id: "writing", label: "短文写作", description: "议论文、应用文或图表类写作。" },
    { id: "context_vocabulary", label: "语境词汇", description: "从真题语境抽取搭配、词义和近义辨析。" }
  ],
  enabled_question_type_ids: ["listening", "reading", "translation", "writing", "context_vocabulary"]
};

const DEFAULT_LEARNING_STATS: LearningStats = {
  exam_id: "cet4",
  exam_name: "大学英语四级",
  questions_done: 0,
  questions_total: 0,
  words_mastered: 0,
  words_total: 0,
  accuracy: 0,
  attempts_total: 0,
  attempts_correct: 0
};

const DRAFT_SESSION_ID = "__draft_new_chat__";
const DEFAULT_CONTEXT_LIMIT = 1_000_000;
const DEFAULT_TOKEN_USAGE: TokenUsage = {
  input: 0,
  output: 0,
  total: 0,
  total_calls: 0,
  average_tokens_per_call: 0,
  average_latency_ms: 0,
  estimated_current_context: 0,
  context_limit: DEFAULT_CONTEXT_LIMIT,
  context_percent: 0,
  context_messages: 0,
  compressed_context_tokens: 0,
  sessions_total: 0,
  messages_total: 0,
  active_days: 0,
  current_streak_days: 0,
  most_used_model: "",
  most_used_model_percent: 0,
  today: { input: 0, output: 0, total: 0, calls: 0 },
  yesterday: { input: 0, output: 0, total: 0, calls: 0 },
  last_7_days: { input: 0, output: 0, total: 0, calls: 0 },
  last_30_days: { input: 0, output: 0, total: 0, calls: 0 },
  current_month: { input: 0, output: 0, total: 0, calls: 0 },
  model_breakdown: [],
  provider_breakdown: [],
  task_breakdown: [],
  daily_activity: [],
  recent_calls: []
};

const API_FORMAT_OPTIONS = [
  { id: "anthropic-messages", label: "Anthropic Messages (/v1/messages)" },
  { id: "openai-chat-completions", label: "Chat Completions (/chat/completions)" },
  { id: "openai-responses", label: "Responses (/responses)", disabled: true, note: "预留，当前调用层暂未启用" }
];

const DEFAULT_DATA_PATHS: DataPathsStatus = {
  user_data_dir: "",
  question_database_dir: "",
  db_path: "",
  log_dir: "",
  project_data_dir: "",
  test_data_dir: "",
  db_exists: false,
  db_size: 0,
  counts: {
    study_sessions: 0,
    messages: 0,
    questions: 0,
    attempts: 0,
    knowledge_items: 0,
    branch_conversations: 0,
    branch_messages: 0,
    model_calls: 0,
    syllabus_sources: 0,
    exam_assets: 0
  }
};

const DEFAULT_MINERU_CONFIG: MinerUConfig = {
  token_url: "https://mineru.net/apiManage/token",
  docs_url: "https://mineru.net/apiManage/docs",
  env_key: "MINERU_TOKEN",
  has_token: false,
  token_preview: ""
};

const DEFAULT_AGENT_PERMISSIONS: AgentSettingsPermissionsStatus = {
  enabled_feature_ids: [],
  features: [
    {
      id: "past_paper_import",
      label: "历年真题导入与题型",
      description: "允许会话 Agent 解析试卷信息，并在用户确认后填入真题导入表单。",
      enabled: false
    },
    {
      id: "profile_exam",
      label: "考试与学习目标",
      description: "允许会话 Agent 按用户确认的目标调整考试、截止时间和学习背景草稿。",
      enabled: false
    },
    {
      id: "model_config",
      label: "模型供应商与默认模型",
      description: "允许会话 Agent 帮助填写模型供应商、模型名、Base URL（基础网址）和能力开关。",
      enabled: false,
      sensitive: true
    },
    {
      id: "context_settings",
      label: "上下文容量",
      description: "允许会话 Agent 帮助调整上下文容量上限和压缩相关设置。",
      enabled: false
    },
    {
      id: "data_paths",
      label: "题目数据库目录",
      description: "允许会话 Agent 帮助填写题目数据库目录迁移设置；迁移前仍需用户确认。",
      enabled: false,
      sensitive: true
    },
    {
      id: "mineru_config",
      label: "MinerU token",
      description: "允许会话 Agent 帮助打开 MinerU 配置项；token 明文仍只能由用户输入。",
      enabled: false,
      sensitive: true
    }
  ]
};

const PANEL_SIZE_STORAGE_KEY = "langdrill.panelSizes";
const PANEL_SIZE_LIMITS = {
  leftDefault: 320,
  leftMin: 240,
  leftMax: 520,
  leftClosed: 72,
  rightDefault: 390,
  rightMin: 320,
  rightMax: 640,
  rightClosed: 58,
  centerMin: 520,
  keyboardStep: 16,
  keyboardLargeStep: 32
};

type PanelSizes = {
  left: number;
  right: number;
};

type ResizablePanel = "left" | "right";

type PanelResizeSnapshot = {
  panel: ResizablePanel;
  startX: number;
  startLeft: number;
  startRight: number;
};

const DEFAULT_PANEL_SIZES: PanelSizes = {
  left: PANEL_SIZE_LIMITS.leftDefault,
  right: PANEL_SIZE_LIMITS.rightDefault
};

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function validPanelSize(value: unknown, fallback: number, min: number, max: number) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? clamp(numeric, min, max) : fallback;
}

function loadPanelSizes(): PanelSizes {
  try {
    const saved = localStorage.getItem(PANEL_SIZE_STORAGE_KEY);
    if (!saved) return DEFAULT_PANEL_SIZES;
    const parsed = JSON.parse(saved) as Partial<PanelSizes>;
    return {
      left: validPanelSize(parsed.left, PANEL_SIZE_LIMITS.leftDefault, PANEL_SIZE_LIMITS.leftMin, PANEL_SIZE_LIMITS.leftMax),
      right: validPanelSize(parsed.right, PANEL_SIZE_LIMITS.rightDefault, PANEL_SIZE_LIMITS.rightMin, PANEL_SIZE_LIMITS.rightMax)
    };
  } catch {
    return DEFAULT_PANEL_SIZES;
  }
}

function clampLeftPanelWidth(width: number, rightWidth: number, rightOpen: boolean, viewportWidth: number) {
  const occupiedRightWidth = rightOpen ? rightWidth : PANEL_SIZE_LIMITS.rightClosed;
  const maxByViewport = viewportWidth - occupiedRightWidth - PANEL_SIZE_LIMITS.centerMin;
  const maxWidth = Math.max(PANEL_SIZE_LIMITS.leftMin, Math.min(PANEL_SIZE_LIMITS.leftMax, maxByViewport));
  return clamp(width, PANEL_SIZE_LIMITS.leftMin, maxWidth);
}

function clampRightPanelWidth(width: number, leftWidth: number, leftOpen: boolean, viewportWidth: number) {
  const occupiedLeftWidth = leftOpen ? leftWidth : PANEL_SIZE_LIMITS.leftClosed;
  const maxByViewport = viewportWidth - occupiedLeftWidth - PANEL_SIZE_LIMITS.centerMin;
  const maxWidth = Math.max(PANEL_SIZE_LIMITS.rightMin, Math.min(PANEL_SIZE_LIMITS.rightMax, maxByViewport));
  return clamp(width, PANEL_SIZE_LIMITS.rightMin, maxWidth);
}

function clampPanelSizes(sizes: PanelSizes, leftOpen: boolean, rightOpen: boolean, viewportWidth: number) {
  const left = clampLeftPanelWidth(sizes.left, sizes.right, rightOpen, viewportWidth);
  const right = clampRightPanelWidth(sizes.right, left, leftOpen, viewportWidth);
  return { left, right };
}

function isOptionAnswer(content: string) {
  return /^(?:选择?\s*)?[A-D]$/i.test(content.trim()) || /^答案是\s*[A-D]$/i.test(content.trim());
}

const VOCAB_TERM_RE = /^[A-Za-z][A-Za-z'-]{1,40}$/;
const VOCAB_MEANING_RE = /[\u4e00-\u9fff]|^(?:n|v|vi|vt|adj|adv|prep|conj|pron|num|art|aux)\./i;
const VOCAB_INLINE_POS_RE = /^[A-Za-z][A-Za-z'-]{1,40}\s+(?:n|v|vi|vt|adj|adv|prep|conj|pron|num|art|aux)\..+/i;
const VOCAB_INLINE_SEPARATOR_RE = /^[A-Za-z][A-Za-z'-]{1,40}\s*[:：]\s*.+/;

function looksLikeScreenshotVocabulary(content: string) {
  const lines = content.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  let terms = 0;
  for (let index = 0; index < lines.length; index += 1) {
    if (VOCAB_INLINE_POS_RE.test(lines[index]) || (VOCAB_INLINE_SEPARATOR_RE.test(lines[index]) && VOCAB_MEANING_RE.test(lines[index]))) {
      terms += 1;
      continue;
    }
    if (VOCAB_TERM_RE.test(lines[index]) && lines[index + 1] && VOCAB_MEANING_RE.test(lines[index + 1])) {
      terms += 1;
    }
  }
  return terms >= 3;
}

const CHAT_ADVICE_RE = /怎么|如何|为什么|为啥|吗|？|\?|是不是|建议|推荐|计划|规划|应该/;
const FORCE_DRILL_RE = /(?:出题|出.{0,16}题|生成题|生成.{0,16}题|刷题|做题|练题|考我|测验|小测)|(?:quiz|drill|practice|test me)/i;
const DRILL_ACTION_RE = /(?:出题|出.{0,16}题|生成题|生成.{0,16}题)|(?:给我|帮我|请|来|开始|现在|我要|我想)?.{0,8}(?:刷题|做题|练题|练(?:习|单词|词汇|听力|阅读|写作)?|考我|测验|小测|训练)|(?:quiz|drill|practice|test me)/i;
const START_LEARNING_RE = /(?:今天|今日|现在|开始|我要|我想).{0,12}(?:学习|复习|背单词|练习|练|训练|刷题)/i;

function looksLikePracticeRequest(content: string) {
  const text = content.trim();
  if (!text) return false;
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (lines.some((line) => VOCAB_INLINE_POS_RE.test(line) || VOCAB_INLINE_SEPARATOR_RE.test(line))) {
    return true;
  }
  if (CHAT_ADVICE_RE.test(text) && !FORCE_DRILL_RE.test(text)) return false;
  if (DRILL_ACTION_RE.test(text)) return true;
  return START_LEARNING_RE.test(text);
}

function formatNumber(value: number | undefined) {
  return Math.round(value || 0).toLocaleString("zh-CN");
}

function formatCompactNumber(value: number | undefined) {
  const amount = value || 0;
  if (amount >= 100_000_000) return `${(amount / 100_000_000).toFixed(1)}亿`;
  if (amount >= 10_000) return `${(amount / 10_000).toFixed(1)}万`;
  return formatNumber(amount);
}

function contextPercentFromUsage(tokenUsage: TokenUsage) {
  const limit = tokenUsage.context_limit || DEFAULT_CONTEXT_LIMIT;
  const current = tokenUsage.estimated_current_context || 0;
  const reportedPercent = tokenUsage.context_percent;
  const ratio = typeof reportedPercent === "number" && Number.isFinite(reportedPercent)
    ? reportedPercent > 1
      ? reportedPercent / 100
      : reportedPercent
    : limit > 0
      ? current / limit
      : 0;
  return Math.max(0, Math.min(100, Math.round((Number.isFinite(ratio) ? ratio : 0) * 100)));
}

function formatBytes(value: number | undefined) {
  const amount = value || 0;
  if (amount >= 1024 * 1024) return `${(amount / 1024 / 1024).toFixed(1)} MB`;
  if (amount >= 1024) return `${(amount / 1024).toFixed(1)} KB`;
  return `${amount} B`;
}

function cleanQuestionPrompt(question: Question) {
  return question.prompt.replace(/^第\s*\d+\s*题\s*\/\s*共\s*\d+\s*题\s*\n?/, "").trim();
}

function optionLetter(index: number) {
  return String.fromCharCode(65 + index);
}

function selectedLetterForQuestion(question: AnsweredQuestion) {
  const directLetter = (question.selected_option || "").trim().toUpperCase();
  if (/^[A-D]$/.test(directLetter)) return directLetter;
  const answerText = (question.selected_answer || "").trim();
  if (!answerText) return "";
  const index = question.options.findIndex((option) => option.trim() === answerText);
  return index >= 0 ? optionLetter(index) : "";
}

function correctLetterForQuestion(question: Question) {
  const directLetter = (question.answer?.letter || "").trim().toUpperCase();
  if (/^[A-D]$/.test(directLetter)) return directLetter;
  const correctText = (question.answer?.correct || "").trim();
  if (!correctText) return "";
  const index = question.options.findIndex((option) => option.trim() === correctText);
  return index >= 0 ? optionLetter(index) : "";
}

function toDateTimeLocalValue(value?: string | null) {
  if (!value) return "";
  const normalized = value.length >= 16 ? value.slice(0, 16) : value;
  return normalized;
}

function countdownText(value?: string | null) {
  if (!value) return "未设置";
  const deadline = new Date(value);
  if (Number.isNaN(deadline.getTime())) return "时间格式异常";
  const diff = deadline.getTime() - Date.now();
  if (diff <= 0) return "考试时间已到";
  const minutes = Math.floor(diff / 60000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const restMinutes = minutes % 60;
  if (days > 0) return `${days} 天 ${hours} 小时`;
  if (hours > 0) return `${hours} 小时 ${restMinutes} 分钟`;
  return `${Math.max(restMinutes, 1)} 分钟`;
}

function selectedProvider(providers: ProviderOption[], providerId: string) {
  return providers.find((item) => item.id === providerId)
    || FALLBACK_PROVIDERS.find((item) => item.id === providerId)
    || providers[0]
    || FALLBACK_PROVIDERS[0];
}

function modelOptionLabel(option: ModelOption) {
  return typeof option === "string" ? option : option.label || option.id;
}

function normalizedModelOption(option: ModelOption): Exclude<ModelOption, string> {
  if (typeof option === "string") {
    return { id: option, label: option, vision: false, visible: true };
  }
  return { ...option, vision: Boolean(option.vision), visible: option.visible !== false };
}

function modelOptionsFor(provider: ProviderOption, currentModel: string, optionsConfig: { visibleOnly?: boolean } = {}) {
  const allOptions = [...(provider.model_options || [])].map(normalizedModelOption);
  const options = optionsConfig.visibleOnly
    ? allOptions.filter((option) => option.visible !== false || option.id === currentModel)
    : allOptions;
  const seen = new Set(options.map((option) => option.id));
  for (const model of [provider.model, currentModel]) {
    if (model && !seen.has(model)) {
      const known = allOptions.find((option) => option.id === model);
      if (!optionsConfig.visibleOnly || known?.visible !== false || model === currentModel) {
        options.push(known || { id: model, label: model, visible: true });
      }
      seen.add(model);
    }
  }
  return options;
}

function thinkingOptionsForModel(provider: ProviderOption, modelId: string) {
  const model = modelOptionsFor(provider, modelId).find((option) => option.id === modelId);
  return model?.reasoning?.levels || [];
}

function defaultThinkingLevelForModel(provider: ProviderOption, modelId: string) {
  const model = modelOptionsFor(provider, modelId).find((option) => option.id === modelId);
  return model?.reasoning?.default_level || model?.reasoning?.levels?.[0]?.id || "";
}

function defaultThinkingLevelFromOptions(options: ThinkingLevelOption[], fallback = "") {
  if (!options.length) return "";
  if (fallback && options.some((option) => option.id === fallback)) return fallback;
  return options[0]?.id || "";
}

function thinkingLevelForOptions(options: ThinkingLevelOption[], value: string | undefined, fallback = "") {
  if (!options.length) return "";
  if (value && options.some((option) => option.id === value)) return value;
  return defaultThinkingLevelFromOptions(options, fallback);
}

function modelThinkingSelection(provider: ProviderOption, modelId: string, value: string | undefined) {
  const options = thinkingOptionsForModel(provider, modelId);
  return {
    options,
    level: thinkingLevelForOptions(options, value, defaultThinkingLevelForModel(provider, modelId))
  };
}

function slugifyThinkingLevelId(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_\-\u4e00-\u9fa5]/g, "");
}

function modelSupportsVision(provider: ProviderOption, modelId: string) {
  const model = modelOptionsFor(provider, modelId).find((option) => option.id === modelId);
  return Boolean(model?.vision);
}

function pickerProviders(providers: ProviderOption[], currentProviderId = "") {
  const visible = providers.filter((provider) => provider.visible_in_picker && provider.id !== "mock");
  const current = providers.find((provider) => provider.id === currentProviderId && provider.id !== "mock");
  if (current && !visible.some((provider) => provider.id === current.id)) {
    return [current, ...visible];
  }
  if (visible.length) return visible;
  if (current) return [current];
  const defaultReal = providers.find((provider) => provider.id === DEFAULT_MODEL_CONFIG.provider_id)
    || providers.find((provider) => provider.id !== "mock");
  return defaultReal ? [defaultReal] : providers.filter((provider) => provider.id !== "mock");
}

function normalizeProviders(providers: ProviderOption[] | undefined) {
  if (!providers?.length) return FALLBACK_PROVIDERS;
  const normalized: ProviderOption[] = providers.map((provider) => ({
    ...(FALLBACK_PROVIDERS.find((item) => item.id === provider.id) || {}),
    ...provider,
    base_url: provider.base_url || FALLBACK_PROVIDERS.find((item) => item.id === provider.id)?.base_url || "",
    model: provider.model || FALLBACK_PROVIDERS.find((item) => item.id === provider.id)?.model || "",
    model_options: provider.model_options?.length
      ? provider.model_options
      : FALLBACK_PROVIDERS.find((item) => item.id === provider.id)?.model_options || [provider.model].filter(Boolean),
    enabled: provider.enabled ?? true,
    has_api_key: provider.has_api_key ?? false,
    visible_in_picker: provider.id !== "mock" && Boolean(provider.visible_in_picker)
  }));
  if (!normalized.some((provider) => provider.id === "mock")) {
    normalized.push(FALLBACK_PROVIDERS.find((provider) => provider.id === "mock") as ProviderOption);
  }
  return normalized;
}

function normalizeModelConfig(config: ModelConfig | undefined) {
  if (!config || config.provider_id === "mock") return DEFAULT_MODEL_CONFIG;
  return {
    ...DEFAULT_MODEL_CONFIG,
    ...config,
    thinking_level: (config.thinking_level || "") as ThinkingLevel,
    thinking_level_options: config.thinking_level_options || [],
    vision: Boolean(config.vision)
  };
}

const personalityOptions = [
  { id: "none", label: "不使用人格", prompt: "不额外注入人格提示词，只按系统学习流程回复。" },
  { id: "warm", label: "热情开朗", prompt: "反馈积极，语气明亮，不夸张。" },
  { id: "professional", label: "专业可靠", prompt: "语气克制，结论清晰，建议具体可执行，适合日常正式学习。" },
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
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const selectedTextRef = useRef("");
  const [profile, setProfile] = useState<Profile>(MOCK_PROFILE);
  const [providers, setProviders] = useState<ProviderOption[]>(FALLBACK_PROVIDERS);
  const [modelConfig, setModelConfig] = useState<ModelConfig>(DEFAULT_MODEL_CONFIG);
  const [examOptions, setExamOptions] = useState<ExamOption[]>(DEFAULT_EXAM_OPTIONS);
  const [syllabusStatus, setSyllabusStatus] = useState<SyllabusStatus>(DEFAULT_SYLLABUS_STATUS);
  const [pastPaperStatus, setPastPaperStatus] = useState<PastPaperStatus>(DEFAULT_PAST_PAPER_STATUS);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [dailyPanel, setDailyPanel] = useState<DailyPanel>(DEFAULT_PANEL);
  const [learningStats, setLearningStats] = useState<LearningStats>(DEFAULT_LEARNING_STATS);
  const [activeQuestion, setActiveQuestion] = useState<Question | null>(null);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage>(DEFAULT_TOKEN_USAGE);
  const [dataPaths, setDataPaths] = useState<DataPathsStatus>(DEFAULT_DATA_PATHS);
  const [mineruConfig, setMineruConfig] = useState<MinerUConfig>(DEFAULT_MINERU_CONFIG);
  const [agentPermissions, setAgentPermissions] = useState<AgentSettingsPermissionsStatus>(DEFAULT_AGENT_PERMISSIONS);
  const [pendingPaperDraft, setPendingPaperDraft] = useState<PastPaperDraft | null>(null);
  const [input, setInput] = useState("");
  const [composerAttachments, setComposerAttachments] = useState<ChatImageAttachment[]>([]);
  const [composerDragActive, setComposerDragActive] = useState(false);
  const [composerFileStatus, setComposerFileStatus] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("模型正在思考");
  const [quickStartHint, setQuickStartHint] = useState("");
  const [compressingContext, setCompressingContext] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [pendingNewSession, setPendingNewSession] = useState(false);
  const [leftOpen, setLeftOpen] = useState(() => localStorage.getItem("leftOpen") !== "false");
  const [rightOpen, setRightOpen] = useState(false);
  const [panelSizes, setPanelSizes] = useState<PanelSizes>(() => loadPanelSizes());
  const panelSizesRef = useRef(panelSizes);
  const pendingPanelSizesRef = useRef(panelSizes);
  const resizeSnapshotRef = useRef<PanelResizeSnapshot | null>(null);
  const [resizingPanel, setResizingPanel] = useState<ResizablePanel | null>(null);
  const [workbenchTab, setWorkbenchTab] = useState<WorkbenchTab>("branch");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => (localStorage.getItem("themeMode") as ThemeMode | null) || "system");
  const [fontSize, setFontSize] = useState(() => Number(localStorage.getItem("fontSize") || 16));
  const [expandedDates, setExpandedDates] = useState<Record<string, boolean>>(() => {
    const saved = localStorage.getItem("expandedDates");
    return saved ? JSON.parse(saved) : { [localDateString()]: true };
  });
  const [selectedText, setSelectedText] = useState("");
  const [branchId, setBranchId] = useState<string | null>(null);
  const [branchMessages, setBranchMessages] = useState<Message[]>([]);
  const [branchSending, setBranchSending] = useState(false);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    items: ContextMenuItem[];
  } | null>(null);

  const displaySessions = useMemo(() => {
    if (!pendingNewSession) return sessions;
    const today = localDateString();
    const draftSession: SessionItem = {
      id: DRAFT_SESSION_ID,
      title: "新聊天",
      folder_date: today,
      exam_id: profile.exam_id,
      status: "draft",
      draft: true
    };
    return [draftSession, ...sessions.filter((session) => session.id !== DRAFT_SESSION_ID)];
  }, [pendingNewSession, profile.exam_id, sessions]);
  const sessionsByDate = useMemo(() => groupSessions(displaySessions), [displaySessions]);
  const emptyContext = messages.length === 0;
  const quickProviders = pickerProviders(providers, modelConfig.provider_id);
  const quickProviderId = quickProviders.some((provider) => provider.id === modelConfig.provider_id)
    ? modelConfig.provider_id
    : quickProviders[0]?.id || modelConfig.provider_id;
  const quickProvider = selectedProvider(quickProviders, quickProviderId);
  const quickCurrentModel = quickProvider.id === modelConfig.provider_id ? modelConfig.model : quickProvider.model;
  const quickModelOptions = modelOptionsFor(quickProvider, quickCurrentModel, { visibleOnly: true });
  const quickThinkingSelection = modelThinkingSelection(
    quickProvider,
    quickCurrentModel,
    quickProvider.id === modelConfig.provider_id ? modelConfig.thinking_level : undefined
  );
  const quickThinkingOptions = quickThinkingSelection.options;
  const quickThinkingLevel = quickThinkingSelection.level;
  const currentModelVision = quickProvider.id === modelConfig.provider_id && quickCurrentModel === modelConfig.model
    ? Boolean(modelConfig.vision)
    : modelSupportsVision(quickProvider, quickCurrentModel);
  const appShellStyle = {
    "--left-rail-width": `${panelSizes.left}px`,
    "--right-rail-width": `${panelSizes.right}px`
  } as CSSProperties;

  const applyPanelSizeVars = useCallback((sizes: PanelSizes) => {
    const node = appRef.current;
    if (!node) return;
    node.style.setProperty("--left-rail-width", `${sizes.left}px`);
    node.style.setProperty("--right-rail-width", `${sizes.right}px`);
  }, []);

  const resizePanelWithKeyboard = useCallback((panel: ResizablePanel, event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const step = event.shiftKey ? PANEL_SIZE_LIMITS.keyboardLargeStep : PANEL_SIZE_LIMITS.keyboardStep;
    const direction = panel === "left"
      ? (event.key === "ArrowRight" ? 1 : -1)
      : (event.key === "ArrowLeft" ? 1 : -1);

    setPanelSizes((current) => {
      const viewportWidth = window.innerWidth;
      const next = panel === "left"
        ? {
            ...current,
            left: clampLeftPanelWidth(current.left + direction * step, current.right, rightOpen, viewportWidth)
          }
        : {
            ...current,
            right: clampRightPanelWidth(current.right + direction * step, current.left, leftOpen, viewportWidth)
          };
      panelSizesRef.current = next;
      pendingPanelSizesRef.current = next;
      applyPanelSizeVars(next);
      return next;
    });
  }, [applyPanelSizeVars, leftOpen, rightOpen]);

  const startPanelResize = useCallback((panel: ResizablePanel, event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const snapshot: PanelResizeSnapshot = {
      panel,
      startX: event.clientX,
      startLeft: panelSizesRef.current.left,
      startRight: panelSizesRef.current.right
    };
    resizeSnapshotRef.current = snapshot;
    pendingPanelSizesRef.current = { left: snapshot.startLeft, right: snapshot.startRight };
    setResizingPanel(panel);
    document.body.classList.add("panel-resize-active");
    event.currentTarget.setPointerCapture?.(event.pointerId);

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const currentSnapshot = resizeSnapshotRef.current;
      if (!currentSnapshot) return;
      const viewportWidth = window.innerWidth;
      const deltaX = moveEvent.clientX - currentSnapshot.startX;
      const next = currentSnapshot.panel === "left"
        ? {
            left: clampLeftPanelWidth(currentSnapshot.startLeft + deltaX, currentSnapshot.startRight, rightOpen, viewportWidth),
            right: currentSnapshot.startRight
          }
        : {
            left: currentSnapshot.startLeft,
            right: clampRightPanelWidth(currentSnapshot.startRight - deltaX, currentSnapshot.startLeft, leftOpen, viewportWidth)
          };
      pendingPanelSizesRef.current = next;
      applyPanelSizeVars(next);
    };

    const stopResize = () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
      document.body.classList.remove("panel-resize-active");
      resizeSnapshotRef.current = null;
      setResizingPanel(null);
      setPanelSizes((current) => {
        const finalSizes = clampPanelSizes(pendingPanelSizesRef.current || current, leftOpen, rightOpen, window.innerWidth);
        panelSizesRef.current = finalSizes;
        pendingPanelSizesRef.current = finalSizes;
        applyPanelSizeVars(finalSizes);
        return finalSizes;
      });
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  }, [applyPanelSizeVars, leftOpen, rightOpen]);

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
      
      gsap.from(".learning-stat-card", {
        scale: 0.92,
        y: 14,
        duration: 0.45,
        ease: "back.out(1.4)",
        stagger: 0.04,
        delay: 0.2,
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
    panelSizesRef.current = panelSizes;
    pendingPanelSizesRef.current = panelSizes;
    applyPanelSizeVars(panelSizes);
    localStorage.setItem(PANEL_SIZE_STORAGE_KEY, JSON.stringify(panelSizes));
  }, [applyPanelSizeVars, panelSizes]);

  useEffect(() => {
    const handleResize = () => {
      setPanelSizes((current) => {
        const next = clampPanelSizes(current, leftOpen, rightOpen, window.innerWidth);
        panelSizesRef.current = next;
        pendingPanelSizesRef.current = next;
        applyPanelSizeVars(next);
        return next;
      });
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [applyPanelSizeVars, leftOpen, rightOpen]);

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
      token_usage: TokenUsage;
      data_paths?: DataPathsStatus;
      mineru_config?: MinerUConfig;
      learning_stats?: LearningStats;
      providers: ProviderOption[];
      model_config: ModelConfig;
      exam_options?: ExamOption[];
      syllabus_status?: SyllabusStatus;
      past_paper_status?: PastPaperStatus;
      agent_permissions?: AgentSettingsPermissionsStatus;
    }>("/api/bootstrap")
      .then((data) => {
        setProfile(data.profile);
        setProviders(normalizeProviders(data.providers));
        setModelConfig(normalizeModelConfig(data.model_config));
        setExamOptions(data.exam_options?.length ? data.exam_options : DEFAULT_EXAM_OPTIONS);
        setSyllabusStatus(data.syllabus_status || DEFAULT_SYLLABUS_STATUS);
        setPastPaperStatus(data.past_paper_status || DEFAULT_PAST_PAPER_STATUS);
        setSessions(data.sessions);
        setTokenUsage({ ...DEFAULT_TOKEN_USAGE, ...data.token_usage });
        setDataPaths(data.data_paths || DEFAULT_DATA_PATHS);
        setMineruConfig({ ...DEFAULT_MINERU_CONFIG, ...data.mineru_config });
        setAgentPermissions(data.agent_permissions || DEFAULT_AGENT_PERMISSIONS);
        setLearningStats(data.learning_stats || DEFAULT_LEARNING_STATS);
        setOnboardingOpen(data.profile.exam_id === "unassigned");
      })
      .catch(() => setOnboardingOpen(true));
  }, []);

  const postChatContent = useCallback(async (
    content: string,
    forceNewSession = pendingNewSession,
    attachments: ChatImageAttachment[] = []
  ) => {
    const cleanContent = content.trim();
    if ((!cleanContent && !attachments.length) || sending) return;
    setQuickStartHint("");
    const likelyScreenshot = looksLikeScreenshotVocabulary(cleanContent);
    const likelyPractice = looksLikePracticeRequest(cleanContent);
    const nextLabel = likelyScreenshot
      ? "截图解析中"
      : attachments.length
        ? "模型正在识别图片"
      : activeQuestion && isOptionAnswer(cleanContent)
        ? "模型正在判题"
        : likelyPractice ? "题目生成中" : "模型正在思考";
    setLoadingLabel(nextLabel);
    const generationTimer = likelyScreenshot
      ? window.setTimeout(() => setLoadingLabel("题目生成中"), 900)
      : undefined;
    const attachmentLine = attachments.length
      ? `\n\n[图片附件：${attachments.map((item) => item.filename || "图片").join("、")}]`
      : "";
    const userMessage: Message = {
      id: `local-${Date.now()}`,
      role: "user",
      content: `${cleanContent || "图片输入"}${attachmentLine}`
    };
    setMessages((current) => [...current, userMessage]);
    if (activeQuestion && isOptionAnswer(cleanContent)) {
      setActiveQuestion(null);
    }
    setSending(true);
    try {
      const data = await apiPost<{
        session_id: string;
        message: Message;
        daily_panel: DailyPanel;
        active_question: Question | null;
        token_usage: TokenUsage;
        learning_stats?: LearningStats;
      }>("/api/chat", {
        content: cleanContent,
        session_id: activeSessionId,
        force_new_session: forceNewSession,
        attachments
      });
      setActiveSessionId(data.session_id);
      setPendingNewSession(false);
      setMessages((current) => [...current, data.message]);
      setDailyPanel(data.daily_panel);
      setActiveQuestion(data.active_question);
      setTokenUsage({ ...DEFAULT_TOKEN_USAGE, ...data.token_usage });
      if (data.learning_stats) setLearningStats(data.learning_stats);
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
      if (generationTimer !== undefined) window.clearTimeout(generationTimer);
      setSending(false);
    }
  }, [activeQuestion, activeSessionId, pendingNewSession, sending]);

  const handleComposerFiles = useCallback(async (files: File[]) => {
    if (!files.length || sending) return;
    setComposerFileStatus("正在读取拖入文件...");
    try {
      const imageFiles = files.filter(isImageFile);
      const extractFiles = files.filter((file) => !isImageFile(file));
      const attachedNames: string[] = [];
      if (currentModelVision && imageFiles.length) {
        const nextAttachments = await Promise.all(
          imageFiles.map(async (file) => ({
            type: "image" as const,
            filename: file.name,
            mime_type: file.type || "image/png",
            data_url: await fileToDataUrl(file)
          }))
        );
        setComposerAttachments((current) => [...current, ...nextAttachments]);
        attachedNames.push(...nextAttachments.map((item) => item.filename));
      } else {
        extractFiles.push(...imageFiles);
      }
      let extractedNames: string[] = [];
      if (extractFiles.length) {
        const extracted = await extractTextFromFiles(extractFiles);
        setInput((current) => appendImportedText(current, extracted.text));
        extractedNames = extracted.results.map((result) => result.filename);
      }
      const statusParts = [
        attachedNames.length ? `已附加 ${attachedNames.join("、")}，将由当前模型视觉识别` : "",
        extractedNames.length ? `已插入 ${extractedNames.join("、")} 的文本` : ""
      ].filter(Boolean);
      setComposerFileStatus(statusParts.join("；") || "未读取到可导入文件。");
      composerRef.current?.focus();
    } catch (err) {
      setComposerFileStatus(`文件读取失败：${err instanceof Error ? err.message : "未知错误"}`);
    }
  }, [currentModelVision, sending]);

  const handleComposerDrop = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setComposerDragActive(false);
    const files = Array.from(event.dataTransfer.files || []);
    void handleComposerFiles(files);
  }, [handleComposerFiles]);

  const sendMessage = useCallback(async () => {
    const content = input.trim();
    if ((!content && !composerAttachments.length) || sending) return;
    const attachments = composerAttachments;
    setInput("");
    setComposerAttachments([]);
    setComposerFileStatus("");
    await postChatContent(content, pendingNewSession, attachments);
  }, [composerAttachments, input, pendingNewSession, postChatContent, sending]);

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
    setLoadingLabel("模型正在判题");
    setSending(true);
    try {
      const data = await apiPost<{
        session_id: string;
        message: Message;
        daily_panel: DailyPanel;
        active_question: Question | null;
        token_usage: TokenUsage;
        learning_stats?: LearningStats;
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
      setTokenUsage({ ...DEFAULT_TOKEN_USAGE, ...data.token_usage });
      if (data.learning_stats) setLearningStats(data.learning_stats);
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

  const startNewChat = useCallback(() => {
    const today = localDateString();
    setActiveSessionId(null);
    setPendingNewSession(true);
    setExpandedDates((current) => ({ ...current, [today]: true }));
    setDailyPanel({ ...DEFAULT_PANEL, date: today });
    setActiveQuestion(null);
    setMessages([]);
    setInput("");
    setQuickStartHint("");
    composerRef.current?.focus();
  }, []);

  const saveQuickModelConfig = useCallback(async (nextConfig: ModelConfig) => {
    const nextProvider = selectedProvider(providers, nextConfig.provider_id);
    const nextThinkingOptions = thinkingOptionsForModel(nextProvider, nextConfig.model);
    const nextThinkingLevel = thinkingLevelForOptions(
      nextThinkingOptions,
      nextConfig.thinking_level,
      defaultThinkingLevelForModel(nextProvider, nextConfig.model)
    );
    const data = await apiPost<{ model_config: ModelConfig; providers?: ProviderOption[] }>("/api/model-config", {
      provider_id: nextConfig.provider_id,
      base_url: nextConfig.base_url,
      model: nextConfig.model,
      thinking_level: nextThinkingLevel,
      thinking_level_options: nextThinkingOptions,
      api_format: nextConfig.api_format || "",
      vision: Boolean(nextConfig.vision)
    });
    setModelConfig(normalizeModelConfig(data.model_config));
    if (data.providers) {
      setProviders(normalizeProviders(data.providers));
    }
  }, [providers]);

  const toggleDate = useCallback((date: string) => {
    setExpandedDates((current) => ({ ...current, [date]: !current[date] }));
  }, []);

  const copyText = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      document.body.removeChild(area);
    }
  }, []);

  const createBranchFromText = useCallback(async (text: string) => {
    const cleanText = text.trim();
    if (!activeSessionId || !cleanText || branchSending) return;
    const userMessage: Message = { id: `branch-create-${Date.now()}`, role: "user", content: cleanText };
    setBranchId(null);
    setRightOpen(true);
    setWorkbenchTab("branch");
    setBranchMessages([userMessage]);
    setBranchSending(true);
    try {
      const data = await apiPost<{ branch_id: string; message: string }>("/api/branch", {
        session_id: activeSessionId,
        selected_text: cleanText,
        message: "解释这段内容，并指出是否应写回复习卡片。"
      });
      setBranchId(data.branch_id);
      setBranchMessages((current) => [
        ...current,
        { id: `${data.branch_id}-a`, role: "assistant", content: data.message }
      ]);
    } catch (err) {
      setBranchMessages((current) => [
        ...current,
        { id: `branch-error-${Date.now()}`, role: "assistant", content: `分支创建失败：${err instanceof Error ? err.message : "未知错误"}` }
      ]);
    } finally {
      setBranchSending(false);
    }
  }, [activeSessionId, branchSending]);

  const startBranch = useCallback(async () => {
    await createBranchFromText(selectedTextRef.current || selectedText);
  }, [createBranchFromText, selectedText]);

  const sendBranchMessage = useCallback(async (content: string) => {
    const cleanContent = content.trim();
    if (!branchId || !cleanContent || branchSending) return;
    const userMessage: Message = { id: `branch-local-${Date.now()}`, role: "user", content: cleanContent };
    setBranchMessages((current) => [...current, userMessage]);
    setBranchSending(true);
    try {
      const data = await apiPost<{ branch_id: string; message: string }>(`/api/branch/${branchId}/messages`, { message: cleanContent });
      setBranchMessages((current) => [...current, { id: `${data.branch_id}-a-${Date.now()}`, role: "assistant", content: data.message }]);
    } catch (err) {
      setBranchMessages((current) => [...current, { id: `branch-error-${Date.now()}`, role: "assistant", content: `分支回复失败：${err instanceof Error ? err.message : "未知错误"}` }]);
    } finally {
      setBranchSending(false);
    }
  }, [branchId, branchSending]);

  const handleScreenshotImportComplete = useCallback((result: ScreenshotImportResult) => {
    if (result.session_id) {
      setActiveSessionId(result.session_id);
      setPendingNewSession(false);
    }
    if (result.messages?.length) {
      setMessages(result.messages);
    } else if (result.message) {
      setMessages((current) => [...current, result.message as Message]);
    }
    if (result.daily_panel) setDailyPanel(result.daily_panel);
    if (result.active_question !== undefined) setActiveQuestion(result.active_question || null);
    if (result.token_usage) setTokenUsage({ ...DEFAULT_TOKEN_USAGE, ...result.token_usage });
    if (result.learning_stats) setLearningStats(result.learning_stats);
    if (result.sessions) setSessions(result.sessions);
    if (result.auto_started) setQuickStartHint("");
    if (result.auto_started) setRightOpen(false);
  }, []);

  const handleConfirmSettingsAction = useCallback((action: SettingsAction) => {
    if (action.type === "past_paper_import_draft") {
      setPendingPaperDraft(action.draft);
      setSettingsOpen(true);
    }
  }, []);

  const hasCurrentImportedContent = hasDailyImportedContent(dailyPanel);

  const quickStartToday = useCallback(() => {
    if (!hasCurrentImportedContent) {
      setWorkbenchTab("screenshot");
      setRightOpen(true);
      setQuickStartHint("当前题库为空，右侧已打开截图导入。");
      return;
    }
    setQuickStartHint("");
    void postChatContent("继续当前题组", false);
  }, [hasCurrentImportedContent, postChatContent]);

  const compressContext = useCallback(async () => {
    if (!activeSessionId || compressingContext) return;
    setCompressingContext(true);
    try {
      const data = await apiPost<{ token_usage: TokenUsage; method: string; note: string }>("/api/context/compress", {
        session_id: activeSessionId
      });
      setTokenUsage({ ...DEFAULT_TOKEN_USAGE, ...data.token_usage });
    } catch (err) {
      const errorMsg: Message = {
        id: `context-error-${Date.now()}`,
        role: "assistant",
        content: `上下文压缩失败：${err instanceof Error ? err.message : "未知错误"}`
      };
      setMessages((current) => [...current, errorMsg]);
    } finally {
      setCompressingContext(false);
    }
  }, [activeSessionId, compressingContext]);

  const deleteSession = useCallback(async (sessionId: string) => {
    if (!window.confirm("确认删除这个会话？相关消息、题目、作答和分支记录会一并删除。")) return;
    const data = await apiDelete<{ deleted: boolean; sessions: SessionItem[]; learning_stats?: LearningStats }>(`/api/sessions/${sessionId}`);
    setSessions(data.sessions);
    if (data.learning_stats) setLearningStats(data.learning_stats);
    if (sessionId === activeSessionId) {
      setActiveSessionId(null);
      setPendingNewSession(false);
      setDailyPanel(DEFAULT_PANEL);
      setActiveQuestion(null);
      setMessages([]);
    }
  }, [activeSessionId]);

  const showSessionMenu = useCallback((event: MouseEvent, session: SessionItem) => {
    event.preventDefault();
    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      items: [
        { label: "删除会话", hint: "同时删除消息和题目", destructive: true, onSelect: () => void deleteSession(session.id) }
      ]
    });
  }, [deleteSession]);

  const showMessageMenu = useCallback((event: MouseEvent, message: Message) => {
    event.preventDefault();
    const items: ContextMenuItem[] = [
      { label: "复制", onSelect: () => void copyText(message.content) },
      {
        label: "重新编辑",
        hint: "放回输入框",
        onSelect: () => {
          setInput(message.content);
          composerRef.current?.focus();
        }
      },
      {
        label: "开启分支对话",
        hint: activeSessionId ? "基于这条消息" : "需要先发送主会话消息",
        disabled: !activeSessionId,
        onSelect: () => void createBranchFromText(message.content)
      }
    ];
    setContextMenu({ x: event.clientX, y: event.clientY, items });
  }, [activeSessionId, copyText, createBranchFromText]);

  return (
    <div className={`app-shell ${resizingPanel ? `resizing-panels resizing-${resizingPanel}` : ""}`} ref={appRef} style={appShellStyle}>
      <aside className={`left-rail panel-motion ${leftOpen ? "open" : "closed"}`}>
        {leftOpen && (
          <button
            type="button"
            className="panel-resizer panel-resizer-left"
            aria-label="拖拽调整左侧栏宽度"
            title="拖拽调整左侧栏宽度"
            onPointerDown={(event) => startPanelResize("left", event)}
            onKeyDown={(event) => resizePanelWithKeyboard("left", event)}
          />
        )}
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
                        className={`session-link ${(item.id === activeSessionId || item.draft) ? "active" : ""} ${item.draft ? "draft" : ""}`}
                        key={item.id}
                        onContextMenu={(event) => {
                          if (!item.draft) showSessionMenu(event, item);
                        }}
                        onClick={async () => {
                          if (item.draft) {
                            startNewChat();
                            return;
                          }
                          setActiveSessionId(item.id);
                          setQuickStartHint("");
                          try {
                            const detail = await apiGet<{
                              session: Record<string, unknown>;
                              messages: Message[];
                              daily_panel: DailyPanel;
                              active_question: Question | null;
                              token_usage: TokenUsage;
                              learning_stats?: LearningStats;
                            }>(`/api/sessions/${item.id}`);
                            if (detail.messages) {
                              setMessages(detail.messages);
                              setDailyPanel(detail.daily_panel);
                              setActiveQuestion(detail.active_question);
                              setTokenUsage({ ...DEFAULT_TOKEN_USAGE, ...detail.token_usage });
                              if (detail.learning_stats) setLearningStats(detail.learning_stats);
                              setPendingNewSession(false);
                            }
                          } catch {
                            // 加载失败时保持当前状态
                          }
                        }}
                      >
                        <ChatCircleText size={16} />
                        <span>{item.title}</span>
                        {item.draft && <small>草稿</small>}
                      </button>
                    ))}
                </section>
              ))}
            </div>
            <button className="settings-button" onClick={() => setSettingsOpen(true)} title="打开设置">
              <GearSix size={18} />
              <span>设置</span>
            </button>
          </>
        )}
      </aside>

      <main className="chat-main panel-motion">
        <div
          className="message-stream"
          onMouseUp={() => {
            const text = window.getSelection()?.toString().trim() || "";
            if (text) selectedTextRef.current = text;
            setSelectedText(text);
          }}
        >
          <LongTermPanel
            profile={profile}
            tokenUsage={tokenUsage}
            learningStats={learningStats}
            dailyPanel={dailyPanel}
            compact={!emptyContext}
            quickStartHint={quickStartHint}
            onQuickStart={quickStartToday}
          />
          {messages.map((message) => (
            <MessageItem
              key={message.id}
              message={message}
              onContextMenu={showMessageMenu}
              onConfirmSettingsAction={handleConfirmSettingsAction}
            />
          ))}
          {sending && <ThinkingBubble label={loadingLabel} />}
          {activeQuestion?.status === "ready" && (
            <QuestionDock
              question={activeQuestion}
              sending={sending}
              onSubmit={(option, extraPrompt) => void sendQuestionAnswer(option, extraPrompt)}
            />
          )}
          <div ref={messageEndRef} />
        </div>
        {selectedText && (
          <InteractiveButton
            className="branch-fab"
            onClick={startBranch}
            onPointerDown={(event) => event.preventDefault()}
          >
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
              value={quickProviderId}
              onChange={(event) => {
                const nextProvider = selectedProvider(quickProviders, event.target.value);
                const nextModel = modelOptionsFor(nextProvider, nextProvider.model, { visibleOnly: true })[0]?.id || nextProvider.model || "";
                void saveQuickModelConfig({
                  ...modelConfig,
                  provider_id: nextProvider.id,
                  base_url: nextProvider.base_url,
                  model: nextModel,
                  api_format: nextProvider.api_format,
                  thinking_level: defaultThinkingLevelForModel(nextProvider, nextModel),
                  vision: modelSupportsVision(nextProvider, nextModel)
                });
              }}
              title="模型供应商"
            >
              {quickProviders.map((provider) => (
                <option key={provider.id} value={provider.id}>{provider.label}</option>
              ))}
            </select>
            <select
              value={quickCurrentModel}
              onChange={(event) => void saveQuickModelConfig({
                ...modelConfig,
                provider_id: quickProvider.id,
                base_url: quickProvider.base_url,
                api_format: quickProvider.api_format,
                model: event.target.value,
                thinking_level: defaultThinkingLevelForModel(quickProvider, event.target.value),
                vision: modelSupportsVision(quickProvider, event.target.value)
              })}
              title="模型"
            >
              {quickModelOptions.map((model) => (
                <option key={model.id} value={model.id}>{modelOptionLabel(model)}</option>
              ))}
            </select>
            {quickThinkingOptions.length > 0 && (
              <select
                value={quickThinkingLevel}
                onChange={(event) => void saveQuickModelConfig({
                  ...modelConfig,
                  provider_id: quickProvider.id,
                  base_url: quickProvider.base_url,
                  api_format: quickProvider.api_format,
                  model: quickCurrentModel,
                  thinking_level: event.target.value as ThinkingLevel,
                  vision: modelSupportsVision(quickProvider, quickCurrentModel)
                })}
                title="思考等级"
              >
                {quickThinkingOptions.map((option) => (
                  <option key={option.id} value={option.id}>思考：{option.label}</option>
                ))}
              </select>
            )}
            <span title={currentModelVision ? "拖入图片会随消息发给当前模型" : "拖入图片会先调用 MinerU/本地 OCR 提取文本"}>图片：{currentModelVision ? "模型视觉" : "MinerU解析"}</span>
          </div>
          {composerAttachments.length > 0 && (
            <div className="composer-attachments" aria-label="待发送图片">
              {composerAttachments.map((attachment, index) => (
                <button
                  key={`${attachment.filename}-${index}`}
                  type="button"
                  onClick={() => setComposerAttachments((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                  title="移除图片附件"
                >
                  <ImageSquare size={16} />
                  <span>{attachment.filename || "图片附件"}</span>
                  <X size={14} />
                </button>
              ))}
            </div>
          )}
          <div
            className={`composer ${composerDragActive ? "drag-over" : ""}`}
            onDragEnter={(event) => {
              if (event.dataTransfer.types.includes("Files")) setComposerDragActive(true);
            }}
            onDragOver={(event) => {
              if (event.dataTransfer.types.includes("Files")) event.preventDefault();
            }}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                setComposerDragActive(false);
              }
            }}
            onDrop={handleComposerDrop}
          >
            <textarea
              ref={composerRef}
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
            <ContextMeter
              tokenUsage={tokenUsage}
              disabled={!activeSessionId || compressingContext}
              compressing={compressingContext}
              onCompress={() => void compressContext()}
            />
            <InteractiveButton className={`send-button ${sending ? "sending" : ""}`} onClick={() => void sendMessage()} title="发送">
              {sending ? <span className="spinner" /> : <PaperPlaneRight size={20} weight="fill" />}
            </InteractiveButton>
          </div>
          {composerFileStatus && <p className="composer-file-status">{composerFileStatus}</p>}
        </div>
      </main>

      <RightWorkbench
        open={rightOpen}
        branchId={branchId}
        branchMessages={branchMessages}
        branchSending={branchSending}
        sessionId={activeSessionId}
        activeTab={workbenchTab}
        onTabChange={setWorkbenchTab}
        onToggle={() => setRightOpen((value) => !value)}
        onResizeStart={(event) => startPanelResize("right", event)}
        onResizeKeyDown={(event) => resizePanelWithKeyboard("right", event)}
        onSendBranchMessage={(content) => void sendBranchMessage(content)}
        onDailyPanelChange={setDailyPanel}
        onScreenshotImportComplete={handleScreenshotImportComplete}
      />

      {settingsOpen && (
        <SettingsDialog
          profile={profile}
          providers={providers}
          modelConfig={modelConfig}
          themeMode={themeMode}
          fontSize={fontSize}
          tokenUsage={tokenUsage}
          dataPaths={dataPaths}
          mineruConfig={mineruConfig}
          agentPermissions={agentPermissions}
          pendingPaperDraft={pendingPaperDraft}
          sessions={sessions}
          examOptions={examOptions}
          syllabusStatus={syllabusStatus}
          pastPaperStatus={pastPaperStatus}
          onClose={() => setSettingsOpen(false)}
          onProfileChange={setProfile}
          onSessionsChange={setSessions}
          onSyllabusStatusChange={setSyllabusStatus}
          onPastPaperStatusChange={setPastPaperStatus}
          onModelConfigChange={setModelConfig}
          onAppearanceChange={(nextTheme, nextFontSize) => {
            setThemeMode(nextTheme);
            setFontSize(nextFontSize);
          }}
          onProvidersChange={setProviders}
          onLearningStatsChange={setLearningStats}
          onTokenUsageChange={(nextUsage) => setTokenUsage({ ...DEFAULT_TOKEN_USAGE, ...nextUsage })}
          onDataPathsChange={(nextPaths) => setDataPaths({ ...DEFAULT_DATA_PATHS, ...nextPaths })}
          onMinerUConfigChange={(nextConfig) => setMineruConfig({ ...DEFAULT_MINERU_CONFIG, ...nextConfig })}
          onAgentPermissionsChange={setAgentPermissions}
          onPaperDraftConsumed={() => setPendingPaperDraft(null)}
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
            void apiGet<{ model_config?: ModelConfig; learning_stats?: LearningStats }>("/api/bootstrap").then((data) => {
              setModelConfig(normalizeModelConfig(data.model_config));
              if (data.learning_stats) setLearningStats(data.learning_stats);
            });
            setOnboardingOpen(false);
          }}
        />
      )}
      {contextMenu && <ContextMenu x={contextMenu.x} y={contextMenu.y} items={contextMenu.items} onClose={() => setContextMenu(null)} />}
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

function LongTermPanel({
  profile,
  tokenUsage,
  learningStats,
  dailyPanel,
  compact = false,
  quickStartHint,
  onQuickStart
}: {
  profile: Profile;
  tokenUsage: TokenUsage;
  learningStats: LearningStats;
  dailyPanel: DailyPanel;
  compact?: boolean;
  quickStartHint?: string;
  onQuickStart: () => void;
}) {
  const questionTotal = learningStats.questions_total || 0;
  const wordsTotal = learningStats.words_total || 0;
  const accuracyText = learningStats.attempts_total ? `${Math.round(learningStats.accuracy * 100)}%` : "未开始";
  const questionPercent = questionTotal ? Math.round((learningStats.questions_done / questionTotal) * 100) : 0;
  const wordPercent = wordsTotal ? Math.round((learningStats.words_mastered / wordsTotal) * 100) : 0;
  const hasCurrentContent = hasDailyImportedContent(dailyPanel);
  return (
    <section className={`long-panel ${compact ? "compact" : ""}`}>
      <div className="long-grid">
        <div>
          <span className="kicker">Learning Memory（学习记忆）</span>
          <h1>长期学习记录总面板</h1>
          <p>{`${profile.exam_name || learningStats.exam_name} · ${profile.target_language}`}</p>
          {!hasCurrentContent && quickStartHint && <p className="quick-start-hint" aria-live="polite">{quickStartHint}</p>}
        </div>
        <div className="score-stack">
          <Stat icon={<CheckCircle size={18} />} label="题目完成" value={`${learningStats.questions_done}/${questionTotal}`} detail={questionTotal ? `${questionPercent}%` : "等待题组"} />
          <Stat icon={<Brain size={18} />} label="单词掌握" value={`${learningStats.words_mastered}/${wordsTotal}`} detail={wordsTotal ? `${wordPercent}%` : "等待导入"} />
          <Stat icon={<ShieldCheck size={18} />} label="整体正确率" value={accuracyText} detail={`${learningStats.attempts_correct}/${learningStats.attempts_total} 次正确`} />
          <Stat icon={<Target size={18} />} label="考试倒计时" value={countdownText(profile.deadline)} detail={profile.deadline ? "按考试时间实时计算" : "在设置中添加考试时间"} />
        </div>
      </div>
      <div className="learning-stat-strip" aria-label="长期学习统计">
        <span><ListBullets size={16} /> 当前考试：{learningStats.exam_name || profile.exam_name}</span>
        <span><Brain size={16} /> 累计 token（令牌）：{(tokenUsage.total || 0).toLocaleString("zh-CN")}</span>
        <button
          type="button"
          className={`quick-start-button ${hasCurrentContent ? "primary" : "import"}`}
          onClick={onQuickStart}
          aria-label={hasCurrentContent ? "继续当前题组" : "打开当日截图导入"}
          title={hasCurrentContent ? "继续当前题组" : "打开右侧截图导入"}
        >
          {hasCurrentContent ? <PlayCircle size={17} /> : <ImageSquare size={17} />}
          <span>{hasCurrentContent ? "快速开始" : "当日导入"}</span>
        </button>
      </div>
    </section>
  );
}

function Stat({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string; detail: string }) {
  return (
    <div className="stat learning-stat-card">
      <div className="stat-icon">{icon}</div>
      <strong>{value}</strong>
      <span>{label}</span>
      <small>{detail}</small>
    </div>
  );
}

function ContextMeter({
  tokenUsage,
  disabled,
  compressing,
  onCompress
}: {
  tokenUsage: TokenUsage;
  disabled: boolean;
  compressing: boolean;
  onCompress: () => void;
}) {
  const limit = tokenUsage.context_limit || DEFAULT_CONTEXT_LIMIT;
  const current = tokenUsage.estimated_current_context || 0;
  const percent = contextPercentFromUsage(tokenUsage);
  return (
    <div className="context-meter-wrap">
      <button
        className="context-meter-button"
        type="button"
        aria-label="上下文容量"
        style={{ "--context-percent": `${percent}%` } as CSSProperties}
      >
        {compressing ? <CircleNotch size={19} className="context-spin" /> : <span />}
      </button>
      <div className="context-popover">
        <div className="context-popover-head">
          <strong>上下文容量</strong>
          <span>{formatCompactNumber(current)} / {formatCompactNumber(limit)}（{percent}%）</span>
        </div>
        <div className="thin-progress compact">
          <span style={{ width: `${Math.max(4, percent)}%` }} />
        </div>
        <dl>
          <div><dt>消息数</dt><dd>{formatNumber(tokenUsage.context_messages)}</dd></div>
          <div><dt>压缩摘要</dt><dd>{formatCompactNumber(tokenUsage.compressed_context_tokens)}</dd></div>
          <div><dt>压缩方式</dt><dd>{tokenUsage.compression_method || "未压缩"}</dd></div>
        </dl>
        <button className="inline-action context-compress" disabled={disabled} onClick={onCompress}>
          {compressing ? "压缩中..." : "压缩上下文"}
        </button>
      </div>
    </div>
  );
}

function QuestionReviewCard({ question }: { question: AnsweredQuestion }) {
  const selectedLetter = selectedLetterForQuestion(question);
  const correctLetter = correctLetterForQuestion(question);
  const total = Math.max(question.set_total || 0, question.sequence || 1);
  const resultText = question.is_correct ? "回答正确" : "回答错误";
  return (
    <section className={`question-review-card ${question.is_correct ? "correct" : "incorrect"}`} aria-label="已回答题目">
      <div className="question-review-head">
        {question.is_correct ? <CheckCircle size={18} /> : <X size={18} />}
        <span>已回答：第 {question.sequence || 1} 题 / 共 {total} 题</span>
        <strong>{resultText}</strong>
      </div>
      <p>{cleanQuestionPrompt(question)}</p>
      <div className="review-options" aria-label="上一题选项回顾">
        {question.options.map((option, index) => {
          const letter = optionLetter(index);
          const isSelected = selectedLetter === letter;
          const isCorrect = correctLetter === letter;
          const marker = isSelected && isCorrect ? "你的选择 / 正确答案" : isCorrect ? "正确答案" : isSelected ? "你的选择" : "";
          return (
            <div
              key={`${letter}-${option}`}
              className={`review-option ${isSelected ? "selected" : ""} ${isCorrect ? "correct" : ""}`}
            >
              <span className="review-letter">{letter}</span>
              <span>{option}</span>
              {marker && <small>{marker}</small>}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function QuestionDock({
  question,
  sending,
  onSubmit
}: {
  question: Question;
  sending: boolean;
  onSubmit: (option: string, extraPrompt: string) => void;
}) {
  const [selectedOption, setSelectedOption] = useState("");
  const [extraPrompt, setExtraPrompt] = useState("");
  const total = Math.max(question.set_total || 0, question.sequence || 1);
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
            key={`${index}-${option}`}
            className={selectedOption === optionLetter(index) ? "selected" : ""}
            onClick={() => setSelectedOption(optionLetter(index))}
          >
            {optionLetter(index)}. {option}
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
  dataPaths,
  mineruConfig,
  agentPermissions,
  pendingPaperDraft,
  sessions,
  examOptions,
  syllabusStatus,
  pastPaperStatus,
  onClose,
  onProfileChange,
  onSessionsChange,
  onSyllabusStatusChange,
  onPastPaperStatusChange,
  onModelConfigChange,
  onAppearanceChange,
  onProvidersChange,
  onLearningStatsChange,
  onTokenUsageChange,
  onDataPathsChange,
  onMinerUConfigChange,
  onAgentPermissionsChange,
  onPaperDraftConsumed,
  onOpenOnboarding
}: {
  profile: Profile;
  providers: ProviderOption[];
  modelConfig: ModelConfig;
  themeMode: ThemeMode;
  fontSize: number;
  tokenUsage: TokenUsage;
  dataPaths: DataPathsStatus;
  mineruConfig: MinerUConfig;
  agentPermissions: AgentSettingsPermissionsStatus;
  pendingPaperDraft: PastPaperDraft | null;
  sessions: SessionItem[];
  examOptions: ExamOption[];
  syllabusStatus: SyllabusStatus;
  pastPaperStatus: PastPaperStatus;
  onClose: () => void;
  onProfileChange: (profile: Profile) => void;
  onSessionsChange: (sessions: SessionItem[]) => void;
  onSyllabusStatusChange: (status: SyllabusStatus) => void;
  onPastPaperStatusChange: (status: PastPaperStatus) => void;
  onModelConfigChange: (config: ModelConfig) => void;
  onAppearanceChange: (themeMode: ThemeMode, fontSize: number) => void;
  onProvidersChange: (providers: ProviderOption[]) => void;
  onLearningStatsChange: (stats: LearningStats) => void;
  onTokenUsageChange: (usage: TokenUsage) => void;
  onDataPathsChange: (paths: DataPathsStatus) => void;
  onMinerUConfigChange: (config: MinerUConfig) => void;
  onAgentPermissionsChange: (permissions: AgentSettingsPermissionsStatus) => void;
  onPaperDraftConsumed: () => void;
  onOpenOnboarding: () => void;
}) {
  const [draft, setDraft] = useState(profile);
  const [modelDraft, setModelDraft] = useState<ModelConfig>({ ...modelConfig, api_key: "" });
  const [modelRefreshing, setModelRefreshing] = useState(false);
  const [modelRefreshMessage, setModelRefreshMessage] = useState("");
  const [customProviderOpen, setCustomProviderOpen] = useState(false);
  const [customProviderSaving, setCustomProviderSaving] = useState(false);
  const [customProviderDraft, setCustomProviderDraft] = useState({
    name: "",
    base_url: "",
    default_model: ""
  });
  const [thinkingLevelFormOpen, setThinkingLevelFormOpen] = useState(false);
  const [thinkingLevelDraft, setThinkingLevelDraft] = useState({ label: "", api_value: "" });
  const [thinkingLevelError, setThinkingLevelError] = useState("");
  const [appearanceDraft, setAppearanceDraft] = useState({ themeMode, fontSize });
  const [reviewIntensity, setReviewIntensity] = useState(3);
  const [saveState, setSaveState] = useState("");
  const [contextLimit, setContextLimit] = useState(tokenUsage.context_limit || DEFAULT_CONTEXT_LIMIT);
  const [dataPathDraft, setDataPathDraft] = useState<DataPathsStatus>(dataPaths);
  const [mineruDraft, setMineruDraft] = useState<MinerUConfig>({ ...DEFAULT_MINERU_CONFIG, ...mineruConfig });
  const [mineruToken, setMineruToken] = useState("");
  const [mineruMessage, setMineruMessage] = useState("");
  const [permissionDraft, setPermissionDraft] = useState<AgentSettingsPermissionsStatus>(agentPermissions);
  const [permissionMessage, setPermissionMessage] = useState("");
  const [questionDbFolder, setQuestionDbFolder] = useState(dataPaths.user_data_dir || "");
  const [migrateQuestionDb, setMigrateQuestionDb] = useState(true);
  const [overwriteQuestionDb, setOverwriteQuestionDb] = useState(false);
  const [dataPathMessage, setDataPathMessage] = useState("");
  const [activeSettingsTab, setActiveSettingsTab] = useState("model");
  const [syllabusDraft, setSyllabusDraft] = useState(syllabusStatus);
  const [syllabusMessage, setSyllabusMessage] = useState("");
  const [pastPaperDraft, setPastPaperDraft] = useState(pastPaperStatus);
  const [pastPaperMessage, setPastPaperMessage] = useState("");
  const [paperImportOpen, setPaperImportOpen] = useState(false);
  const [paperImportDraft, setPaperImportDraft] = useState({
    title: "",
    year: "",
    source_url: "",
    local_path: "",
    summary: "",
    question_types: "",
    raw_text: ""
  });
  const [paperImportFile, setPaperImportFile] = useState<File | null>(null);
  const [paperImportDragActive, setPaperImportDragActive] = useState(false);
  const paperFileInputRef = useRef<HTMLInputElement | null>(null);
  const [customExam, setCustomExam] = useState({
    name: "",
    target_language: "",
    syllabus_mode: "auto",
    syllabus_url: "",
    paper_source_url: "",
    default_question_types: "",
    local_path: "",
    notes: ""
  });
  const provider = selectedProvider(providers, modelDraft.provider_id);
  const modelOptions = modelOptionsFor(provider, modelDraft.model);
  const modelThinkingOptions = modelDraft.thinking_level_options?.length
    ? modelDraft.thinking_level_options
    : thinkingOptionsForModel(provider, modelDraft.model);
  const selectedModelThinkingLevel = thinkingLevelForOptions(
    modelThinkingOptions,
    modelDraft.thinking_level,
    defaultThinkingLevelForModel(provider, modelDraft.model)
  );
  const applyPaperDraftToForm = useCallback((draft: PastPaperDraft, message: string) => {
    setActiveSettingsTab("syllabus");
    setPaperImportOpen(true);
    setPaperImportDraft((current) => ({
      title: draft.title || current.title,
      year: draft.year ? String(draft.year) : current.year,
      source_url: draft.source_url || current.source_url,
      local_path: draft.local_path || current.local_path,
      summary: draft.summary || current.summary,
      question_types: draft.question_types?.length ? draft.question_types.join(", ") : current.question_types,
      raw_text: draft.raw_text || current.raw_text
    }));
    setPastPaperMessage(message);
  }, []);
  useEffect(() => {
    setPermissionDraft(agentPermissions);
  }, [agentPermissions]);
  useEffect(() => {
    if (!pendingPaperDraft) return;
    applyPaperDraftToForm(pendingPaperDraft, "已由会话 Agent 填入试卷导入草稿，保存前可继续修改。");
    onPaperDraftConsumed();
  }, [applyPaperDraftToForm, onPaperDraftConsumed, pendingPaperDraft]);
  const chooseProvider = (providerId: string) => {
    const nextProvider = selectedProvider(providers, providerId);
    const nextModel = modelOptionsFor(nextProvider, nextProvider.model)[0]?.id || nextProvider.model || "";
    const nextThinkingOptions = thinkingOptionsForModel(nextProvider, nextModel);
    setModelDraft({
      ...modelDraft,
      provider_id: nextProvider.id,
      base_url: nextProvider.base_url,
      api_format: nextProvider.api_format,
      model: nextModel,
      thinking_level: defaultThinkingLevelForModel(nextProvider, nextModel),
      thinking_level_options: nextThinkingOptions,
      vision: modelSupportsVision(nextProvider, nextModel)
    });
    setThinkingLevelFormOpen(false);
    setThinkingLevelDraft({ label: "", api_value: "" });
    setThinkingLevelError("");
  };
  const chooseModel = (modelId: string) => {
    const nextThinkingOptions = thinkingOptionsForModel(provider, modelId);
    setModelDraft({
      ...modelDraft,
      model: modelId,
      thinking_level: defaultThinkingLevelForModel(provider, modelId),
      thinking_level_options: nextThinkingOptions,
      vision: modelSupportsVision(provider, modelId)
    });
    setThinkingLevelFormOpen(false);
    setThinkingLevelDraft({ label: "", api_value: "" });
    setThinkingLevelError("");
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
      try {
        const paperStatus = await apiGet<PastPaperStatus>("/api/past-papers/status?exam_id=custom");
        setPastPaperDraft(paperStatus);
        onPastPaperStatusChange(paperStatus);
      } catch {
        setPastPaperMessage("自定义考试真题状态读取失败，请确认后端已启动。");
      }
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
      const paperStatus = await apiGet<PastPaperStatus>(`/api/past-papers/status?exam_id=${encodeURIComponent(option.id)}`);
      setPastPaperDraft(paperStatus);
      onPastPaperStatusChange(paperStatus);
    } catch {
      setSyllabusMessage("考纲或真题状态读取失败，请确认后端已启动。");
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
  const togglePastPaper = async (paperId: string) => {
    const selected = new Set(pastPaperDraft.selected_paper_ids);
    if (selected.has(paperId)) {
      selected.delete(paperId);
    } else {
      selected.add(paperId);
    }
    try {
      const status = await apiPost<PastPaperStatus>("/api/past-papers/select", {
        exam_id: draft.exam_id,
        paper_ids: Array.from(selected)
      });
      setPastPaperDraft(status);
      onPastPaperStatusChange(status);
      setPastPaperMessage(`当前参考 ${status.selected_paper_ids.length} 套历年真题试卷。`);
    } catch (err) {
      setPastPaperMessage(err instanceof Error ? err.message : "真题选择保存失败");
    }
  };
  const toggleQuestionType = async (typeId: string) => {
    const selected = new Set(pastPaperDraft.enabled_question_type_ids);
    if (selected.has(typeId)) {
      selected.delete(typeId);
    } else {
      selected.add(typeId);
    }
    try {
      const status = await apiPost<PastPaperStatus>("/api/past-papers/question-types", {
        exam_id: draft.exam_id,
        enabled_type_ids: Array.from(selected)
      });
      setPastPaperDraft(status);
      onPastPaperStatusChange(status);
      setPastPaperMessage("题型生成范围已保存。");
    } catch (err) {
      setPastPaperMessage(err instanceof Error ? err.message : "题型保存失败");
    }
  };
  const draftPastPaperImport = async () => {
    setPastPaperMessage("正在解析试卷草稿...");
    try {
      const questionTypes = paperImportDraft.question_types.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean);
      const data = paperImportFile
        ? await uploadPastPaperDraftFile<{ draft: PastPaperDraft; parser: string; message: string; file_parser?: string }>(paperImportFile, {
          exam_id: draft.exam_id,
          title: paperImportDraft.title.trim() || fileTitle(paperImportFile),
          year: paperImportDraft.year,
          source_url: paperImportDraft.source_url,
          summary: paperImportDraft.summary,
          question_types: paperImportDraft.question_types,
          parse_now: false
        })
        : await apiPost<{ draft: PastPaperDraft; parser: string; message: string; file_parser?: string }>("/api/past-papers/draft", {
          exam_id: draft.exam_id,
          title: paperImportDraft.title,
          year: paperImportDraft.year ? Number(paperImportDraft.year) : null,
          source_url: paperImportDraft.source_url,
          local_path: paperImportDraft.local_path,
          summary: paperImportDraft.summary,
          question_types: questionTypes,
          raw_text: paperImportDraft.raw_text,
          filename: paperImportDraft.local_path
        });
      applyPaperDraftToForm(data.draft, data.file_parser ? `${data.message} 文件解析器：${data.file_parser}` : data.message);
    } catch (err) {
      setPastPaperMessage(err instanceof Error ? err.message : "草稿解析失败");
    }
  };
  const importPastPaper = async () => {
    const finalTitle = paperImportDraft.title.trim() || (paperImportFile ? fileTitle(paperImportFile) : "");
    if (!finalTitle) {
      setPastPaperMessage("请先填写试卷标题。");
      return;
    }
    try {
      const questionTypes = paperImportDraft.question_types.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean);
      const status = paperImportFile
        ? await uploadPastPaperFile<PastPaperStatus>(paperImportFile, {
          exam_id: draft.exam_id,
          title: finalTitle,
          year: paperImportDraft.year,
          source_url: paperImportDraft.source_url,
          summary: paperImportDraft.summary,
          question_types: paperImportDraft.question_types,
          parse_now: true
        })
        : await apiPost<PastPaperStatus>("/api/past-papers/import", {
          exam_id: draft.exam_id,
          title: finalTitle,
          year: paperImportDraft.year ? Number(paperImportDraft.year) : null,
          source_url: paperImportDraft.source_url,
          local_path: paperImportDraft.local_path,
          summary: paperImportDraft.summary,
          question_types: questionTypes,
          raw_text: paperImportDraft.raw_text,
          parse_now: true
        });
      setPastPaperDraft(status);
      onPastPaperStatusChange(status);
      setPaperImportDraft({ title: "", year: "", source_url: "", local_path: "", summary: "", question_types: "", raw_text: "" });
      setPaperImportFile(null);
      setPaperImportOpen(false);
      setPastPaperMessage("已保存试卷文件/文本、完成解析并加入当前参考列表。");
    } catch (err) {
      setPastPaperMessage(err instanceof Error ? err.message : "手动导入失败");
    }
  };
  const parsePastPaper = async (paperId: string) => {
    setPastPaperMessage("正在重新解析试卷...");
    try {
      const status = await apiPost<PastPaperStatus>("/api/past-papers/parse", {
        exam_id: draft.exam_id,
        paper_id: paperId
      });
      setPastPaperDraft(status);
      onPastPaperStatusChange(status);
      setPastPaperMessage("已重新解析试卷。");
    } catch (err) {
      setPastPaperMessage(err instanceof Error ? err.message : "重新解析失败");
    }
  };
  const searchImportPastPapers = async () => {
    setPastPaperMessage("正在创建联网搜索导入索引...");
    try {
      const status = await apiPost<PastPaperStatus>("/api/past-papers/search-import", {
        exam_id: draft.exam_id,
        source_website: paperImportDraft.source_url || customExam.paper_source_url || pastPaperDraft.source_website
      });
      setPastPaperDraft(status);
      onPastPaperStatusChange(status);
      setPastPaperMessage(status.message || "已导入近三年真题搜索索引。");
    } catch (err) {
      setPastPaperMessage(err instanceof Error ? err.message : "联网搜索导入失败");
    }
  };
  const selectPastPaperFile = useCallback((file: File) => {
    setPaperImportOpen(true);
    setPaperImportFile(file);
    setPaperImportDraft((current) => ({
      ...current,
      title: current.title || fileTitle(file),
      local_path: file.name
    }));
    setPastPaperMessage(`已选择文件：${file.name}。`);
  }, []);
  const handlePastPaperDrop = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setPaperImportDragActive(false);
    const file = Array.from(event.dataTransfer.files || [])[0];
    if (!file) return;
    selectPastPaperFile(file);
  }, [selectPastPaperFile]);
  const handlePastPaperFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = Array.from(event.target.files || [])[0];
    if (file) selectPastPaperFile(file);
    event.target.value = "";
  };
  const refreshProviderModels = async () => {
    setModelRefreshing(true);
    setModelRefreshMessage("正在从供应商 API 获取可调用模型...");
    try {
      const data = await apiPost<{ provider: ProviderOption; providers: ProviderOption[]; model_config?: ModelConfig; message?: string }>("/api/model-config/models/refresh", {
        provider_id: modelDraft.provider_id,
        base_url: modelDraft.base_url,
        api_key: modelDraft.api_key || "",
        api_format: modelDraft.api_format
      });
      const nextProviders = normalizeProviders(data.providers);
      const nextProvider = selectedProvider(nextProviders, modelDraft.provider_id);
      const selectableModels = modelOptionsFor(nextProvider, modelDraft.model, { visibleOnly: true });
      const nextModel = selectableModels.some((item) => item.id === modelDraft.model)
        ? modelDraft.model
        : selectableModels[0]?.id || nextProvider.model || "";
      const nextThinkingOptions = thinkingOptionsForModel(nextProvider, nextModel);
      onProvidersChange(nextProviders);
      if (data.model_config) onModelConfigChange(normalizeModelConfig(data.model_config));
      setModelDraft({
        ...modelDraft,
        provider_id: nextProvider.id,
        base_url: nextProvider.base_url,
        api_format: nextProvider.api_format,
        model: nextModel,
        thinking_level: defaultThinkingLevelForModel(nextProvider, nextModel),
        thinking_level_options: nextThinkingOptions,
        vision: modelSupportsVision(nextProvider, nextModel)
      });
      setModelRefreshMessage(data.message || `已获取 ${selectableModels.length} 个可调用模型。`);
    } catch (err) {
      setModelRefreshMessage(err instanceof Error ? err.message : "获取模型列表失败。");
    } finally {
      setModelRefreshing(false);
    }
  };
  const toggleModelVisibility = async (modelId: string, visible: boolean) => {
    setModelRefreshMessage(`正在${visible ? "显示" : "隐藏"}模型 ${modelId}...`);
    try {
      const data = await apiPost<{ provider: ProviderOption; providers: ProviderOption[]; model_config?: ModelConfig; message?: string }>("/api/model-config/models/visibility", {
        provider_id: modelDraft.provider_id,
        model: modelId,
        visible
      });
      const nextProviders = normalizeProviders(data.providers);
      onProvidersChange(nextProviders);
      if (data.model_config) onModelConfigChange(normalizeModelConfig(data.model_config));
      const nextProvider = selectedProvider(nextProviders, modelDraft.provider_id);
      setModelDraft({
        ...modelDraft,
        thinking_level_options: thinkingOptionsForModel(nextProvider, modelDraft.model),
        vision: modelSupportsVision(nextProvider, modelDraft.model)
      });
      setModelRefreshMessage(data.message || `模型 ${modelId} 已${visible ? "显示" : "隐藏"}。`);
    } catch (err) {
      setModelRefreshMessage(err instanceof Error ? err.message : "模型显示状态保存失败。");
    }
  };
  const saveModelConfig = async (successMessage = "模型配置已保存，Base URL（基础网址）、API 格式和模型能力会应用于当前供应商。") => {
    const finalModel = modelDraft.model;
    const finalThinkingOptions = finalModel === modelDraft.model ? modelThinkingOptions : thinkingOptionsForModel(provider, finalModel);
    const finalThinkingLevel = thinkingLevelForOptions(
      finalThinkingOptions,
      modelDraft.thinking_level,
      defaultThinkingLevelForModel(provider, finalModel)
    );
    const data = await apiPost<{ model_config: ModelConfig; providers?: ProviderOption[] }>("/api/model-config", {
      ...modelDraft,
      model: finalModel,
      thinking_level: finalThinkingLevel,
      thinking_level_options: finalThinkingOptions
    });
    onModelConfigChange(data.model_config);
    if (data.providers) {
      onProvidersChange(normalizeProviders(data.providers));
    }
    setSaveState(successMessage);
  };
  const saveDefaultModelConfig = async () => {
    const finalModel = modelDraft.model;
    const finalThinkingOptions = finalModel === modelDraft.model ? modelThinkingOptions : thinkingOptionsForModel(provider, finalModel);
    const finalThinkingLevel = thinkingLevelForOptions(
      finalThinkingOptions,
      modelDraft.thinking_level,
      defaultThinkingLevelForModel(provider, finalModel)
    );
    const data = await apiPost<{ model_config: ModelConfig; providers?: ProviderOption[] }>("/api/model-config/default", {
      ...modelDraft,
      model: finalModel,
      thinking_level: finalThinkingLevel,
      thinking_level_options: finalThinkingOptions
    });
    onModelConfigChange(data.model_config);
    if (data.providers) {
      onProvidersChange(normalizeProviders(data.providers));
    }
    setSaveState(`默认模型已切换为 ${data.model_config.model}。`);
  };
  const saveSettings = async () => {
    // 持久化 profile 到后端
    try {
      const profileData = await apiPost<{ profile: Profile; sessions?: SessionItem[]; syllabus_status?: SyllabusStatus; past_paper_status?: PastPaperStatus; learning_stats?: LearningStats }>("/api/profile", {
        display_name: draft.display_name,
        target_language: draft.target_language,
        exam_id: draft.exam_id,
        exam_name: draft.exam_name,
        deadline: draft.deadline || null,
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
      if (profileData.past_paper_status) {
        onPastPaperStatusChange(profileData.past_paper_status);
        setPastPaperDraft(profileData.past_paper_status);
      }
      if (profileData.learning_stats) onLearningStatsChange(profileData.learning_stats);
    } catch {
      // 后端不可用时仅更新本地
      onProfileChange(draft);
    }
    onAppearanceChange(appearanceDraft.themeMode, appearanceDraft.fontSize);
    try {
      await saveModelConfig();
      if (contextLimit !== (tokenUsage.context_limit || DEFAULT_CONTEXT_LIMIT)) {
        await saveContextLimit();
      }
    } finally {
      onClose();
    }
  };
  const openCustomProviderForm = () => {
    setCustomProviderOpen(true);
    setSaveState("请填写自定义供应商信息。");
  };
  const cancelCustomProviderForm = () => {
    setCustomProviderOpen(false);
    setCustomProviderDraft({ name: "", base_url: "", default_model: "" });
    setSaveState("");
  };
  const handleAddCustomProvider = async () => {
    const name = customProviderDraft.name.trim();
    const baseUrl = customProviderDraft.base_url.trim();
    const defaultModel = customProviderDraft.default_model.trim();
    if (!name || !baseUrl || !defaultModel) {
      setSaveState("请填写供应商名称、Base URL（基础网址）和默认模型。");
      return;
    }
    setCustomProviderSaving(true);
    try {
      const data = await apiPost<{ provider: ProviderOption; providers: ProviderOption[] }>("/api/config/providers/custom", {
        name,
        base_url: baseUrl,
        default_model: defaultModel
      });
      const nextProviders = normalizeProviders(data.providers);
      const nextProvider = nextProviders.find((item) => item.id === data.provider.id) || normalizeProviders([data.provider])[0];
      onProvidersChange(nextProviders);
      setModelDraft({
        ...modelDraft,
        provider_id: nextProvider.id,
        base_url: nextProvider.base_url,
        api_format: nextProvider.api_format,
        model: nextProvider.model,
        thinking_level: defaultThinkingLevelForModel(nextProvider, nextProvider.model),
        thinking_level_options: thinkingOptionsForModel(nextProvider, nextProvider.model),
        vision: modelSupportsVision(nextProvider, nextProvider.model)
      });
      setCustomProviderDraft({ name: "", base_url: "", default_model: "" });
      setCustomProviderOpen(false);
      setSaveState(`提供商 [${name}] 添加成功，已切换到该供应商。`);
    } catch (e) {
      setSaveState(`添加失败: ${e instanceof Error ? e.message : e}`);
    } finally {
      setCustomProviderSaving(false);
    }
  };
  const openThinkingLevelForm = () => {
    setThinkingLevelFormOpen(true);
    setThinkingLevelError("");
    setSaveState("");
  };
  const cancelThinkingLevelForm = () => {
    setThinkingLevelFormOpen(false);
    setThinkingLevelDraft({ label: "", api_value: "" });
    setThinkingLevelError("");
  };
  const handleAddThinkingLevel = () => {
    const label = thinkingLevelDraft.label.trim();
    const apiValue = thinkingLevelDraft.api_value.trim();
    if (!label) {
      setThinkingLevelError("请填写显示名称。");
      return;
    }
    const id = slugifyThinkingLevelId(apiValue || label);
    if (!id) {
      setThinkingLevelError("思考等级标识无效，请换一个名称或原生值。");
      return;
    }
    if (modelThinkingOptions.some((option) => option.id === id)) {
      setThinkingLevelError("当前模型已有同名思考等级。");
      return;
    }
    const nextOptions = [...modelThinkingOptions, { id, label, api_value: apiValue, custom: true }];
    setModelDraft({
      ...modelDraft,
      thinking_level: id,
      thinking_level_options: nextOptions
    });
    setThinkingLevelDraft({ label: "", api_value: "" });
    setThinkingLevelFormOpen(false);
    setThinkingLevelError("");
    setSaveState("已加入当前模型的自定义思考等级，保存模型配置后生效。");
  };
  const handleRemoveThinkingLevel = (optionId: string) => {
    const target = modelThinkingOptions.find((option) => option.id === optionId);
    if (!target?.custom) return;
    const nextOptions = modelThinkingOptions.filter((option) => option.id !== optionId);
    const nextLevel = thinkingLevelForOptions(
      nextOptions,
      modelDraft.thinking_level === optionId ? "" : modelDraft.thinking_level,
      defaultThinkingLevelForModel(provider, modelDraft.model)
    );
    setModelDraft({
      ...modelDraft,
      thinking_level: nextLevel,
      thinking_level_options: nextOptions
    });
    setThinkingLevelError("");
    setSaveState("已删除自定义思考等级，保存模型配置后生效。");
  };
  const resetDefaults = async () => {
    if (!window.confirm("确认恢复默认设置？模型、个性化、学习目标和自定义提供商会恢复默认，学习会话不会删除。")) return;
    const data = await apiPost<{ profile: Profile; model_config: ModelConfig; providers: ProviderOption[] }>("/api/settings/defaults", {});
    const nextProfile = data.profile;
    const nextModel = normalizeModelConfig(data.model_config);
    const nextProviders = normalizeProviders(data.providers);
    setDraft(nextProfile);
    setModelDraft({ ...nextModel, api_key: "" });
    setReviewIntensity(3);
    setAppearanceDraft({ themeMode: "system", fontSize: 16 });
    setPastPaperDraft(DEFAULT_PAST_PAPER_STATUS);
    onProfileChange(nextProfile);
    onModelConfigChange(nextModel);
    onProvidersChange(nextProviders);
    onPastPaperStatusChange(DEFAULT_PAST_PAPER_STATUS);
    onAppearanceChange("system", 16);
    setSaveState("已恢复默认设置。");
  };
  const currentExamOption = examOptions.find((item) => item.id === draft.exam_id) || examOptions[0];
  const tokenMax = Math.max(tokenUsage.total || 0, 1);
  const todayUsage = tokenUsage.today || { input: 0, output: 0, total: 0, calls: 0 };
  const yesterdayUsage = tokenUsage.yesterday || { input: 0, output: 0, total: 0, calls: 0 };
  const weekUsage = tokenUsage.last_7_days || { input: 0, output: 0, total: 0, calls: 0 };
  const monthUsage = tokenUsage.current_month || { input: 0, output: 0, total: 0, calls: 0 };
  const last30Usage = tokenUsage.last_30_days || { input: 0, output: 0, total: 0, calls: 0 };
  const maxDailyTokens = Math.max(...(tokenUsage.daily_activity || []).map((day) => day.tokens), 1);
  const saveContextLimit = async () => {
    const data = await apiPost<{ token_usage: TokenUsage }>("/api/context/settings", {
      max_tokens: contextLimit
    });
    onTokenUsageChange(data.token_usage);
    setSaveState("上下文容量已保存。");
  };
  const migrateQuestionDatabaseFolder = async () => {
    setDataPathMessage("正在更新题目数据库目录...");
    try {
      const data = await apiPost<{ data_paths: DataPathsStatus; message?: string }>("/api/data-paths/question-db-folder", {
        folder: questionDbFolder,
        migrate: migrateQuestionDb,
        overwrite: overwriteQuestionDb
      });
      const nextPaths = { ...DEFAULT_DATA_PATHS, ...data.data_paths };
      setDataPathDraft(nextPaths);
      setQuestionDbFolder(nextPaths.user_data_dir || questionDbFolder);
      onDataPathsChange(nextPaths);
      setDataPathMessage(data.message || "题目数据库目录已更新。");
    } catch (err) {
      setDataPathMessage(err instanceof Error ? err.message : "题目数据库目录更新失败");
    }
  };
  const chooseQuestionDatabaseFolder = async () => {
    setDataPathMessage("正在打开文件夹选择器...");
    try {
      const data = await apiPost<{ selected: boolean; folder: string; message?: string }>("/api/data-paths/select-folder", {
        initial_folder: questionDbFolder || dataPathDraft.user_data_dir || "",
        title: "选择题目数据库文件夹"
      });
      if (data.selected && data.folder) {
        setQuestionDbFolder(data.folder);
      }
      setDataPathMessage(data.message || (data.selected ? "已选择文件夹。" : "未选择文件夹。"));
    } catch (err) {
      setDataPathMessage(err instanceof Error ? err.message : "文件夹选择器打开失败");
    }
  };
  const saveMinerUConfig = async (clearToken = false) => {
    setMineruMessage(clearToken ? "正在清除 MinerU token..." : "正在保存 MinerU token...");
    try {
      const data = await apiPost<{ mineru_config: MinerUConfig }>("/api/mineru-config", {
        token: clearToken ? "" : mineruToken,
        clear_token: clearToken
      });
      const nextConfig = { ...DEFAULT_MINERU_CONFIG, ...data.mineru_config };
      setMineruDraft(nextConfig);
      onMinerUConfigChange(nextConfig);
      setMineruToken("");
      setMineruMessage(clearToken ? "MinerU token 已清除。" : "MinerU token 已保存。");
    } catch (err) {
      setMineruMessage(err instanceof Error ? err.message : "MinerU token 保存失败");
    }
  };
  const toggleAgentPermission = (featureId: string) => {
    const enabled = new Set(permissionDraft.enabled_feature_ids);
    if (enabled.has(featureId)) {
      enabled.delete(featureId);
    } else {
      enabled.add(featureId);
    }
    const nextIds = permissionDraft.features
      .map((feature) => feature.id)
      .filter((featureIdItem) => enabled.has(featureIdItem));
    setPermissionDraft({
      enabled_feature_ids: nextIds,
      features: permissionDraft.features.map((feature) => ({
        ...feature,
        enabled: enabled.has(feature.id)
      }))
    });
    setPermissionMessage("");
  };
  const saveAgentPermissions = async () => {
    setPermissionMessage("正在保存权限...");
    try {
      const data = await apiPost<{ agent_permissions: AgentSettingsPermissionsStatus }>("/api/settings/agent-permissions", {
        enabled_feature_ids: permissionDraft.enabled_feature_ids
      });
      setPermissionDraft(data.agent_permissions);
      onAgentPermissionsChange(data.agent_permissions);
      setPermissionMessage("Agent 设置权限已保存。");
    } catch (err) {
      setPermissionMessage(err instanceof Error ? err.message : "权限保存失败");
    }
  };
  const settingTabs = [
    { id: "model", label: "模型", icon: GearSix },
    { id: "exam", label: "考试", icon: Target },
    { id: "syllabus", label: "考纲", icon: ListBullets },
    { id: "tokens", label: "令牌", icon: Brain },
    { id: "data", label: "数据", icon: Database },
    { id: "permissions", label: "权限", icon: ShieldCheck },
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
                    {providers.filter((provider) => provider.id !== "mock").map((provider) => (
                      <option key={provider.id} value={provider.id}>{provider.label}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="inline-action square-action"
                    onClick={openCustomProviderForm}
                    title="新增自定义提供商"
                    aria-label="新增自定义提供商"
                  >
                    <Plus size={18} />
                  </button>
                </div>
                {customProviderOpen && (
                  <div className="custom-provider-form">
                    <label className="field-label">
                      <span>供应商名称</span>
                      <input
                        value={customProviderDraft.name}
                        onChange={(event) => setCustomProviderDraft({ ...customProviderDraft, name: event.target.value })}
                        placeholder="例如：MyProvider"
                      />
                    </label>
                    <label className="field-label">
                      <span>Base URL（基础网址）</span>
                      <input
                        value={customProviderDraft.base_url}
                        onChange={(event) => setCustomProviderDraft({ ...customProviderDraft, base_url: event.target.value })}
                        placeholder="https://api.example.com/v1"
                      />
                    </label>
                    <label className="field-label">
                      <span>默认模型</span>
                      <input
                        value={customProviderDraft.default_model}
                        onChange={(event) => setCustomProviderDraft({ ...customProviderDraft, default_model: event.target.value })}
                        placeholder="provider-model-name"
                      />
                    </label>
                    <div className="inline-row form-actions">
                      <button type="button" className="inline-action" onClick={cancelCustomProviderForm} disabled={customProviderSaving}>取消</button>
                      <button
                        type="button"
                        className="inline-action primary-inline"
                        onClick={() => void handleAddCustomProvider()}
                        disabled={customProviderSaving}
                      >
                        {customProviderSaving ? "添加中..." : "添加供应商"}
                      </button>
                    </div>
                  </div>
                )}
                <input
                  value={modelDraft.base_url}
                  onChange={(event) => setModelDraft({ ...modelDraft, base_url: event.target.value })}
                  placeholder={provider.base_url || "供应商 Base URL（基础网址）"}
                />
                <label className="field-label">
                  <span>API 格式</span>
                  <select
                    value={modelDraft.api_format || provider.api_format || "openai-chat-completions"}
                    onChange={(event) => setModelDraft({ ...modelDraft, api_format: event.target.value })}
                  >
                    {API_FORMAT_OPTIONS.map((option) => (
                      <option key={option.id} value={option.id} disabled={option.disabled}>
                        {option.label}{option.note ? ` · ${option.note}` : ""}
                      </option>
                    ))}
                  </select>
                  <small>模型调用与模型列表刷新会按这里的接口格式选择 endpoint（端点）。</small>
                </label>
                <input
                  value={modelDraft.api_key || ""}
                  onChange={(event) => setModelDraft({ ...modelDraft, api_key: event.target.value })}
                  placeholder={modelDraft.has_api_key ? "API Key（接口密钥）已配置，留空则不覆盖" : "API Key（接口密钥）"}
                  type="password"
                  autoComplete="off"
                />
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={Boolean(modelDraft.vision)}
                    onChange={(event) => setModelDraft({ ...modelDraft, vision: event.target.checked })}
                  />
                  <span>
                    <strong>当前模型支持图片输入</strong>
                    <small>开启后，聊天栏拖入图片会直接发给当前模型；关闭时图片会先走 MinerU/本地 OCR 提取文本。</small>
                  </span>
                </label>
                <label className="field-label">
                  <span>模型列表</span>
                  <div className="field-with-button">
                    <select value={modelDraft.model} onChange={(event) => chooseModel(event.target.value)}>
                      {modelOptions.map((model) => (
                        <option key={model.id} value={model.id}>{modelOptionLabel(model)}{model.visible === false ? "（已隐藏）" : ""}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="inline-action square-action"
                      onClick={() => void refreshProviderModels()}
                      disabled={modelRefreshing}
                      title="从 API 获取可调用模型"
                      aria-label="从 API 获取可调用模型"
                    >
                      <ArrowClockwise size={18} />
                    </button>
                  </div>
                  <small>刷新会调用当前供应商的模型列表接口，把返回的可调用模型写入下拉。隐藏的模型不会出现在聊天栏快捷模型选择中。</small>
                </label>
                <div className="model-visibility-list" aria-label="模型栏显示设置">
                  {modelOptions.map((model) => {
                    const visible = model.visible !== false;
                    return (
                      <div className="model-visibility-row" key={model.id}>
                        <div>
                          <strong>{modelOptionLabel(model)}</strong>
                          <span>
                            {model.context_tokens ? `${formatCompactNumber(model.context_tokens)} 上下文` : "上下文未知"}
                            {" · "}
                            {model.vision ? "支持图片" : "文本模型"}
                            {" · "}
                            {model.reasoning?.levels?.length ? `${model.reasoning.levels.length} 个思考档位` : "无思考档位"}
                          </span>
                        </div>
                        <button
                          type="button"
                          className="inline-action compact-action"
                          onClick={() => void toggleModelVisibility(model.id, !visible)}
                          title={visible ? "从聊天栏隐藏" : "显示到聊天栏"}
                        >
                          {visible ? <EyeSlash size={16} /> : <Eye size={16} />}
                          {visible ? "隐藏" : "显示"}
                        </button>
                      </div>
                    );
                  })}
                </div>
                {modelRefreshMessage && <p className="hint strong-hint">{modelRefreshMessage}</p>}
                <div className="settings-summary-line">图片解析：{modelDraft.vision ? "聊天栏图片直传当前模型；试卷、截图和文件抽取仍可走 MinerU。" : "聊天栏图片、试卷、截图和文件抽取优先走 MinerU，失败后按文件类型尝试本地兜底。"}</div>
                <div className="mineru-config">
                  <label className="field-label">
                    <span>MinerU token（用户信息）</span>
                    <input
                      value={mineruToken}
                      onChange={(event) => setMineruToken(event.target.value)}
                      placeholder={mineruDraft.has_token ? `已配置：${mineruDraft.token_preview}` : "粘贴 MinerU 官方 token"}
                      type="password"
                      autoComplete="off"
                    />
                    <small>保存到本地 .env 的 {mineruDraft.env_key}；接口不会返回 token 明文。</small>
                  </label>
                  <div className="inline-row wrap-row">
                    <a className="inline-link" href={mineruDraft.token_url} target="_blank" rel="noreferrer">获取官方 token</a>
                    <a className="inline-link" href={mineruDraft.docs_url} target="_blank" rel="noreferrer">查看 API 文档</a>
                    <button className="inline-action" type="button" onClick={() => void saveMinerUConfig(false)}>保存 MinerU token</button>
                    {mineruDraft.has_token && (
                      <button className="inline-action" type="button" onClick={() => void saveMinerUConfig(true)}>清除 token</button>
                    )}
                  </div>
                  {mineruMessage && <p className="hint strong-hint">{mineruMessage}</p>}
                </div>
                <div className="reasoning-config">
                  <div className="inline-row">
                    {modelThinkingOptions.length > 0 ? (
                      <select
                        value={selectedModelThinkingLevel}
                        onChange={(event) => setModelDraft({ ...modelDraft, thinking_level: event.target.value as ThinkingLevel })}
                      >
                        {modelThinkingOptions.map((option) => (
                          <option key={option.id} value={option.id}>思考等级：{option.label}</option>
                        ))}
                      </select>
                    ) : (
                      <span className="settings-summary-line">当前模型未配置思考等级</span>
                    )}
                    {!thinkingLevelFormOpen && (
                      <button type="button" className="inline-action" onClick={openThinkingLevelForm}>添加自定义思考等级</button>
                    )}
                  </div>
                  {modelThinkingOptions.some((option) => option.custom) && (
                    <div className="thinking-level-list" aria-label="自定义思考等级">
                      {modelThinkingOptions.filter((option) => option.custom).map((option) => (
                        <span className="thinking-level-item" key={option.id}>
                          <span>{option.label}</span>
                          <button
                            type="button"
                            className="icon-button mini-icon-button"
                            onClick={() => handleRemoveThinkingLevel(option.id)}
                            title={`删除 ${option.label}`}
                            aria-label={`删除 ${option.label}`}
                          >
                            <X size={13} />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                  {thinkingLevelFormOpen && (
                    <div className="custom-provider-form thinking-level-form">
                      <label className="field-label">
                        <span>显示名称</span>
                        <input
                          value={thinkingLevelDraft.label}
                          onChange={(event) => setThinkingLevelDraft({ ...thinkingLevelDraft, label: event.target.value })}
                          placeholder="例如：最高"
                        />
                      </label>
                      <label className="field-label">
                        <span>API（接口）原生值</span>
                        <input
                          value={thinkingLevelDraft.api_value}
                          onChange={(event) => setThinkingLevelDraft({ ...thinkingLevelDraft, api_value: event.target.value })}
                          placeholder="例如：xhigh、max、enabled"
                        />
                      </label>
                      <div className="inline-row form-actions">
                        <button type="button" className="inline-action" onClick={cancelThinkingLevelForm}>取消</button>
                        <button type="button" className="inline-action primary-inline" onClick={handleAddThinkingLevel}>添加</button>
                      </div>
                      {thinkingLevelError && <p className="hint strong-hint">{thinkingLevelError}</p>}
                    </div>
                  )}
                </div>
                <div className="context-setting-row model-context-row">
                  <label className="field-label">
                    <span>上下文容量上限</span>
                    <input
                      type="number"
                      min="1000"
                      max="10000000"
                      step="1000"
                      value={contextLimit}
                      onChange={(event) => setContextLimit(Number(event.target.value || DEFAULT_CONTEXT_LIMIT))}
                    />
                    <small>默认 1,000,000；聊天栏右下角圆圈会按这个上限显示占用。</small>
                  </label>
                  <button className="inline-action" onClick={() => void saveContextLimit()}>保存容量</button>
                </div>
                <div className="inline-row wrap-row">
                  <button className="inline-action" onClick={() => void saveModelConfig()}>保存模型配置</button>
                  <button className="inline-action primary-inline" onClick={() => void saveDefaultModelConfig()}>设为默认模型</button>
                </div>
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
                <label className="field-label">
                  <span>考试时间</span>
                  <input
                    type="datetime-local"
                    value={toDateTimeLocalValue(draft.deadline)}
                    onChange={(event) => setDraft({ ...draft, deadline: event.target.value || null })}
                    onInput={(event) => setDraft({ ...draft, deadline: event.currentTarget.value || null })}
                  />
                  <small>{draft.deadline ? `剩余：${countdownText(draft.deadline)}` : "用于长期面板倒计时，可为空。"}</small>
                </label>
                {draft.exam_id === "custom" && (
                  <div className="custom-exam-grid">
                    <input value={customExam.name} onChange={(event) => setCustomExam({ ...customExam, name: event.target.value })} placeholder="自定义考试名称" />
                    <input value={customExam.target_language} onChange={(event) => setCustomExam({ ...customExam, target_language: event.target.value })} placeholder="目标语言" />
                    <select value={customExam.syllabus_mode} onChange={(event) => setCustomExam({ ...customExam, syllabus_mode: event.target.value })}>
                      <option value="auto">考纲网址自动下载</option>
                      <option value="manual">手动导入本地文件</option>
                    </select>
                    <input value={customExam.syllabus_url} onChange={(event) => setCustomExam({ ...customExam, syllabus_url: event.target.value })} placeholder="官方考纲网址" />
                    <input value={customExam.paper_source_url} onChange={(event) => setCustomExam({ ...customExam, paper_source_url: event.target.value })} placeholder="历年真题来源网站" />
                    <input value={customExam.default_question_types} onChange={(event) => setCustomExam({ ...customExam, default_question_types: event.target.value })} placeholder="题型清单，用逗号分隔" />
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
            {activeSettingsTab === "syllabus" && (
              <SettingSection title="历年真题与题型">
                <div className="syllabus-current">
                  <strong>{pastPaperDraft.current_papers.length || 0} 套</strong>
                  <span>当前参考：{pastPaperDraft.current_papers.map((paper) => paper.year || paper.title).join("、") || "暂无"}</span>
                </div>
                <div className="settings-summary-line">{pastPaperDraft.description}</div>
                <div className="inline-row">
                  <button className="inline-action" onClick={() => void searchImportPastPapers()}><Sparkle size={16} /> 大模型联网搜索导入</button>
                  {pastPaperDraft.source_website && <a className="inline-link" href={pastPaperDraft.source_website} target="_blank" rel="noreferrer">打开来源网站</a>}
                </div>
                <div className="paper-list">
                  {pastPaperDraft.papers.map((paper) => (
                    <div className="check-row paper-row" key={paper.id}>
                      <label className="paper-check">
                        <input
                          type="checkbox"
                          checked={pastPaperDraft.selected_paper_ids.includes(paper.id)}
                          onChange={() => void togglePastPaper(paper.id)}
                        />
                        <span>
                          <strong>{paper.year || "未知年份"} - {paper.title}</strong>
                          <small>{paper.source_url || paper.local_path || "未记录来源"} · {paper.trusted_level}</small>
                          <small>原始：{paper.metadata?.raw_path || paper.local_path || "未保存"} · 解析：{paper.metadata?.parsed_path || "未生成"} · 状态：{paper.metadata?.parse_status || "未知"}</small>
                          {paper.metadata?.parse_error && <small>解析问题：{paper.metadata.parse_error}</small>}
                        </span>
                      </label>
                      <button className="inline-action compact-action" onClick={() => void parsePastPaper(paper.id)}>重新解析</button>
                    </div>
                  ))}
                  {!pastPaperDraft.papers.length && <p className="hint">暂无真题试卷索引，可手动导入或使用联网搜索导入。</p>}
                </div>
                <div className="inline-row">
                  <button type="button" className="inline-action" onClick={() => setPaperImportOpen((open) => !open)}>
                    <Plus size={16} /> {paperImportOpen ? "收起加入试卷" : "加入试卷"}
                  </button>
                </div>
                {paperImportOpen && (
                  <div className="paper-import-grid">
                    <div
                      className={`drop-zone paper-import-drop ${paperImportDragActive ? "drag-over" : ""}`}
                      onDragEnter={(event) => {
                        if (event.dataTransfer.types.includes("Files")) setPaperImportDragActive(true);
                      }}
                      onDragOver={(event) => {
                        if (event.dataTransfer.types.includes("Files")) event.preventDefault();
                      }}
                      onDragLeave={(event) => {
                        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                          setPaperImportDragActive(false);
                        }
                      }}
                      onDrop={handlePastPaperDrop}
                    >
                      <FolderOpen size={20} />
                      <strong>{paperImportFile ? paperImportFile.name : "拖入或选择试卷文件"}</strong>
                      <span>PDF / DOCX / TXT / MD / 图片</span>
                      <input
                        ref={paperFileInputRef}
                        className="hidden-file-input"
                        type="file"
                        accept=".pdf,.doc,.docx,.txt,.md,.markdown,image/*"
                        onChange={handlePastPaperFileChange}
                      />
                      <button type="button" className="drop-zone-action" onClick={() => paperFileInputRef.current?.click()}>
                        <FolderOpen size={16} /> 选择文件
                      </button>
                    </div>
                    <input value={paperImportDraft.title} onChange={(event) => setPaperImportDraft({ ...paperImportDraft, title: event.target.value })} placeholder="试卷标题，例如：2025 年 6 月英语四级真题" />
                    <input value={paperImportDraft.year} onChange={(event) => setPaperImportDraft({ ...paperImportDraft, year: event.target.value })} placeholder="年份" inputMode="numeric" />
                    <input value={paperImportDraft.source_url} onChange={(event) => setPaperImportDraft({ ...paperImportDraft, source_url: event.target.value })} placeholder="来源网站或网页 URL" />
                    <input value={paperImportDraft.local_path} onChange={(event) => setPaperImportDraft({ ...paperImportDraft, local_path: event.target.value })} placeholder="本地试卷文件路径，可为空" />
                    <input value={paperImportDraft.question_types} onChange={(event) => setPaperImportDraft({ ...paperImportDraft, question_types: event.target.value })} placeholder="试卷题型，用逗号分隔" />
                    <textarea value={paperImportDraft.raw_text} onChange={(event) => setPaperImportDraft({ ...paperImportDraft, raw_text: event.target.value })} placeholder="可直接粘贴试卷文本或已提取的 Markdown；填写后会保存到 papers/<考试>/raw 并解析" />
                    <textarea value={paperImportDraft.summary} onChange={(event) => setPaperImportDraft({ ...paperImportDraft, summary: event.target.value })} placeholder="风格摘要、题量、分值、注意事项；不要粘贴大段受版权限制的完整真题原文" />
                    <div className="paper-import-actions">
                      <button type="button" className="inline-action" onClick={() => void draftPastPaperImport()}><Sparkle size={16} /> 解析草稿</button>
                      <button type="button" className="inline-action" onClick={() => void importPastPaper()}><Plus size={16} /> 确认加入试卷</button>
                      <button type="button" className="inline-action" onClick={() => setPaperImportOpen(false)}>收起</button>
                    </div>
                  </div>
                )}
                <div className="question-type-grid">
                  {pastPaperDraft.question_types.map((type) => (
                    <label className="check-row" key={type.id}>
                      <input
                        type="checkbox"
                        checked={pastPaperDraft.enabled_question_type_ids.includes(type.id)}
                        onChange={() => void toggleQuestionType(type.id)}
                      />
                      <span>
                        <strong>{type.label}</strong>
                        <small>{type.description}</small>
                      </span>
                    </label>
                  ))}
                </div>
                <p className="hint">生成题组时只会使用已勾选题型，并把当前选中的真题试卷索引写入模型上下文和题目来源引用。</p>
                {pastPaperMessage && <p className="hint strong-hint">{pastPaperMessage}</p>}
              </SettingSection>
            )}
            {activeSettingsTab === "tokens" && (
              <SettingSection title="使用统计">
                <div className="usage-dashboard">
                  {[
                    ["今日 token", formatCompactNumber(todayUsage.total), `${formatNumber(todayUsage.calls)} 次调用`],
                    ["近 7 天", formatCompactNumber(weekUsage.total), `${formatNumber(weekUsage.calls)} 次调用`],
                    ["近 30 天", formatCompactNumber(last30Usage.total), `${formatNumber(last30Usage.calls)} 次调用`],
                    ["本月 token", formatCompactNumber(monthUsage.total), `${formatNumber(monthUsage.calls)} 次调用`],
                    ["累计 token", formatCompactNumber(tokenUsage.total), `${formatNumber(tokenUsage.total_calls)} 次调用`],
                    ["最常用模型", tokenUsage.most_used_model || "暂无", `${Math.round((tokenUsage.most_used_model_percent || 0) * 100)}%`]
                  ].map(([label, value, detail]) => (
                    <div className="usage-card" key={label}>
                      <span>{label}</span>
                      <strong>{value}</strong>
                      <small>{detail}</small>
                    </div>
                  ))}
                </div>
                <div className="token-dashboard">
                  <div className="token-hero">
                    <strong>{formatCompactNumber(todayUsage.total)}</strong>
                    <span>今日 token（令牌）</span>
                    <small>昨日 {formatCompactNumber(yesterdayUsage.total)} · 平均 {formatCompactNumber(tokenUsage.average_tokens_per_call)} / 调用</small>
                  </div>
                  {[
                    ["今日输入", todayUsage.input, todayUsage.total || 1],
                    ["今日输出", todayUsage.output, todayUsage.total || 1],
                    ["累计输入", tokenUsage.input, tokenMax],
                    ["累计输出", tokenUsage.output, tokenMax],
                    ["当前上下文估算", tokenUsage.estimated_current_context, tokenUsage.context_limit || DEFAULT_CONTEXT_LIMIT]
                  ].map(([label, value, maxValue]) => (
                    <div className="token-meter" key={label}>
                      <div><span>{label}</span><strong>{formatNumber(Number(value))}</strong></div>
                      <div className="thin-progress compact"><span style={{ width: `${Math.max(8, Math.min(100, (Number(value) / Number(maxValue || 1)) * 100))}%` }} /></div>
                    </div>
                  ))}
                </div>
                <div className="activity-panel">
                  <div className="activity-head">
                    <strong>近 30 天活动</strong>
                    <span>较少</span>
                    <i /><i /><i /><i /><i />
                    <span>较多</span>
                  </div>
                  <div className="activity-grid">
                    {(tokenUsage.daily_activity || []).map((item) => {
                      const level = item.tokens ? Math.max(1, Math.ceil((item.tokens / maxDailyTokens) * 5)) : 0;
                      return <span key={item.date} className={`activity-cell level-${level}`} title={`${item.date}：${formatNumber(item.tokens)} tokens，${formatNumber(item.calls)} 次调用`} />;
                    })}
                  </div>
                </div>
                <div className="usage-ledger-grid">
                  <div className="model-usage-panel">
                    <div className="ledger-head"><strong>模型排行</strong><span>按 token 排序</span></div>
                    {(tokenUsage.model_breakdown || []).map((item) => (
                      <div className="model-usage-row" key={`${item.provider_id}-${item.model}`}>
                        <div>
                          <strong>{item.model}</strong>
                          <span>{item.provider_id} · 输入 {formatCompactNumber(item.input)} / 输出 {formatCompactNumber(item.output)} · {item.calls} 次</span>
                        </div>
                        <small>{Math.round(item.percent * 100)}%</small>
                      </div>
                    ))}
                    {!(tokenUsage.model_breakdown || []).length && <p className="hint">暂无模型调用记录。</p>}
                  </div>
                  <div className="model-usage-panel">
                    <div className="ledger-head"><strong>Provider（供应商）</strong><span>调用来源</span></div>
                    {(tokenUsage.provider_breakdown || []).map((item) => (
                      <div className="model-usage-row" key={item.provider_id}>
                        <div>
                          <strong>{item.provider_id}</strong>
                          <span>{formatCompactNumber(item.tokens)} tokens · {item.calls} 次调用</span>
                        </div>
                        <small>{Math.round(item.percent * 100)}%</small>
                      </div>
                    ))}
                    {!(tokenUsage.provider_breakdown || []).length && <p className="hint">暂无供应商记录。</p>}
                  </div>
                </div>
                <div className="usage-ledger-grid">
                  <div className="model-usage-panel">
                    <div className="ledger-head"><strong>任务类型</strong><span>Agent 调用分布</span></div>
                    {(tokenUsage.task_breakdown || []).map((item) => (
                      <div className="model-usage-row" key={item.task_type}>
                        <div>
                          <strong>{item.task_type}</strong>
                          <span>{formatCompactNumber(item.tokens)} tokens · {item.calls} 次调用</span>
                        </div>
                        <small>{Math.round(item.percent * 100)}%</small>
                      </div>
                    ))}
                    {!(tokenUsage.task_breakdown || []).length && <p className="hint">暂无任务记录。</p>}
                  </div>
                  <div className="model-usage-panel">
                    <div className="ledger-head"><strong>账户概览</strong><span>本地统计</span></div>
                    {[
                      ["会话数量", tokenUsage.sessions_total, "已创建会话"],
                      ["消息数量", tokenUsage.messages_total, "主会话消息"],
                      ["活跃天数", tokenUsage.active_days, "有学习记录的日期"],
                      ["连续天数", tokenUsage.current_streak_days, "按本地日期计算"],
                      ["平均延迟", tokenUsage.average_latency_ms, "毫秒"]
                    ].map(([label, value, detail]) => (
                      <div className="model-usage-row" key={label}>
                        <div>
                          <strong>{label}</strong>
                          <span>{detail}</span>
                        </div>
                        <small>{formatNumber(Number(value))}</small>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="recent-call-table">
                  <div className="ledger-head"><strong>最近调用明细</strong><span>最近 24 条</span></div>
                  <div className="recent-call-head">
                    <span>时间</span><span>任务</span><span>模型</span><span>输入</span><span>输出</span><span>延迟</span>
                  </div>
                  {(tokenUsage.recent_calls || []).map((call) => (
                    <div className="recent-call-row" key={call.id}>
                      <span>{call.created_at}</span>
                      <span>{call.agent_name} / {call.task_type}</span>
                      <span>{call.provider_id}:{call.model}</span>
                      <span>{formatNumber(call.input_tokens)}</span>
                      <span>{formatNumber(call.output_tokens)}</span>
                      <span>{formatNumber(call.latency_ms)} ms</span>
                    </div>
                  ))}
                  {!(tokenUsage.recent_calls || []).length && <p className="hint">暂无调用明细。</p>}
                </div>
              </SettingSection>
            )}
            {activeSettingsTab === "data" && (
              <SettingSection title="题目数据库">
                <div className="data-path-grid">
                  <div>
                    <span>当前数据库</span>
                    <strong>{dataPathDraft.db_path || "未初始化"}</strong>
                  </div>
                  <div>
                    <span>用户数据目录</span>
                    <strong>{dataPathDraft.user_data_dir || "默认目录"}</strong>
                  </div>
                  <div>
                    <span>测试数据目录</span>
                    <strong>{dataPathDraft.test_data_dir || "测试数据"}</strong>
                  </div>
                  <div>
                    <span>数据库大小</span>
                    <strong>{formatBytes(dataPathDraft.db_size)}</strong>
                  </div>
                </div>
                <div className="usage-dashboard compact-dashboard">
                  {[
                    ["题目", dataPathDraft.counts.questions],
                    ["作答", dataPathDraft.counts.attempts],
                    ["会话", dataPathDraft.counts.study_sessions],
                    ["知识项", dataPathDraft.counts.knowledge_items],
                    ["考纲", dataPathDraft.counts.syllabus_sources],
                    ["真题索引", dataPathDraft.counts.exam_assets]
                  ].map(([label, value]) => (
                    <div className="usage-card compact-card" key={label}>
                      <span>{label}</span>
                      <strong>{formatNumber(Number(value))}</strong>
                    </div>
                  ))}
                </div>
                <label className="field-label">
                  <span>题目数据库文件夹</span>
                  <div className="field-with-button">
                    <input
                      value={questionDbFolder}
                      onChange={(event) => setQuestionDbFolder(event.target.value)}
                      placeholder="例如：D:\\LangDrill\\user-data"
                    />
                    <button
                      type="button"
                      className="inline-action square-action"
                      onClick={() => void chooseQuestionDatabaseFolder()}
                      title="选择文件夹"
                      aria-label="选择题目数据库文件夹"
                    >
                      <FolderOpen size={18} />
                    </button>
                  </div>
                  <small>数据库文件会写入该文件夹下的 data\\langdrill_agent.db。</small>
                </label>
                <div className="toggle-grid">
                  <label className="check-row">
                    <input
                      type="checkbox"
                      checked={migrateQuestionDb}
                      onChange={(event) => setMigrateQuestionDb(event.target.checked)}
                    />
                    <span>
                      <strong>迁移当前数据库</strong>
                      <small>关闭后会在目标文件夹初始化空库。</small>
                    </span>
                  </label>
                  <label className="check-row">
                    <input
                      type="checkbox"
                      checked={overwriteQuestionDb}
                      onChange={(event) => setOverwriteQuestionDb(event.target.checked)}
                    />
                    <span>
                      <strong>允许覆盖目标库</strong>
                      <small>覆盖前保留 pre-migration 备份。</small>
                    </span>
                  </label>
                </div>
                <div className="inline-row wrap-row">
                  <button className="inline-action primary-inline" onClick={() => void migrateQuestionDatabaseFolder()}>
                    迁移并使用此文件夹
                  </button>
                  <button
                    className="inline-action"
                    onClick={() => {
                      setQuestionDbFolder(dataPathDraft.user_data_dir || "");
                      setDataPathMessage("");
                    }}
                  >
                    恢复当前路径
                  </button>
                </div>
                {dataPathMessage && <p className="hint strong-hint">{dataPathMessage}</p>}
              </SettingSection>
            )}
            {activeSettingsTab === "permissions" && (
              <SettingSection title="Agent 设置权限">
                <p className="hint">这些权限只允许会话 Agent 先生成可确认草稿或打开对应设置动作；保存、迁移、密钥输入等关键步骤仍需要用户确认。</p>
                <div className="permission-grid">
                  {permissionDraft.features.map((feature) => (
                    <label className="check-row permission-row" key={feature.id}>
                      <input
                        type="checkbox"
                        checked={permissionDraft.enabled_feature_ids.includes(feature.id)}
                        onChange={() => toggleAgentPermission(feature.id)}
                      />
                      <span>
                        <strong>{feature.label}{feature.sensitive ? "（敏感）" : ""}</strong>
                        <small>{feature.description}</small>
                      </span>
                    </label>
                  ))}
                </div>
                <div className="inline-row wrap-row">
                  <button className="inline-action primary-inline" onClick={() => void saveAgentPermissions()}>保存权限</button>
                  <button
                    className="inline-action"
                    onClick={() => {
                      setPermissionDraft(agentPermissions);
                      setPermissionMessage("已恢复当前已保存权限。");
                    }}
                  >
                    恢复当前权限
                  </button>
                </div>
                {permissionMessage && <p className="hint strong-hint">{permissionMessage}</p>}
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
                <select aria-label="掌握度算法">
                  <option>掌握度算法：当前 V1（基础分数版）</option>
                  <option>间隔复习算法：FSRS（Free Spaced Repetition Scheduler，间隔复习调度器）预留，暂未启用</option>
                </select>
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
    provider_id: modelConfig.provider_id || DEFAULT_MODEL_CONFIG.provider_id,
    base_url: modelConfig.base_url || DEFAULT_MODEL_CONFIG.base_url,
    api_key: "",
    model: modelConfig.model || DEFAULT_MODEL_CONFIG.model,
    display_name: profile.display_name,
    target_language: profile.target_language || "英语",
    exam_id: profile.exam_id || "cet4",
    exam_name: profile.exam_name || "大学英语四级",
    deadline: profile.deadline || "",
    learning_goal: profile.learning_goal || "",
    learning_background: profile.learning_background || "",
    search_years: 3
  });
  const [errorMsg, setErrorMsg] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const provider = selectedProvider(providers, draft.provider_id);
  const modelOptions = modelOptionsFor(provider, draft.model);
  const chooseProvider = (providerId: string) => {
    const nextProvider = selectedProvider(providers, providerId);
    const nextModel = modelOptionsFor(nextProvider, nextProvider.model)[0]?.id || nextProvider.model || "";
    setDraft({
      ...draft,
      provider_id: nextProvider.id,
      base_url: nextProvider.base_url,
      model: nextModel
    });
  };

  const submit = async () => {
    setErrorMsg("");
    setIsSubmitting(true);
    try {
      const data = await apiPost<{ profile: Profile }>("/api/initialize", {
        ...draft,
        deadline: draft.deadline || null
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
          <label>供应商<select value={draft.provider_id} onChange={(event) => chooseProvider(event.target.value)}>{providers.filter((provider) => provider.id !== "mock").map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}</select></label>
          <label>Base URL（基础网址）<input value={draft.base_url} onChange={(event) => setDraft({ ...draft, base_url: event.target.value })} placeholder={provider.base_url || "供应商 Base URL（基础网址）"} /></label>
          <label>API Key（接口密钥）<input value={draft.api_key} onChange={(event) => setDraft({ ...draft, api_key: event.target.value })} placeholder="留空则不覆盖已有密钥" type="password" autoComplete="off" /></label>
          <label>模型选项<select value={draft.model} onChange={(event) => setDraft({ ...draft, model: event.target.value })}>{modelOptions.map((model) => <option key={model.id} value={model.id}>{modelOptionLabel(model)}</option>)}</select></label>
          <label>称呼<input value={draft.display_name} onChange={(event) => setDraft({ ...draft, display_name: event.target.value })} /></label>
          <label>目标语言<input value={draft.target_language} onChange={(event) => setDraft({ ...draft, target_language: event.target.value })} /></label>
          <label>目标考试<input value={draft.exam_name} onChange={(event) => setDraft({ ...draft, exam_name: event.target.value })} /></label>
          <label>考试时间<input type="datetime-local" value={toDateTimeLocalValue(draft.deadline)} onChange={(event) => setDraft({ ...draft, deadline: event.target.value })} onInput={(event) => setDraft({ ...draft, deadline: event.currentTarget.value })} /></label>
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
