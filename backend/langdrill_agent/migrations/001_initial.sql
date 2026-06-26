CREATE TABLE IF NOT EXISTS user_profiles (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  display_name TEXT NOT NULL DEFAULT 'boss',
  target_language TEXT NOT NULL DEFAULT '英语',
  exam_id TEXT NOT NULL DEFAULT 'cet4',
  exam_name TEXT NOT NULL DEFAULT '大学英语四级',
  deadline TEXT,
  daily_minutes INTEGER NOT NULL DEFAULT 35,
  learning_goal TEXT NOT NULL DEFAULT '',
  learning_background TEXT NOT NULL DEFAULT '',
  persona TEXT NOT NULL DEFAULT 'professional',
  global_user_prompt TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO user_profiles (id) VALUES (1);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_providers (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  base_url TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  api_key_env TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS study_sessions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  folder_date TEXT NOT NULL,
  exam_id TEXT NOT NULL DEFAULT 'cet4',
  status TEXT NOT NULL DEFAULT 'active',
  daily_plan_json TEXT NOT NULL DEFAULT '{}',
  summary TEXT NOT NULL DEFAULT '',
  token_input INTEGER NOT NULL DEFAULT 0,
  token_output INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS branch_conversations (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  selected_text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  merge_target TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS branch_messages (
  id TEXT PRIMARY KEY,
  branch_id TEXT NOT NULL REFERENCES branch_conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_items (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  term TEXT NOT NULL,
  reading TEXT NOT NULL DEFAULT '',
  meaning TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  exam_id TEXT NOT NULL DEFAULT 'unassigned',
  source_scope TEXT NOT NULL DEFAULT 'user',
  mastery_score REAL NOT NULL DEFAULT 0.2,
  due_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS questions (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL,
  type TEXT NOT NULL,
  prompt TEXT NOT NULL,
  options_json TEXT NOT NULL DEFAULT '[]',
  answer_json TEXT NOT NULL,
  explanation TEXT NOT NULL,
  knowledge_tags_json TEXT NOT NULL DEFAULT '[]',
  difficulty REAL NOT NULL DEFAULT 0.5,
  status TEXT NOT NULL DEFAULT 'ready',
  source_refs_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attempts (
  id TEXT PRIMARY KEY,
  question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
  user_answer TEXT NOT NULL,
  is_correct INTEGER NOT NULL,
  used_hint INTEGER NOT NULL DEFAULT 0,
  feedback TEXT NOT NULL,
  mastery_delta REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mastery_events (
  id TEXT PRIMARY KEY,
  knowledge_id TEXT,
  question_id TEXT,
  attempt_id TEXT,
  event_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prompt_modules (
  id TEXT PRIMARY KEY,
  version TEXT NOT NULL,
  scope TEXT NOT NULL,
  task_type TEXT NOT NULL,
  exam_id TEXT NOT NULL DEFAULT 'any',
  priority INTEGER NOT NULL DEFAULT 0,
  token_budget INTEGER NOT NULL DEFAULT 0,
  dependencies TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_calls (
  id TEXT PRIMARY KEY,
  agent_name TEXT NOT NULL,
  task_type TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_modules_json TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  validation_status TEXT NOT NULL DEFAULT 'not_required',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS syllabus_sources (
  id TEXT PRIMARY KEY,
  exam_id TEXT NOT NULL,
  title TEXT NOT NULL,
  year INTEGER,
  url TEXT NOT NULL DEFAULT '',
  local_path TEXT NOT NULL DEFAULT '',
  trusted_level TEXT NOT NULL DEFAULT 'unknown',
  copyright_boundary TEXT NOT NULL DEFAULT 'reference_only',
  is_latest_checked INTEGER NOT NULL DEFAULT 0,
  checked_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exam_assets (
  id TEXT PRIMARY KEY,
  exam_id TEXT NOT NULL,
  asset_type TEXT NOT NULL,
  title TEXT NOT NULL,
  year INTEGER,
  source_url TEXT NOT NULL DEFAULT '',
  local_path TEXT NOT NULL DEFAULT '',
  trusted_level TEXT NOT NULL DEFAULT 'unknown',
  copyright_boundary TEXT NOT NULL DEFAULT 'reference_only',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS generation_jobs (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES study_sessions(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  target_count INTEGER NOT NULL DEFAULT 0,
  generated_count INTEGER NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  level TEXT NOT NULL,
  event_type TEXT NOT NULL,
  message TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
