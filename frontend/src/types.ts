export type Profile = {
  display_name: string;
  target_language: string;
  exam_id: string;
  exam_name: string;
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
  base_url: string;
  model: string;
  model_options: string[];
};

export type ModelConfig = {
  provider_id: string;
  base_url: string;
  model: string;
  api_key?: string;
  has_api_key?: boolean;
};

export type SessionItem = {
  id: string;
  title: string;
  folder_date: string;
  exam_id?: string;
  status: string;
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
