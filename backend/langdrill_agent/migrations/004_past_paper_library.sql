CREATE TABLE IF NOT EXISTS past_paper_sources (
  id TEXT PRIMARY KEY,
  exam_id TEXT NOT NULL,
  title TEXT NOT NULL,
  source_url TEXT NOT NULL,
  year INTEGER,
  session TEXT NOT NULL DEFAULT '',
  set_number INTEGER,
  answer_source_url TEXT NOT NULL DEFAULT '',
  source_host TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(exam_id, source_url)
);

CREATE TABLE IF NOT EXISTS past_paper_import_jobs (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  run_id TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  stage TEXT NOT NULL DEFAULT 'queued',
  partial_path TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL DEFAULT '',
  bytes_downloaded INTEGER NOT NULL DEFAULT 0,
  error_code TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(source_id) REFERENCES past_paper_sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS past_paper_documents (
  id TEXT PRIMARY KEY,
  source_id TEXT,
  exam_id TEXT NOT NULL,
  title TEXT NOT NULL,
  year INTEGER,
  session TEXT NOT NULL DEFAULT '',
  set_number INTEGER,
  source_url TEXT NOT NULL DEFAULT '',
  raw_path TEXT NOT NULL DEFAULT '',
  markdown_path TEXT NOT NULL DEFAULT '',
  structured_path TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  parser TEXT NOT NULL DEFAULT '',
  parser_version TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(exam_id, source_url, content_hash),
  FOREIGN KEY(source_id) REFERENCES past_paper_sources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS past_paper_sections (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  question_type TEXT NOT NULL DEFAULT '',
  source_page INTEGER,
  UNIQUE(document_id, ordinal),
  FOREIGN KEY(document_id) REFERENCES past_paper_documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS past_paper_passages (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  section_id TEXT,
  ordinal INTEGER NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  source_page INTEGER,
  content_hash TEXT NOT NULL,
  UNIQUE(document_id, ordinal),
  FOREIGN KEY(document_id) REFERENCES past_paper_documents(id) ON DELETE CASCADE,
  FOREIGN KEY(section_id) REFERENCES past_paper_sections(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS past_paper_questions (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  section_id TEXT,
  passage_id TEXT,
  question_number TEXT NOT NULL DEFAULT '',
  question_type TEXT NOT NULL,
  prompt TEXT NOT NULL,
  options_json TEXT NOT NULL DEFAULT '[]',
  answer_json TEXT NOT NULL DEFAULT '{}',
  explanation TEXT NOT NULL DEFAULT '',
  knowledge_tags_json TEXT NOT NULL DEFAULT '[]',
  difficulty REAL,
  source_page INTEGER,
  answer_confidence REAL NOT NULL DEFAULT 0,
  verification_status TEXT NOT NULL DEFAULT 'unverified',
  content_hash TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(document_id, question_number),
  FOREIGN KEY(document_id) REFERENCES past_paper_documents(id) ON DELETE CASCADE,
  FOREIGN KEY(section_id) REFERENCES past_paper_sections(id) ON DELETE SET NULL,
  FOREIGN KEY(passage_id) REFERENCES past_paper_passages(id) ON DELETE SET NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS past_paper_question_fts USING fts5(
  question_id UNINDEXED,
  document_id UNINDEXED,
  question_type UNINDEXED,
  prompt,
  options,
  explanation,
  tags,
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS past_paper_embeddings (
  question_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  dimensions INTEGER NOT NULL,
  vector_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  PRIMARY KEY(question_id, provider, model),
  FOREIGN KEY(question_id) REFERENCES past_paper_questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS past_paper_retrieval_events (
  id TEXT PRIMARY KEY,
  exam_id TEXT NOT NULL,
  query TEXT NOT NULL,
  filters_json TEXT NOT NULL DEFAULT '{}',
  result_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS past_paper_distillations (
  id TEXT PRIMARY KEY,
  exam_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  status TEXT NOT NULL,
  finding_type TEXT NOT NULL DEFAULT '',
  label TEXT NOT NULL DEFAULT '',
  finding_json TEXT NOT NULL DEFAULT '{}',
  evidence_count INTEGER NOT NULL DEFAULT 0,
  paper_count INTEGER NOT NULL DEFAULT 0,
  years_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL DEFAULT 0,
  prompt_version TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(exam_id, version, finding_type, label)
);

CREATE TABLE IF NOT EXISTS past_paper_distillation_evidence (
  distillation_id TEXT NOT NULL,
  question_id TEXT NOT NULL,
  PRIMARY KEY(distillation_id, question_id),
  FOREIGN KEY(distillation_id) REFERENCES past_paper_distillations(id) ON DELETE CASCADE,
  FOREIGN KEY(question_id) REFERENCES past_paper_questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS practice_coverage_ledger (
  exam_id TEXT NOT NULL,
  question_type TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  rolling_seen INTEGER NOT NULL DEFAULT 0,
  rolling_selected INTEGER NOT NULL DEFAULT 0,
  coverage_debt REAL NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(exam_id, question_type)
);

CREATE TABLE IF NOT EXISTS practice_schedule_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL DEFAULT '',
  exam_id TEXT NOT NULL,
  candidate_json TEXT NOT NULL DEFAULT '[]',
  rejected_json TEXT NOT NULL DEFAULT '[]',
  allocation_json TEXT NOT NULL DEFAULT '{}',
  selected_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
