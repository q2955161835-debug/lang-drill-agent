CREATE TABLE IF NOT EXISTS resource_import_staging (
  id TEXT PRIMARY KEY,
  target TEXT NOT NULL CHECK(target IN ('knowledge', 'past_paper')),
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  size_bytes INTEGER NOT NULL,
  staged_path TEXT NOT NULL,
  extracted_path TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('staged', 'parsing', 'preview_ready', 'failed', 'confirmed', 'cancelled')),
  parser TEXT NOT NULL DEFAULT '',
  preview_json TEXT NOT NULL DEFAULT '{}',
  error_code TEXT NOT NULL DEFAULT '',
  error_detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_resource_import_expiry
ON resource_import_staging(status, expires_at);
