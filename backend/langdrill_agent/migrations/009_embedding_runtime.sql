CREATE TABLE IF NOT EXISTS embedding_download_jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'model' CHECK(kind IN ('model', 'runtime')),
  model_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  target_dir TEXT NOT NULL,
  status TEXT NOT NULL,
  files_total INTEGER NOT NULL DEFAULT 0,
  files_completed INTEGER NOT NULL DEFAULT 0,
  bytes_downloaded INTEGER NOT NULL DEFAULT 0,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  error_code TEXT NOT NULL DEFAULT '',
  error_detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS embedding_index_state (
  target TEXT PRIMARY KEY CHECK(target IN ('knowledge', 'past_papers', 'memory')),
  identity_key TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'fts_only',
  indexed_count INTEGER NOT NULL DEFAULT 0,
  error_code TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
