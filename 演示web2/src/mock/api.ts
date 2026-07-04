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
  title: "今日学习记录",
  status: "active",
  plan: {
    new_content: ["截图导入 5 词（achieve/challenge/appropriate/efficient/sustainable）", "阅读理解仔细阅读 ×2 篇"],
    review_content: ["算法复习队列：compound / elaborate / infer", "错题权重回流：近义辨析 3 题", "考纲兜底：语境词汇 2 题"],
    target_minutes: 35,
    status: "in_progress"
  },
  questions_total: 12,
  questions_done: 8,
  knowledge_total: 24,
  knowledge_done: 17,
  knowledge_terms: ["achieve", "challenge", "appropriate", "efficient", "sustainable", "comprehend", "compound", "elaborate", "infer", "validate", "approach", "advertise", "evaluate", "frame", "grasp", "tackle", "synthesize"],
  exam_id: "cet4",
  exam_name: "大学英语四级",
  accuracy: 0.78,
  summary: "今日完成 8/12 题，正确率 78%。系统按掌握度分、错题权重和间隔复习窗口排序；achieve/challenge 已掌握，appropriate 与近义辨析进入下轮回流。"
};

const MOCK_PROFILE: Profile = {
  display_name: "boss",
  target_language: "英语",
  exam_id: "cet4",
  exam_name: "大学英语四级",
  deadline: "2026-12-19T09:00",
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
  current_source_id: "src_cet4",
  current_year: 2016,
  current_title: "全国大学英语四、六级考试大纲（2016年修订版）",
  official_url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm",
  sources: [
    { id: "src_cet4", exam_id: "cet4", title: "全国大学英语四、六级考试大纲（2016年修订版）", year: 2016, url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm", local_path: "", trusted_level: "official_or_exam_org", is_latest_checked: 0, checked_at: null },
    { id: "src_cet6", exam_id: "cet6", title: "全国大学英语四、六级考试大纲（2016年修订版）", year: 2016, url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm", local_path: "", trusted_level: "official_or_exam_org", is_latest_checked: 0, checked_at: null },
    { id: "src_cft4", exam_id: "cft4", title: "全国大学法语四级考试大纲（2023版）", year: 2023, url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm", local_path: "", trusted_level: "official_or_exam_org", is_latest_checked: 0, checked_at: null },
    { id: "src_cjt4", exam_id: "cjt4", title: "全国大学日语四、六级考试大纲（2024年启用）", year: 2024, url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm", local_path: "", trusted_level: "official_or_exam_org", is_latest_checked: 0, checked_at: null },
    { id: "src_cjt6", exam_id: "cjt6", title: "全国大学日语四、六级考试大纲（2024年启用）", year: 2024, url: "https://cet.neea.edu.cn/xhtml1/folder/16113/1588-1.htm", local_path: "", trusted_level: "official_or_exam_org", is_latest_checked: 0, checked_at: null },
    { id: "src_ielts", exam_id: "ielts", title: "IELTS Academic test format（雅思学术类考试结构）", year: 2026, url: "https://ielts.org/take-a-test/test-types/ielts-academic-test", local_path: "", trusted_level: "official", is_latest_checked: 0, checked_at: null },
    { id: "src_toefl", exam_id: "toefl", title: "TOEFL iBT Test Content（托福网考考试内容）", year: 2026, url: "https://www.ets.org/toefl/test-takers/ibt/about/content.html", local_path: "", trusted_level: "official_or_exam_org", is_latest_checked: 0, checked_at: null },
    { id: "src_gaokao-english", exam_id: "gaokao-english", title: "普通高中英语课程标准（2017年版2020年修订）", year: 2020, url: "https://www.moe.gov.cn/srcsite/A26/s8001/202006/t20200603_462199.html", local_path: "", trusted_level: "official", is_latest_checked: 0, checked_at: null }
  ]
};

const DEFAULT_PAST_PAPER_STATUS: PastPaperStatus = {
  exam_id: "cet4",
  description: "CET-4（大学英语四级）真题按阅读、翻译和写作组织；听力题型暂预留。",
  source_website: "https://www.guojiya.cn/#exams",
  papers: [
    { id: "paper_cet4_2025", exam_id: "cet4", asset_type: "past_paper", title: "大学英语四级 2025 年真题参考索引", year: 2025, source_url: "https://www.guojiya.cn/#exams", local_path: "papers/cet4/raw/cet4-2025-2025-er_cet4_2025.md", trusted_level: "needs_verification", copyright_boundary: "style_reference_only", metadata: { summary: "默认近三年真题索引，用于参考 大学英语四级 的题型结构、难度和常见主题。", question_types: ["listening", "reading", "translation", "writing", "context_vocabulary"], raw_path: "papers/cet4/raw/cet4-2025-2025-er_cet4_2025.md", parsed_path: "papers/cet4/parsed/cet4-2025-2025-er_cet4_2025.json", parse_status: "source_manifest_only", parser: "source_manifest" }, created_at: "2026-07-03T10:02:06" },
    { id: "paper_cet4_2024", exam_id: "cet4", asset_type: "past_paper", title: "大学英语四级 2024 年真题参考索引", year: 2024, source_url: "https://www.guojiya.cn/#exams", local_path: "papers/cet4/raw/cet4-2024-2024-er_cet4_2024.md", trusted_level: "needs_verification", copyright_boundary: "style_reference_only", metadata: { summary: "默认近三年真题索引，用于参考 大学英语四级 的题型结构、难度和常见主题。", question_types: ["listening", "reading", "translation", "writing", "context_vocabulary"], raw_path: "papers/cet4/raw/cet4-2024-2024-er_cet4_2024.md", parsed_path: "papers/cet4/parsed/cet4-2024-2024-er_cet4_2024.json", parse_status: "source_manifest_only", parser: "source_manifest" }, created_at: "2026-07-03T10:02:06" },
    { id: "paper_cet4_2023", exam_id: "cet4", asset_type: "past_paper", title: "大学英语四级 2023 年真题参考索引", year: 2023, source_url: "https://www.guojiya.cn/#exams", local_path: "papers/cet4/raw/cet4-2023-2023-er_cet4_2023.md", trusted_level: "needs_verification", copyright_boundary: "style_reference_only", metadata: { summary: "默认近三年真题索引，用于参考 大学英语四级 的题型结构、难度和常见主题。", question_types: ["listening", "reading", "translation", "writing", "context_vocabulary"], raw_path: "papers/cet4/raw/cet4-2023-2023-er_cet4_2023.md", parsed_path: "papers/cet4/parsed/cet4-2023-2023-er_cet4_2023.json", parse_status: "source_manifest_only", parser: "source_manifest" }, created_at: "2026-07-03T10:02:06" }
  ],
  selected_paper_ids: ["paper_cet4_2024"],
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
  questions_done: 184,
  questions_total: 220,
  words_mastered: 342,
  words_total: 600,
  accuracy: 0.78,
  attempts_total: 184,
  attempts_correct: 144
};

const DEFAULT_CONTEXT_LIMIT = 1_000_000;

const DEFAULT_TOKEN_USAGE: TokenUsage = {
  input: 1_284_500, output: 386_200, total: 1_670_700, total_calls: 248,
  average_tokens_per_call: 6737, average_latency_ms: 2480,
  estimated_current_context: 18_400, context_limit: DEFAULT_CONTEXT_LIMIT,
  context_percent: 0.018, context_messages: 12, compressed_context_tokens: 0,
  sessions_total: 38, messages_total: 412, active_days: 24, current_streak_days: 3,
  most_used_model: "mimo-v2.5-pro", most_used_model_percent: 0.72,
  today: { input: 24_800, output: 7_300, total: 32_100, calls: 6, average_tokens_per_call: 5350, average_latency_ms: 2120 },
  yesterday: { input: 31_200, output: 9_400, total: 40_600, calls: 8, average_tokens_per_call: 5075, average_latency_ms: 2280 },
  last_7_days: { input: 184_600, output: 56_200, total: 240_800, calls: 42, average_tokens_per_call: 5733, average_latency_ms: 2310 },
  last_30_days: { input: 612_400, output: 182_800, total: 795_200, calls: 156, average_tokens_per_call: 5097, average_latency_ms: 2420 },
  current_month: { input: 428_300, output: 128_500, total: 556_800, calls: 112, average_tokens_per_call: 4971, average_latency_ms: 2380 },
  model_breakdown: [
    { provider_id: "mimo", model: "mimo-v2.5-pro", input: 924_000, output: 278_400, tokens: 1_202_400, calls: 178, percent: 0.72 },
    { provider_id: "openai", model: "gpt-5.5", input: 236_500, output: 67_800, tokens: 304_300, calls: 48, percent: 0.18 },
    { provider_id: "claude", model: "claude-sonnet-4.7", input: 124_000, output: 40_000, tokens: 164_000, calls: 22, percent: 0.10 }
  ],
  provider_breakdown: [
    { provider_id: "mimo", input: 924_000, output: 278_400, tokens: 1_202_400, calls: 178, percent: 0.72 },
    { provider_id: "openai", input: 236_500, output: 67_800, tokens: 304_300, calls: 48, percent: 0.18 },
    { provider_id: "claude", input: 124_000, output: 40_000, tokens: 164_000, calls: 22, percent: 0.10 }
  ],
  task_breakdown: [
    { task_type: "question_generation", input: 524_000, output: 184_000, tokens: 708_000, calls: 96, percent: 0.42 },
    { task_type: "explanation", input: 386_500, output: 102_400, tokens: 488_900, calls: 72, percent: 0.29 },
    { task_type: "screenshot_parse", input: 218_000, output: 56_300, tokens: 274_300, calls: 44, percent: 0.16 },
    { task_type: "summary", input: 96_000, output: 28_500, tokens: 124_500, calls: 22, percent: 0.08 },
    { task_type: "chat", input: 60_000, output: 15_000, tokens: 75_000, calls: 14, percent: 0.05 }
  ],
  daily_activity: [
    { date: "2026-06-28", input: 18_200, output: 5_400, tokens: 23_600, calls: 4 },
    { date: "2026-06-29", input: 22_400, output: 6_800, tokens: 29_200, calls: 5 },
    { date: "2026-06-27", input: 28_800, output: 8_600, tokens: 37_400, calls: 6 },
    { date: "2026-07-01", input: 31_200, output: 9_400, tokens: 40_600, calls: 8 },
    { date: "2026-07-02", input: 26_400, output: 7_900, tokens: 34_300, calls: 6 },
    { date: "2026-07-03", input: 33_600, output: 10_200, tokens: 43_800, calls: 7 },
    { date: "2026-07-04", input: 24_800, output: 7_300, tokens: 32_100, calls: 6 }
  ],
  recent_calls: [
    { id: "call-0248", agent_name: "question_agent", task_type: "question_generation", provider_id: "mimo", model: "mimo-v2.5-pro", input_tokens: 4200, output_tokens: 1180, total_tokens: 5380, latency_ms: 1980, validation_status: "ok", created_at: "2026-07-04T10:42:18Z" },
    { id: "call-0247", agent_name: "explain_agent", task_type: "explanation", provider_id: "mimo", model: "mimo-v2.5-pro", input_tokens: 3680, output_tokens: 1640, total_tokens: 5320, latency_ms: 2240, validation_status: "ok", created_at: "2026-07-04T10:38:05Z" },
    { id: "call-0246", agent_name: "screenshot_agent", task_type: "screenshot_parse", provider_id: "mimo", model: "mimo-v2.5-pro", input_tokens: 8200, output_tokens: 620, total_tokens: 8820, latency_ms: 3120, validation_status: "ok", created_at: "2026-07-04T10:31:42Z" },
    { id: "call-0245", agent_name: "question_agent", task_type: "question_generation", provider_id: "openai", model: "gpt-5.5", input_tokens: 5800, output_tokens: 1420, total_tokens: 7220, latency_ms: 1860, validation_status: "ok", created_at: "2026-07-04T10:22:11Z" },
    { id: "call-0244", agent_name: "summary_agent", task_type: "summary", provider_id: "claude", model: "claude-sonnet-4.7", input_tokens: 9600, output_tokens: 2400, total_tokens: 12000, latency_ms: 3480, validation_status: "ok", created_at: "2026-07-03T22:14:33Z" }
  ]
};

const DEFAULT_DATA_PATHS: DataPathsStatus = {
  user_data_dir: "~/LangDrill/user-data",
  question_database_dir: "~/LangDrill/user-data",
  db_path: "~/LangDrill/user-data/langdrill_agent.db",
  log_dir: "~/LangDrill/logs",
  project_data_dir: "",
  test_data_dir: "",
  db_exists: true,
  db_size: 18_472_960,
  counts: {
    study_sessions: 38,
    messages: 412,
    questions: 220,
    attempts: 248,
    knowledge_items: 612,
    branch_conversations: 14,
    branch_messages: 86,
    model_calls: 248,
    syllabus_sources: 5,
    exam_assets: 12
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

// ---------- 演示数据：2 段真实会话记录 ----------
// 数据来源：真实 langdrill_agent.db，仅做路径脱敏；其中 ses_demo_cet4_active 是今天用于截图演示的会话（包含 collection 单词卡片）

const DEMO_SESSIONS: SessionItem[] = [
  { id: "ses_demo_cet4_active", title: "截图词表练习：collection", folder_date: "2026-07-04", exam_id: "cet4", status: "active" },
  { id: "ses_demo_cjt4_active", title: "日语四级错题回流", folder_date: "2026-07-03", exam_id: "cjt4", status: "active" }
];

// 2 段真实会话的完整消息记录（从真实数据库提取，仅脱敏路径；payload 保留以让已答题卡正确渲染）
const SESSION_MESSAGES: Record<string, Message[]> = {
  ses_demo_cet4_active: [
    { id: "msg_0168a18f47f1", role: "user", content: "把今天截图里的词表导入，按英语四级题型生成一组练习。" },
    {
      id: "msg_8a948d3493d7",
      role: "assistant",
      content: "截图词表已解析为 12 个高频词，并已先生成完整题组入库。\n\n本轮覆盖：词汇语境、完形填空、阅读理解、同义改写和翻译判断。先从易混词开始。"
    },
    { id: "msg_fc7e36c9d846", role: "user", content: "A\n补充提问：为什么这里不能选另一个看起来也合理的词？" },
    {
      id: "msg_3ea7a97eeb75",
      role: "assistant",
      content: "判断：正确。\n\n正确答案：A evident\n\n讲解：evident 表示“明显的”，符合后半句 everyone could see the pattern 的语义线索。\n\n补充：你问到干扰项时，优先看句子里的语义触发词，而不是只看中文释义相近。\n\n下一题已就绪：第 2 题 / 共 12 题。",
      payload: {
        answered_question: {
          id: "q_9cb8e4178e60",
          sequence: 1,
          type: "multiple_choice",
          prompt: "【词汇语境】The result was so ______ that even the least experienced student could see the pattern.",
          options: ["evident", "fierce", "mysterious", "contrary"],
          answer: { letter: "A", correct: "evident" },
          explanation: "evident 表示“明显的”，符合后半句 everyone could see the pattern 的语义线索。",
          knowledge_tags: ["vocabulary:evident"],
          status: "answered",
          set_total: 12,
          set_done: 1,
          selected_option: "A",
          selected_answer: "evident",
          is_correct: true
        }
      }
    },
    { id: "msg_6811343cffdd", role: "user", content: "B\n补充提问：为什么这里不能选另一个看起来也合理的词？" },
    {
      id: "msg_d8de296741d0",
      role: "assistant",
      content: "判断：不正确。\n\n正确答案：A discard\n\n讲解：discard 表示“丢弃”，样本保存温度错误后不能继续使用。\n\n补充：你问到干扰项时，优先看句子里的语义触发词，而不是只看中文释义相近。\n\n下一题已就绪：第 3 题 / 共 12 题。",
      payload: {
        answered_question: {
          id: "q_8fe43d4d4358",
          sequence: 2,
          type: "cloze",
          prompt: "【完形填空】The lab had to ______ the samples because they were stored at the wrong temperature.",
          options: ["discard", "apply", "guide", "collect"],
          answer: { letter: "A", correct: "discard" },
          explanation: "discard 表示“丢弃”，样本保存温度错误后不能继续使用。",
          knowledge_tags: ["vocabulary:discard"],
          status: "answered",
          set_total: 12,
          set_done: 2,
          selected_option: "B",
          selected_answer: "apply",
          is_correct: false
        }
      }
    },
    { id: "msg_25838257b27a", role: "user", content: "A\n补充提问：为什么这里不能选另一个看起来也合理的词？" },
    {
      id: "msg_91739360dd36",
      role: "assistant",
      content: "判断：正确。\n\n正确答案：A The new rule is opposite to the old policy.\n\n讲解：contrary to 表示“与……相反”，opposite to 是最接近的同义表达。\n\n补充：你问到干扰项时，优先看句子里的语义触发词，而不是只看中文释义相近。\n\n下一题已就绪：第 4 题 / 共 12 题。",
      payload: {
        answered_question: {
          id: "q_a72ab347c94b",
          sequence: 3,
          type: "multiple_choice",
          prompt: "【同义改写】Which sentence best keeps the meaning of “The new rule is contrary to the old policy”?",
          options: [
            "The new rule is opposite to the old policy.",
            "The new rule is copied from the old policy.",
            "The new rule is hidden in the old policy.",
            "The new rule is weaker than the old policy."
          ],
          answer: { letter: "A", correct: "The new rule is opposite to the old policy." },
          explanation: "contrary to 表示“与……相反”，opposite to 是最接近的同义表达。",
          knowledge_tags: ["vocabulary:contrary"],
          status: "answered",
          set_total: 12,
          set_done: 3,
          selected_option: "A",
          selected_answer: "The new rule is opposite to the old policy.",
          is_correct: true
        }
      }
    },
    { id: "msg_b9e23cf18c5e", role: "user", content: "B\n补充提问：为什么这里不能选另一个看起来也合理的词？" },
    {
      id: "msg_0aedb76fe266",
      role: "assistant",
      content: "判断：不正确。\n\n正确答案：A The storm delayed traffic on the road.\n\n讲解：原文先说暴风雪延误了车辆，随后才说救援队等待风势减弱。\n\n补充：你问到干扰项时，优先看句子里的语义触发词，而不是只看中文释义相近。\n\n下一题已就绪：第 5 题 / 共 12 题。",
      payload: {
        answered_question: {
          id: "q_484538b5f9e9",
          sequence: 4,
          type: "multiple_choice",
          prompt: "【阅读理解】A snowstorm delayed all vehicles on the mountain road. The rescue team waited until the wind became less fierce. What happened first?",
          options: [
            "The storm delayed traffic on the road.",
            "The rescue team reached the town immediately.",
            "The wind became stronger at once.",
            "The vehicles were discarded by the team."
          ],
          answer: { letter: "A", correct: "The storm delayed traffic on the road." },
          explanation: "原文先说暴风雪延误了车辆，随后才说救援队等待风势减弱。",
          knowledge_tags: ["vocabulary:snowstorm", "vocabulary:vehicle", "vocabulary:fierce"],
          status: "answered",
          set_total: 12,
          set_done: 4,
          selected_option: "B",
          selected_answer: "The rescue team reached the town immediately.",
          is_correct: false
        }
      }
    },
    { id: "msg_ce1eff5e38a2", role: "user", content: "A\n补充提问：为什么这里不能选另一个看起来也合理的词？" },
    {
      id: "msg_6576c46dfa00",
      role: "assistant",
      content: "判断：正确。\n\n正确答案：A apply\n\n讲解：apply for 表示“申请”，scholarship 奖学金通常与 apply for 搭配。\n\n补充：你问到干扰项时，优先看句子里的语义触发词，而不是只看中文释义相近。\n\n下一题已就绪：第 6 题 / 共 12 题。",
      payload: {
        answered_question: {
          id: "q_e2e3a9d57a0a",
          sequence: 5,
          type: "multiple_choice",
          prompt: "【词汇搭配】You must ______ for the scholarship before Friday if you want to be considered.",
          options: ["apply", "collide", "skin", "dry"],
          answer: { letter: "A", correct: "apply" },
          explanation: "apply for 表示“申请”，scholarship 奖学金通常与 apply for 搭配。",
          knowledge_tags: ["vocabulary:apply"],
          status: "answered",
          set_total: 12,
          set_done: 5,
          selected_option: "A",
          selected_answer: "apply",
          is_correct: true
        }
      }
    },
    { id: "msg_53efc19d0dc9", role: "user", content: "请帮我添加一个 DeepSeek 自定义模型，模型名 deepseek-chat-demo，上下文 100 万，文本模型。" },
    {
      id: "msg_d08a3bd43b94",
      role: "assistant",
      content: "我已整理成可确认的自定义模型草稿。你可以点击下方按钮填入设置页，保存前仍可修改模型名、上下文容量和视觉能力。",
      payload: {
        settings_action: {
          type: "custom_model_draft",
          feature_id: "custom_models",
          label: "自定义模型草稿：DeepSeek",
          draft: {
            provider_id: "deepseek",
            model: "deepseek-chat-demo",
            label: "DeepSeek Chat 演示模型",
            context_tokens: 1_000_000,
            vision: false
          }
        }
      }
    },
    { id: "msg_788a8346f963", role: "user", content: "请告诉我当前模型供应商、模型、Base URL、API 格式和思考等级。" },
    {
      id: "msg_206779750da1",
      role: "assistant",
      content: "当前脱敏模型配置如下：\n\n- 供应商：Xiaomi MiMo（小米米魔）\n- 模型：`mimo-v2.5-pro`\n- Base URL（基础网址）：`https://api.xiaomimimo.com/anthropic`\n- API 格式（接口格式）：`anthropic-messages`\n- 思考等级（reasoning，推理）：开启\n- 图片能力：当前聊天栏图片会先走 MinerU/RapidOCR（文档解析/本地文字识别）抽取文本。\n\nAPI Key（接口密钥）只会显示是否已配置，不会在聊天、截图或日志中回显明文。"
    },
    { id: "msg_2e77bb8909b6", role: "user", content: "总结" },
    {
      id: "msg_aabbbf285b45",
      role: "assistant",
      content: "## 今日复盘\n\n你今天的截图词表练习已经完成前 5 题，整体表现稳定，但 `contrary`、`fierce` 和 `collection/collision` 的干扰项仍需要回看。\n\n### 算法依据\n复习队列不是按时间顺序硬排，而是把掌握度分、最近错题权重、间隔复习窗口和当前考试题型一起计算；低掌握词会优先进入下一轮，已稳定答对的词延后复现。\n\n### 错题归因\n- 近形近义干扰：看到 `coll-` 开头时容易先联想到 collision（碰撞），但题干里的 museum、paintings 和 photographs 明确指向 collection（收藏）。\n- 语境触发词没有被优先使用：遇到 fierce、contrary 这类抽象词时，先找句子中的程度、转折和对比线索。\n\n### 下一轮建议\n先做 6 道阅读式词汇题，再用截图导入补 8-10 个低掌握词。答题时继续在补充提问里写出你排除干扰项的理由。"
    }
  ],
  ses_demo_cjt4_active: [
    { id: "msg_cc157f970876", role: "user", content: "把旧日语四级错题拿出来做一轮回流训练。" },
    { id: "msg_664faf98ef51", role: "assistant", content: "已读取旧日语四级学习痕迹，并生成错题回流题组。题型覆盖文字と語彙、文法、阅读改写和翻译判断。" },
    { id: "msg_770d7c282013", role: "user", content: "B\n补充提问：这个词在考纲里常用哪种写法？" },
    {
      id: "msg_c1ab46bd1e3b",
      role: "assistant",
      content: "判断：正确。\n\n正确答案：B 画面をクリックして番号札を受け取った。\n\n讲解：本文に、来場者は入口で画面をクリックして番号札を受け取ったとある。\n\n复习建议：把读音、搭配和句中语气一起记，别只背中文释义。\n\n下一题已就绪：第 2 题 / 共 12 题。",
      payload: {
        answered_question: {
          id: "q_9f26f27f93f4",
          sequence: 1,
          type: "multiple_choice",
          prompt: "【読解】次の文章を読んで、後の問いに答えなさい。\n週末、市の科学館では、原子力の初期模型からハイテク通信機器までを集めた特別展が開かれた。入口で来場者は案内板の画面をクリックして番号札を受け取り、古いエンジンに触れてよい時間は一回十分以内だと説明された。展示室には各時代のテープ機器も並び、色々な技術がどのように現在の通信へ繋がったかが分かるように示されていた。閉館前、職員は安全のため鍵をかける前に全員が外へ出たかを確かめ、内容を要約した紙を一人ずつ配った。\n入口で来場者がしたこととして最も適当なものはどれか。",
          options: [
            "鍵を借りて展示室を閉めた。",
            "画面をクリックして番号札を受け取った。",
            "紙を配ってから中へ入った。",
            "すぐにエンジンを分解し始めた。"
          ],
          answer: { letter: "B", correct: "画面をクリックして番号札を受け取った。" },
          explanation: "本文に、来場者は入口で画面をクリックして番号札を受け取ったとある。",
          knowledge_tags: ["vocabulary:クリック", "vocabulary:エンジン", "vocabulary:～以内"],
          status: "answered",
          set_total: 12,
          set_done: 1,
          selected_option: "B",
          selected_answer: "画面をクリックして番号札を受け取った。",
          is_correct: true
        }
      }
    },
    { id: "msg_dacc393e3877", role: "user", content: "C\n补充提问：这个词在考纲里常用哪种写法？" },
    {
      id: "msg_f1671b431166",
      role: "assistant",
      content: "判断：正确。\n\n正确答案：C たいしたことのない\n\n讲解：ここでの「軽い」は“深刻ではない、重くない”という意味。「怒る」は相手が本気で腹を立てたことを示す。\n\n复习建议：把读音、搭配和句中语气一起记，别只背中文释义。\n\n下一题已就绪：第 3 题 / 共 12 题。",
      payload: {
        answered_question: {
          id: "q_c5bed8b00a26",
          sequence: 2,
          type: "multiple_choice",
          prompt: "【文字と語彙】次の文の下線部の意味として最も適当なものを、[Ａ][Ｂ][Ｃ][Ｄ]から一つ選びなさい。\n彼は軽い冗談のつもりだったが、相手は本気で怒った。",
          options: ["かなり暗い", "すでに終わった", "たいしたことのない", "非常に重たい"],
          answer: { letter: "C", correct: "たいしたことのない" },
          explanation: "ここでの「軽い」は“深刻ではない、重くない”という意味。「怒る」は相手が本気で腹を立てたことを示す。",
          knowledge_tags: ["vocabulary:軽い", "vocabulary:怒る"],
          status: "answered",
          set_total: 12,
          set_done: 2,
          selected_option: "C",
          selected_answer: "たいしたことのない",
          is_correct: true
        }
      }
    },
    { id: "msg_8de073145944", role: "user", content: "B\n补充提问：这个词在考纲里常用哪种写法？" },
    {
      id: "msg_e54ca2b371b4",
      role: "assistant",
      content: "判断：不正确。\n\n正确答案：C しまって\n\n讲解：「〜てしまう」は完了や遗憾を表す。ここでは“把重要手帕弄丢了”という残念な気持ちがある。\n\n复习建议：把读音、搭配和句中语气一起记，别只背中文释义。\n\n下一题已就绪：第 4 题 / 共 12 题。",
      payload: {
        answered_question: {
          id: "q_0da06324e55d",
          sequence: 3,
          type: "multiple_choice",
          prompt: "【文法】次の文の（　）に入るのに最も適当なものを、[Ａ][Ｂ][Ｃ][Ｄ]から一つ選びなさい。\n大事なハンカチを途中で落として（　）、駅まで戻った。",
          options: ["おいて", "みて", "しまって", "ばかりで"],
          answer: { letter: "C", correct: "しまって" },
          explanation: "「〜てしまう」は完了や遗憾を表す。ここでは“把重要手帕弄丢了”という残念な気持ちがある。",
          knowledge_tags: ["grammar:〜てしまう", "vocabulary:ハンカチ", "vocabulary:途中"],
          status: "answered",
          set_total: 12,
          set_done: 3,
          selected_option: "B",
          selected_answer: "みて",
          is_correct: false
        }
      }
    },
    { id: "msg_58ce65434e70", role: "user", content: "B\n补充提问：这个词在考纲里常用哪种写法？" },
    {
      id: "msg_454522551501",
      role: "assistant",
      content: "判断：正确。\n\n正确答案：B その前後\n\n讲解：「〜ごろ」は“前后、大约那个时间”。「確か」は这里是“我记得、大概”的语气。\n\n复习建议：把读音、搭配和句中语气一起记，别只背中文释义。\n\n下一题已就绪：第 5 题 / 共 12 题。",
      payload: {
        answered_question: {
          id: "q_832645ed5cb1",
          sequence: 4,
          type: "multiple_choice",
          prompt: "【文字と語彙】次の文の下線部の意味として最も適当なものを、[Ａ][Ｂ][Ｃ][Ｄ]から一つ選びなさい。\n彼は『確か九時ごろ会社に着く』と言っていたが、まだ完全ではない資料を持っていた。",
          options: ["共同で", "その前後", "以前のように", "ちょうどその瞬間だけ"],
          answer: { letter: "B", correct: "その前後" },
          explanation: "「〜ごろ」は“前后、大约那个时间”。「確か」は这里是“我记得、大概”的语气。",
          knowledge_tags: ["vocabulary:～頃", "vocabulary:確か", "vocabulary:会社", "vocabulary:完全", "vocabulary:時"],
          status: "answered",
          set_total: 12,
          set_done: 4,
          selected_option: "B",
          selected_answer: "その前後",
          is_correct: true
        }
      }
    }
  ]
};

const DEMO_QUESTION: Question = {
  id: "demo-q-3",
  sequence: 3,
  type: "context_vocabulary",
  prompt: "The team worked together to ___ the goal before Friday.",
  options: ["A. assess", "B. achieve", "C. approach", "D. advertise"],
  answer: { correct: "B. achieve", letter: "B" },
  explanation: "achieve 表示“达成目标”。approach 表示“接近”，assess 表示“评估”，advertise 表示“宣传”，与目标语境不符。本词来自今日截图导入，下次复习周期 2 天。",
  knowledge_tags: ["achieve", "goal", "teamwork"],
  status: "pending",
  set_total: 12,
  set_done: 2
};

// 每个会话专属的 daily_panel 与 active_question，让点击不同会话时显示差异化进度
// 数据来源：真实 langdrill_agent.db（ses_demo_cet4_active 当前题 Q6 collection，包含完整单词卡片）
const SESSION_PANELS: Record<string, DailyPanel> = {
  ses_demo_cet4_active: {
    date: new Date().toLocaleDateString("zh-CN"),
    title: "截图词表练习：collection",
    status: "active",
    plan: {
      new_content: ["collection", "discard", "evident", "vehicle", "mysterious", "cotton"],
      review_content: ["算法优先复习：contrary / fierce", "四级阅读同义改写", "间隔窗口：2 天内复现 collection"],
      target_minutes: 45,
      status: "in_progress"
    },
    questions_total: 12,
    questions_done: 5,
    knowledge_total: 24,
    knowledge_done: 17,
    knowledge_terms: ["collection", "discard", "evident", "vehicle", "mysterious", "cotton", "contrary", "fierce", "apply", "snowstorm", "collision", "disguise", "vigorous", "germ", "waterfall", "bull", "guide", "skin"],
    exam_id: "cet4",
    exam_name: "大学英语四级",
    accuracy: 0.78,
    summary: "已完成前 5 题。系统根据掌握度分、错题权重和间隔复习窗口，把 collection / discard / contrary 放入重点复盘；当前题停在第 6 题，适合演示答题讲解和分支追问。"
  },
  ses_demo_cjt4_active: {
    date: new Date(Date.now() - 86_400_000).toLocaleDateString("zh-CN"),
    title: "日语四级错题回流",
    status: "active",
    plan: {
      new_content: ["片仮名", "何となく", "挑戦", "激しい"],
      review_content: ["4.23 错题回流", "语法：ために / てしまう / ておく"],
      target_minutes: 40,
      status: "in_progress"
    },
    questions_total: 12,
    questions_done: 4,
    knowledge_total: 18,
    knowledge_done: 12,
    knowledge_terms: ["片仮名", "ハンカチ", "軽い", "怒る", "しまう", "ごろ", "確か", "刺激", "外交", "向く", "絹", "ハム"],
    exam_id: "cjt4",
    exam_name: "大学日语四级",
    accuracy: 0.66,
    summary: "日语四级演示当前会话：已完成 4 题，下一题展示文字与语汇读音辨析。"
  }
};

const SESSION_QUESTIONS: Record<string, Question | null> = {
  // 当前演示题：Q6 collection，包含完整单词卡片，是今天截图演示使用的会话
  ses_demo_cet4_active: {
    id: "q_68c617bf9dc5",
    sequence: 6,
    type: "context_vocabulary",
    prompt: "【当前演示题】The museum has a large ______ of local paintings and old photographs.",
    options: ["collection", "collision", "waterfall", "germ"],
    answer: { letter: "A", correct: "collection" },
    explanation: "collection 表示“收藏品；集合”，与 museum、paintings、photographs 搭配自然。",
    knowledge_tags: ["vocabulary:collection"],
    status: "pending",
    set_total: 12,
    set_done: 5
  },
  // 日语当前演示题：Q5 和文中訳
  ses_demo_cjt4_active: {
    id: "q_756917e1560a",
    sequence: 5,
    type: "translation",
    prompt: "【和文中訳】次の文の意味として最も適当な中国語を、[Ａ][Ｂ][Ｃ][Ｄ]から一つ選びなさい。\n駅前の店では、絹の袋やハムをレジの横に並べ、税金を含めた料金を瓶のラベルにまできちんと書いている。",
    options: [
      "车站前的店里把丝袋和火腿摆在收银台旁边，连含税价格都仔细写到了瓶子的标签上。",
      "店员不会写字，只能把价格记在自己心里。",
      "车站前的店里不卖任何东西，只把空瓶子堆在门口。",
      "因为税太高，所以店里把所有火腿都送走了。"
    ],
    answer: { letter: "A", correct: "车站前的店里把丝袋和火腿摆在收银台旁边，连含税价格都仔细写到了瓶子的标签上。" },
    explanation: "句子说的是店里把商品摆在收银台旁边，并把含税价格仔细写在瓶子标签上。",
    knowledge_tags: ["vocabulary:絹", "vocabulary:ハム", "vocabulary:レジ", "vocabulary:税金", "vocabulary:含める", "vocabulary:料金", "vocabulary:瓶", "vocabulary:きちんと"],
    status: "pending",
    set_total: 12,
    set_done: 4
  }
};

const ASSISTANT_INTRO = `你好 boss，我是 **Lang Drill Agent** 的展示版模拟回复。

- 这是一个 1:1 还原主应用前端的产品展示站
- 网页版使用正在开发中，暂不支持真实模型调用，敬请期待
- 你可以在当前网页中探索三栏工作台、当前题卡、截图导入、设置和拓展 Skills
- 复习演示会突出掌握度分、错题权重和间隔复习窗口，展示题目如何进入下一轮队列

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
    // 单个会话详情：从 SESSION_MESSAGES 读取消息，按会话返回差异化演示内容
    const sessionId = path.slice("/api/sessions/".length);
    const sessionMeta = DEMO_SESSIONS.find((s) => s.id === sessionId);
    const messages = SESSION_MESSAGES[sessionId] || [];
    data = {
      session: sessionMeta || null,
      messages,
      daily_panel: SESSION_PANELS[sessionId] || DEFAULT_PANEL,
      active_question: SESSION_QUESTIONS[sessionId] ?? DEMO_QUESTION,
      token_usage: DEFAULT_TOKEN_USAGE,
      learning_stats: DEFAULT_LEARNING_STATS
    };
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
      session_id: "ses_demo_cet4_active",
      message: msg,
      daily_panel: SESSION_PANELS["ses_demo_cet4_active"] || DEFAULT_PANEL,
      active_question: SESSION_QUESTIONS["ses_demo_cet4_active"] ?? DEMO_QUESTION,
      token_usage: DEFAULT_TOKEN_USAGE,
      learning_stats: DEFAULT_LEARNING_STATS
    };
    // chat 文本始终返回固定自介绍（产品展示站不连接真实模型），但 panel / question 反映真实学习进度
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
