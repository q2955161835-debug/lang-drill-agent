# Past Paper Assets（历年真题资产）

This directory stores local past-paper assets by exam type（本目录按考试类型保存本地历年真题资产）.

- `raw/`（原始目录）: original downloaded or user-imported files（下载或用户导入的原始文件）.
- `parsed/`（可审阅解析目录）: schema v2 Markdown（结构版本 2 标记语言）that users can review and edit before reparse（用户可在重解析前审阅和编辑）.
- `structured/`（结构化目录）: machine-readable JSON（机器可读数据交换格式）derived from the reviewed Markdown（从已审阅标记语言派生）.
- Each exam has an isolated directory, such as `cet4/raw`, `cet4/parsed`, and `cet4/structured`（每个考试使用独立目录，例如上述英语四级目录）.

## Data Boundary（数据边界）

- SQLite（轻量数据库）is the formal retrieval and learning-state source（是正式检索与学习状态来源）.
- A remote catalog entry is only a discovered source and never counts as an installed paper（远程目录项仅代表已发现来源，不计为已安装试卷）.
- A document becomes `ready`（就绪）only after raw download, extraction, reviewable Markdown generation, structured JSON generation, and question indexing all succeed（只有原始下载、抽取、可审阅标记语言、结构化数据和题目索引全部成功后才进入就绪状态）.
- Reparse prefers user-edited Markdown and atomically replaces SQLite question indexes（重解析优先使用用户编辑后的标记语言，并原子替换数据库题目索引）.
- Missing or unverified answers remain unverified and may provide style evidence only（缺失或未验证答案保持未验证状态，只能提供风格证据）.

## Copyright and Security（版权与安全）

- Do not commit complete copyrighted papers unless redistribution is clearly licensed（除非明确允许再分发，否则不得提交完整版权试卷）.
- Runtime assets under `raw/`, `parsed/`, and `structured/` are ignored by Git（版本控制）by default（默认忽略运行时资产）.
- Automatic sync accepts only configured HTTPS（安全网址）hosts and rejects private, loopback, link-local, executable, oversized, and malicious redirect targets（自动同步只接受已配置安全主机，并拒绝私网、回环、链路本地、可执行文件、超限文件和恶意重定向目标）.
- The application does not bypass login, payment, captcha, or anti-bot controls（应用不会绕过登录、付费、验证码或反爬限制）.
