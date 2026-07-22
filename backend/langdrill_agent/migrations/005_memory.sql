CREATE TABLE IF NOT EXISTS memory_candidates (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'global',
  content TEXT NOT NULL,
  normalized_key TEXT NOT NULL DEFAULT '',
  confidence REAL NOT NULL DEFAULT 0,
  importance REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'staged',
  reason TEXT NOT NULL DEFAULT '',
  valid_from TEXT,
  valid_to TEXT,
  expires_at TEXT,
  pinned INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memory_items (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'global',
  content TEXT NOT NULL,
  normalized_key TEXT NOT NULL DEFAULT '',
  confidence REAL NOT NULL DEFAULT 0,
  importance REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  valid_from TEXT,
  valid_to TEXT,
  expires_at TEXT,
  supersedes_id TEXT,
  pinned INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(supersedes_id) REFERENCES memory_items(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_items_key_status
  ON memory_items(normalized_key, status);
CREATE INDEX IF NOT EXISTS idx_memory_items_scope_category
  ON memory_items(scope, category, status);

CREATE TABLE IF NOT EXISTS memory_evidence (
  id TEXT PRIMARY KEY,
  candidate_id TEXT,
  memory_id TEXT,
  evidence_type TEXT NOT NULL DEFAULT 'reference',
  evidence_ref TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(candidate_id) REFERENCES memory_candidates(id) ON DELETE CASCADE,
  FOREIGN KEY(memory_id) REFERENCES memory_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_revisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  memory_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  content TEXT NOT NULL,
  snapshot_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(memory_id) REFERENCES memory_items(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_item_fts USING fts5(
  memory_id UNINDEXED,
  category UNINDEXED,
  scope UNINDEXED,
  content,
  normalized_key,
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS memory_embeddings (
  memory_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  dimensions INTEGER NOT NULL,
  vector_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  PRIMARY KEY(memory_id, provider, model),
  FOREIGN KEY(memory_id) REFERENCES memory_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_events (
  id TEXT PRIMARY KEY,
  memory_id TEXT,
  candidate_id TEXT,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(memory_id) REFERENCES memory_items(id) ON DELETE SET NULL,
  FOREIGN KEY(candidate_id) REFERENCES memory_candidates(id) ON DELETE SET NULL
);
