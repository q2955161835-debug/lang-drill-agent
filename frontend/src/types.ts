export type Profile = {
  display_name: string;
  target_language: string;
  exam_id: string;
  exam_name: string;
  deadline?: string | null;
  learning_goal: string;
  learning_background: string;
  persona: string;
  global_user_prompt: string;
};

export type ThemeMode = "system" | "light" | "dark";

export type ProviderOption = {
  id: string;
  label: string;
  kind: string;
  api_format?: string;
  api_key_required?: boolean;
  enabled?: boolean;
  has_api_key?: boolean;
  visible_in_picker?: boolean;
  base_url: string;
  model: string;
  model_options: ModelOption[];
};

export type ThinkingLevel = string;

export type ThinkingLevelOption = {
  id: ThinkingLevel;
  label: string;
  api_value: string;
  custom?: boolean;
};

export type ModelOption = string | {
  id: string;
  label?: string;
  context_tokens?: number;
  vision?: boolean;
  visible?: boolean;
  reasoning?: {
    default_level?: string;
    parameter?: string;
    levels?: ThinkingLevelOption[];
  };
};

export type ModelConfig = {
  provider_id: string;
  base_url: string;
  model: string;
  api_key?: string;
  thinking_level?: ThinkingLevel;
  thinking_level_options?: ThinkingLevelOption[];
  thinking_api_value?: string;
  reasoning_parameter?: string;
  api_format?: string;
  vision?: boolean;
  has_api_key?: boolean;
  visible_in_picker?: boolean;
};

export type ChatImageAttachment = {
  type: "image";
  filename: string;
  mime_type: string;
  data_url: string;
};

export type MinerUConfig = {
  token_url: string;
  docs_url: string;
  env_key: string;
  has_token: boolean;
  token_preview: string;
};

export type AgentSettingPermissionFeature = {
  id: string;
  label: string;
  description: string;
  enabled: boolean;
  sensitive?: boolean;
};

export type AgentSettingsPermissionsStatus = {
  features: AgentSettingPermissionFeature[];
  enabled_feature_ids: string[];
};

export type SessionItem = {
  id: string;
  title: string;
  folder_date: string;
  exam_id?: string;
  status: string;
  draft?: boolean;
};

export type DailyPanel = {
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
  knowledge_total?: number;
  knowledge_done?: number;
  knowledge_terms?: string[];
  exam_id?: string;
  exam_name?: string;
  accuracy: number;
  summary: string;
};

export type LearningStats = {
  exam_id: string;
  exam_name: string;
  questions_done: number;
  questions_total: number;
  words_mastered: number;
  words_total: number;
  accuracy: number;
  attempts_total: number;
  attempts_correct: number;
};

export type Question = {
  id: string;
  sequence: number;
  type: string;
  prompt: string;
  options: string[];
  answer?: { correct?: string; letter?: string };
  explanation?: string;
  knowledge_tags: string[];
  status: string;
  set_total?: number;
  set_done?: number;
};

export type AnsweredQuestion = Question & {
  selected_option?: string;
  selected_answer?: string;
  is_correct?: boolean;
};

export type PastPaperDraft = {
  exam_id?: string;
  title: string;
  year: number | null;
  source_url: string;
  local_path: string;
  summary: string;
  question_types: string[];
  raw_text?: string;
};

export type SettingsAction = {
  type: "past_paper_import_draft";
  feature_id: string;
  label: string;
  draft: PastPaperDraft;
  parser?: string;
  confirmation_required?: boolean;
};

export type MessagePayload = {
  active_question?: Question | null;
  answered_question?: AnsweredQuestion;
  settings_action?: SettingsAction;
  source?: string;
  [key: string]: unknown;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  payload?: MessagePayload;
};

