// Mock API for Lang Drill Agent product site demo.
// 不连接真实后端，所有请求返回本地固定数据，让前端 1:1 演示不崩溃。
// 关键交互（chat / screenshot parse）返回演示性富内容。

import type {
  AgentSettingsPermissionsStatus,
  ChatImageAttachment,
  CustomModelDraft,
  DataPathsStatus,
  DailyPanel,
  ExamOption,
  LearningStats,
  Message,
  MinerUConfig,
  ModelConfig,
  PastPaperDraft,
  PastPaperStatus,
  Profile,
  ProviderOption,
  Question,
  ScreenshotImportResult,
  SessionItem,
  SkillsStatus,
  SyllabusStatus,
  TokenUsage
} from "./types";

// ---------- 默认常量（与 App.tsx 中保持一致，便于 UI 复用同一渲染逻辑） ----------

const DEFAULT_PANEL: DailyPanel = {
  date: new Date().toLocaleDateString("zh-CN"),
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
  daily_minutes: 35,
  learning_goal: "提升四级阅读与语境词汇辨识能力",
  learning_background: "曾系统背过四级核心词，但刷题时仍混淆近义辨析。",
  persona: "professional",
  global_user_prompt: ""
};

const FALLBACK_PROVIDERS: ProviderOption[] = [
  { id: "openai", label: "OpenAI GPT", kind: "openai-compatible", api_format: "openai-chat-completions", api_key_required: true, enabled: true, has_api_key: false, visible_in_picker: false, base_url: "https://api.openai.com/v1", model: "gpt-5.5", model_options: [{ id: "gpt-5.5", label: "gpt-5.5", vision: true }, { id: "gpt-5.4", label: "gpt-5.4", vision: true }] },
  { id: "claude", label: "Claude", kind: "anthropic", api_format: "anthropic-messages", api_key_required: true, enabled: true, has_api_key: false, visible_in_picker: false, base_url: "https://api.anthropic.com", model: "claude-sonnet-4.7", model_options: [{ id: "claude-sonnet-4.7", label: "claude-sonnet-4.7", vision: true }, { id: "claude-opus-4.7", label: "claude-opus-4.7", vision: true }] },
  { id: "deepseek", label: "DeepSeek", kind: "openai-compatible", api_format: "openai-chat-completions", api_key_required: true, enabled: true, has_api_key: false, visible_in_picker: false, base_url: "https://api.deepseek.com", model: "deepseek-v4-pro", model_options: [{ id: "deepseek-v4-pro", label: "deepseek-v4-pro", vision: false }, { id: "deepseek-v4-flash", label: "deepseek-v4-flash", vision: false }] },
  { id: "mimo", label: "Xiaomi MiMo", kind: "anthropic", api_format: "anthropic-messages", api_key_required: true, enabled: true, has_api_key: false, visible_in_picker: false, base_url: "https://api.xiaomimimo.com/anthropic", model: "mimo-v2.5-pro", model_options: [{ id: "mimo-v2.5", label: "mimo-v2.5", vision: false }, { id: "mimo-v2.5-pro", label: "mimo-v2.5-pro", vision: false }] }
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
  { id: "cet4", name: "英语四级", target_language: "英语", official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm", default_year: 2016, description: "大学英语四级，默认考试。" },
  { id: "cet6", name: "英语六级", target_language: "英语", official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm", default_year: 2016, description: "大学英语六级，按六级题型和难度组织。" },
  { id: "cft4", name: "法语四级", target_language: "法语", official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm", default_year: 2023, description: "大学法语四级，官方 2023 版考纲。" },
  { id: "cjt4", name: "日语四级", target_language: "日语", official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm", default_year: 2024, description: "大学日语四级，新版考纲 2024 年启用。" },
  { id: "cjt6", name: "日语六级", target_language: "日语", official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm", default_year: 2024, description: "大学日语六级，按更高难度日语题型和表达能力组织。" },
  { id: "ielts", name: "雅思", target_language: "英语", official_url: "https://ielts.org/take-a-test/test-types/ielts-academic-test", default_year: 2026, description: "雅思学术类考试结构，官方页面持续维护。" },
  { id: "toefl", name: "托福", target_language: "英语", official_url: "https://www.ets.org/toefl/test-takers/ibt/about/content.html", default_year: 2026, description: "托福网考考试结构，官方页面持续维护。" },
  { id: "gaokao-english", name: "高考英语", target_language: "英语", official_url: "https://www.moe.gov.cn/srcsite/A26/s8001/202006/t20200603_462199.html", default_year: 2020, description: "普通高中英语课程标准，按高考英语能力框架使用。" },
  { id: "custom", name: "添加自定义", target_language: "", official_url: "", default_year: null, description: "可配置考纲网址自动下载或手动导入。" }
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
  description: "CET-4（大学英语四级）真题按阅读、翻译和写作组织；听力题型暂预留。",
  source_website: "https://www.guojiya.cn/#exams",
  papers: [],
  selected_paper_ids: [],
  current_papers: [],
  question_types: [
    { id: "listening", label: "听力理解", description: "短篇新闻、长对话和听力篇章。", available: false, disabled: true, locked: true, disabled_reason: "暂未接入听力题和语音模型，此题型先预留，当前不可勾选。" },
    { id: "reading", label: "阅读理解", description: "选词填空、长篇匹配和仔细阅读。" },
    { id: "translation", label: "汉译英翻译", description: "段落翻译，偏中国文化与社会话题。" },
    { id: "writing", label: "短文写作", description: "议论文、应用文或图表类写作。" },
    { id: "context_vocabulary", label: "语境词汇", description: "从真题语境抽取搭配、词义和近义辨析。" }
  ],
  enabled_question_type_ids: ["reading", "translation", "writing", "context_vocabulary"]
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

const DEFAULT_CONTEXT_LIMIT = 1_000_000;

const DEFAULT_TOKEN_USAGE: TokenUsage = {
  input: 0, output: 0, total: 0, total_calls: 0,
  average_tokens_per_call: 0, average_latency_ms: 0,
  estimated_current_context: 0, context_limit: DEFAULT_CONTEXT_LIMIT,
  context_percent: 0, context_messages: 0, compressed_context_tokens: 0,
  sessions_total: 0, messages_total: 0, active_days: 0, current_streak_days: 0,
  most_used_model: "", most_used_model_percent: 0,
  today: { input: 0, output: 0, total: 0, calls: 0 },
  yesterday: { input: 0, output: 0, total: 0, calls: 0 },
  last_7_days: { input: 0, output: 0, total: 0, calls: 0 },
  last_30_days: { input: 0, output: 0, total: 0, calls: 0 },
  current_month: { input: 0, output: 0, total: 0, calls: 0 },
  model_breakdown: [], provider_breakdown: [], task_breakdown: [],
  daily_activity: [], recent_calls: []
};

const DEFAULT_DATA_PATHS: DataPathsStatus = {
  user_data_dir: "~/LangDrill/user-data",
  question_database_dir: "~/LangDrill/user-data",
  db_path: "~/LangDrill/user-data/langdrill_agent.db",
  log_dir: "~/LangDrill/logs",
  project_data_dir: "",
  test_data_dir: "",
  db_exists: true,
  db_size: 245760,
  counts: {
    study_sessions: 0, messages: 0, questions: 0, attempts: 0,
    knowledge_items: 0, branch_conversations: 0, branch_messages: 0,
    model_calls: 0, syllabus_sources: 0, exam_assets: 0
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
  enabled_feature_ids: [
    "screenshot_import", "learning_database", "past_paper_import",
    "web_search_import", "profile_exam", "context_settings"
  ],
  features: [
    { id: "screenshot_import", label: "截图导入与词表入库", description: "允许会话 Agent 触发截图/文件词表解析，把确认后的单词写入学习库并创建练习会话。", enabled: true, default_enabled: true },
    { id: "learning_database", label: "单词、题目与作答数据库", description: "允许会话 Agent 通过正式学习流程创建知识项、题目、作答记录和掌握度统计。", enabled: true, default_enabled: true },
    { id: "past_paper_import", label: "历年真题导入与题型", description: "允许会话 Agent 解析试卷信息，并在用户确认后填入真题导入表单。", enabled: true, default_enabled: true },
    { id: "web_search_import", label: "联网功能", description: "允许会话 Agent 打开或引用联网来源。该权限独立于拓展 Skills，默认开启。", enabled: true, default_enabled: true },
    { id: "profile_exam", label: "考试与学习目标", description: "允许会话 Agent 按用户确认的目标调整考试、截止时间和学习背景草稿。", enabled: true, default_enabled: true },
    { id: "context_settings", label: "上下文容量", description: "允许会话 Agent 帮助调整上下文容量上限和压缩相关设置。", enabled: true, default_enabled: true },
    { id: "model_config", label: "模型供应商与默认模型", description: "允许会话 Agent 帮助填写模型供应商、模型名、Base URL（基础网址）和能力开关。", enabled: false, sensitive: true, default_enabled: false },
    { id: "custom_models", label: "配置自定义模型", description: "允许会话 Agent 帮助整理自定义模型草稿；添加、删除和保存仍需用户在设置页确认。", enabled: false, sensitive: true, default_enabled: false },
    { id: "data_paths", label: "题目数据库目录", description: "允许会话 Agent 帮助填写题目数据库目录迁移设置；迁移前仍需用户确认。", enabled: false, sensitive: true, default_enabled: false },
    { id: "mineru_config", label: "MinerU token", description: "允许会话 Agent 帮助打开 MinerU 配置项；token 明文仍只能由用户输入。", enabled: false, sensitive: true, default_enabled: false }
  ],
  groups: [
    { id: "default_enabled", label: "默认开启的能力权限", feature_ids: ["screenshot_import", "learning_database", "past_paper_import", "web_search_import", "profile_exam", "context_settings"] },
    { id: "sensitive", label: "敏感设置权限", feature_ids: ["model_config", "custom_models", "data_paths", "mineru_config"] }
  ]
};

// Skills 占位：skill1 / skill2，路径虚构，不暴露真实主机位置
const DEFAULT_SKILLS_STATUS: SkillsStatus = {
  skills_roots: ["~/LangDrill/skills"],
  installed: [
    {
      id: "skill1",
      name: "skill1",
      label: "skill1",
      description: "演示用拓展 Skill 占位，可在设置页中切换启用状态。展示站不会真实加载该 Skill。",
      path: "~/LangDrill/skills/skill1",
      skill_file: "~/LangDrill/skills/skill1/SKILL.md",
      homepage: "",
      requires_api_key: false,
      requires_token: false,
      installed: true,
      enabled: true,
      builtin: false,
      locked: false,
      always_enabled: false,
      default_enabled: false,
      permission_enabled: true,
      permission_feature_id: "skill_toggles",
      reason: "演示占位"
    },
    {
      id: "skill2",
      name: "skill2",
      label: "skill2",
      description: "演示用拓展 Skill 占位，预留后续文档解析、复习计划扩展能力。展示站不会真实加载该 Skill。",
      path: "~/LangDrill/skills/skill2",
      skill_file: "~/LangDrill/skills/skill2/SKILL.md",
      homepage: "",
      requires_api_key: false,
      requires_token: false,
      installed: true,
      enabled: false,
      builtin: false,
      locked: false,
      always_enabled: false,
      default_enabled: false,
      permission_enabled: true,
      permission_feature_id: "skill_toggles",
      reason: "演示占位"
    }
  ],
  installed_count: 2,
  enabled_skill_ids: ["skill1"],
  no_key_skill_ids: [],
  permission_feature_id: "skill_toggles",
  web_search_permission_feature_id: "web_search_import",
  builtin_web_search: {
    id: "builtin-web-search",
    name: "builtin-web-search",
    label: "内置联网检索",
    description: "普通聊天中用户明确要求联网、搜索或最新信息时，由后端直接检索网页摘要；工具始终可用，实际调用仍遵守「联网功能」权限，不依赖拓展 Skills 开关。",
    homepage: "",
    requires_api_key: false,
    requires_token: false,
    installed: true,
    enabled: true,
    builtin: true,
    locked: true,
    always_enabled: true,
    permission_enabled: true,
    permission_feature_id: "web_search_import"
  },
  web_search_skill: {
    id: "multi-search-engine",
    name: "multi-search-engine",
    label: "Multi Search Engine",
    description: "生成可审计的多搜索引擎查询 URL；不抓取网页摘要，不需要个人 API Key 或 token。",
    homepage: "https://clawhub.com/skills/multi-search-engine",
    requires_api_key: false,
    requires_token: false,
    default_enabled: true,
    installed: false,
    enabled: false,
    permission_feature_id: "web_search_import"
  }
};

// ---------- 模拟延迟 ----------

function delay<T>(value: T, ms = 220): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

// ---------- 演示数据 ----------

const DEMO_SESSIONS: SessionItem[] = [
  { id: "demo-1", title: "CET-4 截图词表练习", folder_date: "今天", exam_id: "cet4", status: "active" },
  { id: "demo-2", title: "CJT4 阅读语境", folder_date: "昨天", exam_id: "cjt4", status: "completed" },
  { id: "demo-3", title: "错题复盘 · 06-30", folder_date: "06-30", status: "completed" }
];

const DEMO_QUESTION: Question = {
  id: "demo-q-1",
  sequence: 1,
  type: "context_vocabulary",
  prompt: "The team worked together to ___ the goal before Friday.",
  options: ["A. assess", "B. achieve", "C. approach", "D. advertise"],
  answer: { correct: "B. achieve", letter: "B" },
  explanation: "achieve 表示“达成目标”。approach 表示“接近”，assess 表示“评估”，advertise 表示“宣传”，与目标语境不符。",
  knowledge_tags: ["achieve", "goal", "teamwork"],
  status: "pending",
  set_total: 8,
  set_done: 0
};

const ASSISTANT_INTRO = `你好 boss，我是 **Lang Drill Agent** 的展示版模拟回复。

- 这是一个 1:1 还原主应用前端的产品展示站
- 网页版使用正在开发中，暂不支持真实模型调用，敬请期待
- 你可以在当前网页中探索三栏工作台、当前题卡、截图导入、设置和拓展 Skills

如果你希望体验完整能力（真实模型组卷、判题讲解、错题回流），可以前往 GitHub 下载 Windows 桌面版。`;

// ---------- URL 路由 ----------

type AnyObj = Record<string, unknown>;

function pathOf(url: string): string {
  // 去除 query
  return url.split("?")[0].replace(/\/+$/, "");
}

function queryOf(url: string): URLSearchParams {
  const idx = url.indexOf("?");
  return idx >= 0 ? new URLSearchParams(url.slice(idx + 1)) : new URLSearchParams();
}

// ---------- 公共 API ----------

export const API = "";

export async function apiGet<T>(url: string): Promise<T> {
  const path = pathOf(url);
  const query = queryOf(url);
  let data: unknown;

  if (path === "/api/bootstrap") {
    data = {
      profile: MOCK_PROFILE,
      providers: FALLBACK_PROVIDERS,
      model_config: DEFAULT_MODEL_CONFIG,
      exam_options: DEFAULT_EXAM_OPTIONS,
      syllabus_status: DEFAULT_SYLLABUS_STATUS,
      past_paper_status: DEFAULT_PAST_PAPER_STATUS,
      sessions: DEMO_SESSIONS,
      token_usage: DEFAULT_TOKEN_USAGE,
      data_paths: DEFAULT_DATA_PATHS,
      mineru_config: DEFAULT_MINERU_CONFIG,
      agent_permissions: DEFAULT_AGENT_PERMISSIONS,
      skills_status: DEFAULT_SKILLS_STATUS,
      learning_stats: DEFAULT_LEARNING_STATS
    };
  } else if (path === "/api/sessions") {
    data = { sessions: DEMO_SESSIONS };
  } else if (path === "/api/data-paths") {
    data = DEFAULT_DATA_PATHS;
  } else if (path === "/api/skills") {
    data = { skills_status: DEFAULT_SKILLS_STATUS };
  } else if (path.startsWith("/api/syllabus/status")) {
    const examId = query.get("exam_id") || "cet4";
    data = { ...DEFAULT_SYLLABUS_STATUS, exam_id: examId };
  } else if (path.startsWith("/api/past-papers/status")) {
    const examId = query.get("exam_id") || "cet4";
    data = { ...DEFAULT_PAST_PAPER_STATUS, exam_id: examId };
  } else if (path === "/api/phone-mirror/status") {
    data = {
      available: false,
      devices: [],
      message: "展示站不连接本机 adb / scrcpy，可在桌面版中体验手机映像。"
    };
  } else if (path.startsWith("/api/sessions/")) {
    // 单个会话详情：返回空壳
    data = { session: null };
  } else {
    data = {};
  }

  return delay(data as T);
}

export async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const path = pathOf(url);
  let data: unknown;
  const payload = (body || {}) as AnyObj;

  if (path === "/api/chat") {
    const userContent = String(payload.content || "");
    const msg: Message = {
      id: `mock-${Date.now()}`,
      role: "assistant",
      content: ASSISTANT_INTRO
    };
    data = {
      session_id: "demo-1",
      message: msg,
      daily_panel: { ...DEFAULT_PANEL, status: "idle" },
      active_question: null,
      token_usage: DEFAULT_TOKEN_USAGE,
      learning_stats: DEFAULT_LEARNING_STATS
    };
    // 模型选择等依旧保留原有样子，但 chat 永远返回固定自介绍
    void userContent;
  } else if (path === "/api/branch" || path.match(/^\/api\/branch\/[^/]+\/messages$/)) {
    const msg: Message = {
      id: `mock-branch-${Date.now()}`,
      role: "assistant",
      content: "分支对话演示回复：网页版分支能力正在开发中，当前展示站只模拟主流程。"
    };
    data = { branch_id: "demo-branch-1", message: msg.content };
  } else if (path === "/api/context/compress") {
    data = { token_usage: DEFAULT_TOKEN_USAGE, method: "extractive", note: "展示站未连接后端，仅返回演示压缩结果。" };
  } else if (path === "/api/context/settings") {
    data = { token_usage: { ...DEFAULT_TOKEN_USAGE, context_limit: Number(payload.context_limit) || DEFAULT_CONTEXT_LIMIT } };
  } else if (path === "/api/model-config") {
    data = { model_config: { ...DEFAULT_MODEL_CONFIG, ...(payload as AnyObj) } };
  } else if (path === "/api/model-config/default") {
    data = { model_config: DEFAULT_MODEL_CONFIG };
  } else if (path.startsWith("/api/model-config/models/")) {
    data = { provider: FALLBACK_PROVIDERS[3], providers: FALLBACK_PROVIDERS, model_config: DEFAULT_MODEL_CONFIG, message: "展示站未连接真实供应商，已返回内置模型列表。" };
  } else if (path === "/api/config/providers/custom") {
    data = { provider: FALLBACK_PROVIDERS[0], providers: FALLBACK_PROVIDERS };
  } else if (path === "/api/settings/defaults") {
    data = { profile: MOCK_PROFILE, model_config: DEFAULT_MODEL_CONFIG, providers: FALLBACK_PROVIDERS };
  } else if (path === "/api/settings/agent-permissions") {
    data = { agent_permissions: DEFAULT_AGENT_PERMISSIONS };
  } else if (path === "/api/profile") {
    data = { profile: { ...MOCK_PROFILE, ...(payload as AnyObj) }, sessions: DEMO_SESSIONS, learning_stats: DEFAULT_LEARNING_STATS };
  } else if (path === "/api/initialize") {
    data = { profile: { ...MOCK_PROFILE, ...(payload as AnyObj) } };
  } else if (path === "/api/data-paths/question-db-folder") {
    data = { data_paths: DEFAULT_DATA_PATHS, message: "展示站不会真实迁移数据库。" };
  } else if (path === "/api/data-paths/select-folder") {
    data = { selected: false, folder: "", message: "展示站不连接本机文件系统，可在桌面版中选择文件夹。" };
  } else if (path === "/api/mineru-config") {
    data = { mineru_config: { ...DEFAULT_MINERU_CONFIG, has_token: Boolean(payload.token), token_preview: payload.token ? "***演示预览***" : "" } };
  } else if (path === "/api/skills/enabled") {
    const next = { ...DEFAULT_SKILLS_STATUS };
    next.enabled_skill_ids = Array.isArray(payload.enabled_skill_ids) ? (payload.enabled_skill_ids as string[]) : next.enabled_skill_ids;
    data = { skills_status: next };
  } else if (path === "/api/syllabus/check" || path === "/api/syllabus/select") {
    data = { changed: false, message: "展示站不下载真实考纲。", status: DEFAULT_SYLLABUS_STATUS };
  } else if (path === "/api/past-papers/select" || path === "/api/past-papers/question-types" || path === "/api/past-papers/parse" || path === "/api/past-papers/import") {
    data = DEFAULT_PAST_PAPER_STATUS;
  } else if (path === "/api/past-papers/draft") {
    const draft: PastPaperDraft = {
      exam_id: "cet4",
      title: "演示真题草稿",
      year: 2024,
      source_url: "https://example.com/paper.pdf",
      local_path: "~/LangDrill/papers/cet4/demo.md",
      summary: "演示草稿：展示站不会真实下载试卷。",
      question_types: ["reading", "translation"]
    };
    data = { draft, parser: "mineru-lite", message: "展示站仅返回草稿示例。" };
  } else if (path === "/api/screenshot/parse") {
    data = mockScreenshotParse();
  } else if (path === "/api/phone-mirror/start") {
    data = { ok: false, command: "", error: "展示站不连接本机 adb / scrcpy。" };
  } else {
    data = {};
  }

  return delay(data as T);
}

export async function apiPostFile<T>(url: string, file: File): Promise<T> {
  const path = pathOf(url);

  if (path.startsWith("/api/files/extract-text")) {
    return delay({
      filename: file.name,
      text: `展示站未连接 MinerU/RapidOCR，已为文件「${file.name}」返回演示文本。可在桌面版中体验真实文件抽取链路。`,
      parser: "mock",
      confidence: "demo"
    } as T, 600);
  }

  if (path.startsWith("/api/past-papers/draft-file") || path.startsWith("/api/past-papers/import-file")) {
    const draft: PastPaperDraft = {
      exam_id: "cet4",
      title: file.name,
      year: 2024,
      source_url: "",
      local_path: `~/LangDrill/papers/cet4/${file.name}`,
      summary: "展示站不会真实保存或解析试卷文件。",
      question_types: ["reading"]
    };
    return delay({ draft, parser: "mock", message: "演示返回。", file_parser: "mock" } as T, 600);
  }

  return delay({} as T);
}

export async function apiDelete<T>(url: string): Promise<T> {
  const path = pathOf(url);

  if (path.startsWith("/api/sessions/")) {
    return delay({ deleted: true, sessions: DEMO_SESSIONS.filter((s) => !path.endsWith(s.id)) } as T);
  }

  return delay({ deleted: true } as T);
}

// ---------- 截图解析 mock ----------

function mockScreenshotParse(): ScreenshotImportResult {
  return {
    prompt: "演示提示词：以下是从截图抽取的可编辑词条，确认后导入并开始练习。",
    options: ["confirm"],
    confidence: "demo",
    raw_text:
      "achieve v. 达成\nchallenge n. 挑战\nappropriate adj. 适当的\nefficient adj. 高效的\nsustainable adj. 可持续的",
    words: [
      { term: "achieve", meaning: "v. 达成" },
      { term: "challenge", meaning: "n. 挑战" },
      { term: "appropriate", meaning: "adj. 适当的" },
      { term: "efficient", meaning: "adj. 高效的" },
      { term: "sustainable", meaning: "adj. 可持续的" }
    ],
    diagnostics: {
      skipped_lines: [],
      repaired_terms: [],
      skipped_count: 0,
      repaired_count: 0
    },
    imported: false,
    imported_count: 5,
    auto_started: false
  };
}

// 类型辅助（避免未使用类型告警）
export type {
  ChatImageAttachment,
  CustomModelDraft,
  PastPaperDraft
};
