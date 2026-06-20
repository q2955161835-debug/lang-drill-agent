import sqlite3
from langdrill_agent.services import ModelConfigService
conn = sqlite3.connect('d:/1Folder/语言学习-lang-drill/语言学习-lang-drill-agent/data/langdrill_agent.db')
conn.row_factory = sqlite3.Row
print(ModelConfigService(conn).current_with_secret())
