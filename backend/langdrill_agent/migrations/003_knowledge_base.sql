CREATE TABLE IF NOT EXISTS knowledge_documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  source_name TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  raw_path TEXT NOT NULL DEFAULT '',
  parsed_path TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL,
  language TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'queued',
  parser TEXT NOT NULL DEFAULT '',
  parser_version TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  heading TEXT NOT NULL DEFAULT '',
  page_start INTEGER,
  page_end INTEGER,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  token_count INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(document_id, ordinal),
  FOREIGN KEY(document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document
ON knowledge_chunks(document_id, ordinal);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunk_fts USING fts5(
  chunk_id UNINDEXED,
  document_id UNINDEXED,
  heading,
  content,
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS knowledge_embeddings (
  chunk_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  dimensions INTEGER NOT NULL,
  vector_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  PRIMARY KEY(chunk_id, provider, model),
  FOREIGN KEY(chunk_id) REFERENCES knowledge_chunks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS retrieval_events (
  id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL DEFAULT '',
  query TEXT NOT NULL,
  filters_json TEXT NOT NULL DEFAULT '{}',
  result_json TEXT NOT NULL DEFAULT '[]',
  injected_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
