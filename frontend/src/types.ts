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
};

export type ModelOption = string | {
  id: string;
  label?: string;
  context_tokens?: number;
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
  has_api_key?: boolean;
  visible_in_picker?: boolean;
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

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export type TokenUsage = {
  input: number;
  output: number;
  total: number;
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
  model_breakdown?: Array<{
    provider_id: string;
    model: string;
    tokens: number;
    calls: number;
    percent: number;
  }>;
  daily_activity?: Array<{
    date: string;
    tokens: number;
    calls: number;
  }>;
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

export type ScreenshotWord = {
  term: string;
  meaning: string;
};

export type ScreenshotImportResult = {
  prompt: string;
  options: string[];
  confidence: string;
  raw_text: string;
  words?: ScreenshotWord[];
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
