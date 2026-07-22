CREATE TABLE IF NOT EXISTS creative_runtime_status (
  singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
  state TEXT NOT NULL DEFAULT 'not_installed',
  version TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  details_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO creative_runtime_status
(singleton_id, state, version, error_code, details_json)
VALUES (1, 'not_installed', '', '', '{}');

CREATE TABLE IF NOT EXISTS creative_mode_settings (
  singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
  enabled INTEGER NOT NULL DEFAULT 0,
  permission_profile TEXT NOT NULL DEFAULT 'request_approval',
  rules_version INTEGER NOT NULL DEFAULT 1,
  rules_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO creative_mode_settings
(singleton_id, enabled, permission_profile, rules_version, rules_json)
VALUES (1, 0, 'request_approval', 1, '[]');

CREATE TABLE IF NOT EXISTS creative_policy_rules (
  id TEXT PRIMARY KEY,
  version INTEGER NOT NULL DEFAULT 1,
  priority INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,
  rule_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_creative_policy_rules_active
ON creative_policy_rules(enabled, priority DESC, id);

CREATE TABLE IF NOT EXISTS creative_audit_events (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL DEFAULT '',
  session_id TEXT NOT NULL DEFAULT '',
  event_type TEXT NOT NULL,
  reason_code TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_creative_audit_events_run
ON creative_audit_events(run_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_creative_audit_events_session
ON creative_audit_events(session_id, created_at, id);

CREATE TABLE IF NOT EXISTS creative_extension_installs (
  id TEXT PRIMARY KEY,
  extension_id TEXT NOT NULL,
  version TEXT NOT NULL,
  source TEXT NOT NULL,
  expected_hash TEXT NOT NULL DEFAULT '',
  installed_hash TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'staged',
  permissions_json TEXT NOT NULL DEFAULT '[]',
  manifest_json TEXT NOT NULL DEFAULT '{}',
  error_code TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(extension_id, version)
);
