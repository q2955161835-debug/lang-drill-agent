# Past Paper Assets（历年真题资产）

This directory stores exam paper assets by exam type.

- `raw/`: original imported paper files or pasted-paper Markdown/TXT saved by the app.
- `parsed/`: structured JSON extracted from raw papers for question generation.
- Each exam type has its own directory, for example `cet4/raw` and `cet4/parsed`.
- Runtime-generated/imported files under `raw/` and `parsed/` are ignored by Git by default; `.gitkeep` only keeps the directory skeleton.

Copyright boundary:

- Do not commit full copyrighted real exam papers unless the source license clearly permits redistribution.
- User-imported local papers can be stored here for local use, but review before committing.
- Parsed JSON should keep only the parts needed for generation: structure, question types, short excerpts, summaries, source URL, and file paths.

中文说明：

- `raw/` 存原始试卷文件、用户粘贴文本或 Markdown（Markdown 文本格式）。
- `parsed/` 存解析后的 JSON（JSON 数据交换格式），用于组卷阶段参考章节、题型、短摘录和来源。
- 不要提交版权不明或来源不清的完整真题；需要提交真实试卷时必须先确认授权。
