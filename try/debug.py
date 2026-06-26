import sqlite3
from langdrill_agent.config import load_settings
from langdrill_agent.services import ModelConfigService
conn = sqlite3.connect(load_settings().db_path)
conn.row_factory = sqlite3.Row
print(ModelConfigService(conn).current_with_secret())