export type TokenUsage = {
  input: number;
  output: number;
  total: number;
  total_calls?: number;
  average_tokens_per_call?: number;
  average_latency_ms?: number;
  estimated_current_context: number;
  context_limit?: number;
  context_percent?: number;
  context_messages?: number;
  compressed_context_tokens?: number;
  compression_method?: string;
  compression_available?: boolean;
  compression_project?: string;
  compression_project_url?: string;
  sessions_total?: number;
  messages_total?: number;
  active_days?: number;
  current_streak_days?: number;
  most_used_model?: string;
  most_used_model_percent?: number;
  today?: UsageWindow;
  yesterday?: UsageWindow;
  last_7_days?: UsageWindow;
  last_30_days?: UsageWindow;
  current_month?: UsageWindow;
  model_breakdown?: Array<{
    provider_id: string;
    model: string;
    input?: number;
    output?: number;
    tokens: number;
    calls: number;
    percent: number;
  }>;
  provider_breakdown?: Array<{
    provider_id: string;
    input: number;
    output: number;
    tokens: number;
    calls: number;
    percent: number;
  }>;
  task_breakdown?: Array<{
    task_type: string;
    input: number;
    output: number;
    tokens: number;
    calls: number;
    percent: number;
  }>;
  daily_activity?: Array<{
    date: string;
    input?: number;
    output?: number;
    tokens: number;
    calls: number;
  }>;
  recent_calls?: TokenUsageCall[];
};

export type UsageWindow = {
  input: number;
  output: number;
  total: number;
  calls: number;
  average_tokens_per_call?: number;
  average_latency_ms?: number;
};

export type TokenUsageCall = {
  id: string;
  agent_name: string;
  task_type: string;
  provider_id: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  latency_ms: number;
  validation_status: string;
  created_at: string;
};

export type DataPathsStatus = {
  user_data_dir: string;
  question_database_dir: string;
  db_path: string;
  log_dir: string;
  project_data_dir: string;
  test_data_dir: string;
  db_exists: boolean;
  db_size: number;
  previous_db_path?: string;
  migrated?: boolean;
  message?: string;
  counts: {
    study_sessions: number;
    messages: number;
    questions: number;
    attempts: number;
    knowledge_items: number;
    branch_conversations: number;
    branch_messages: number;
    model_calls: number;
    syllabus_sources: number;
    exam_assets: number;
    [key: string]: number;
  };
};

export type ExamOption = {
  id: string;
  name: string;
  target_language: string;
  official_url: string;
  default_year: number | null;
  description: string;
};

export type SyllabusSource = {
  id: string;
  exam_id: string;
  title: string;
  year: number | null;
  url: string;
  local_path: string;
  trusted_level: string;
  is_latest_checked: number;
  checked_at?: string | null;
};

export type SyllabusStatus = {
  exam_id: string;
  current_source_id: string;
  current_year: number | null;
  current_title: string;
  official_url: string;
  sources: SyllabusSource[];
};

export type PastPaper = {
  id: string;
  exam_id: string;
  asset_type: string;
  title: string;
  year: number | null;
  source_url: string;
  local_path: string;
  trusted_level: string;
  copyright_boundary: string;
  metadata_json?: string;
  metadata?: {
    summary?: string;
    question_types?: string[];
    raw_path?: string;
    parsed_path?: string;
    parse_status?: string;
    parse_error?: string;
    parser?: string;
  };
  created_at?: string;
};

export type QuestionTypeOption = {
  id: string;
  label: string;
  description: string;
};

export type PastPaperStatus = {
  exam_id: string;
  description: string;
  source_website: string;
  papers: PastPaper[];
  selected_paper_ids: string[];
  current_papers: PastPaper[];
  question_types: QuestionTypeOption[];
  enabled_question_type_ids: string[];
  message?: string;
};

export type ScreenshotWord = {
  term: string;
  meaning: string;
};

export type ScreenshotImportDiagnostics = {
  skipped_lines: Array<{ text: string; reason: string }>;
  repaired_terms: Array<{ text: string; term: string; reason: string }>;
  skipped_count: number;
  repaired_count: number;
};

export type ScreenshotImportResult = {
  prompt: string;
  options: string[];
  confidence: string;
  raw_text: string;
  words?: ScreenshotWord[];
  diagnostics?: ScreenshotImportDiagnostics;
  imported?: boolean;
  imported_count?: number;
  auto_started?: boolean;
  generation_error?: string;
  session_id?: string;
  daily_panel?: DailyPanel;
  active_question?: Question | null;
  message?: Message;
  messages?: Message[];
  token_usage?: TokenUsage;
  learning_stats?: LearningStats;
  sessions?: SessionItem[];
};
