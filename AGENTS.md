# Lang Drill Agent 项目规则

## 项目目标

Lang Drill Agent 是语言学习刷题训练 Agent（智能体），目标是把旧 `语言学习-lang-drill-skill` 的学习流程沉淀为可运行、可测试、可追踪的本地应用。项目同时提供 CLI（Command Line Interface，命令行接口）、Web（网页）前端和后续 Windows 桌面壳，服务于长期语言学习、考试备考、错题复盘、截图单词导入和间隔复习。

当前核心优化方向：
- 以数据库作为唯一正式学习状态来源，保证题组、作答、掌握度、错题和会话历史可追踪。
- 正式刷题必须先生成完整题组并写入数据库，再逐题展示、逐题判分、自动推进下一题。
- Web（网页）体验以三栏学习工作台为主：左侧学习状态，中间聊天与题目，右侧分支/手机映像/截图导入。
- 模型配置支持默认四个真实供应商 OpenAI/GPT、Claude、DeepSeek（深度求索）、MiMo（小米米魔）和保存后才出现的自定义供应商；聊天栏模型选择只暴露已启用且已配置 API Key（接口密钥）的真实供应商，Mock Provider（本地模拟供应商）只保留给自动测试和离线调试。
- 设置页模型配置可声明当前模型是否具备视觉能力；聊天栏拖入图片时，具备视觉能力的模型直接接收图片附件，不具备视觉能力时前端必须走文件抽取链路交给 MinerU/RapidOCR（文档解析/本地文字识别）提取文本。
- 思考等级必须跟随当前模型的原生 reasoning（推理）配置；禁止把思考等级降级为提示词控制。没有原生档位或未自定义添加档位的模型，不在聊天栏暴露思考等级选择；聊天栏只保留思考等级选择器作为当前思考状态入口，不额外显示“当前：开启”这类重复状态标签。
- OpenAI/GPT 官方 provider（供应商）可使用 Chat Completions（聊天补全）中的 `developer` role（角色）承载上下文；DeepSeek（深度求索）、本地模型和自定义 OpenAI-compatible（OpenAI 兼容）供应商必须只发送兼容的 `system`/`user` 消息，把上下文合并进 user 内容，避免供应商拒收 `developer` role。
- 长期学习总面板必须展示真实学习统计：题目完成/总数、单词掌握/总数、整体正确率、考试倒计时和 token（令牌）累计；新聊天在正式发送前只作为本地草稿，不写入数据库会话列表。
- 长期学习总面板的“当日导入 / 快速开始”按钮必须按当前查看的 `dailyPanel` 是否有题目或词汇判断：当前面板为空时打开右侧截图导入并提示，已有导入或题组时显示“快速开始”并继续当前题组，不能仅因日期不是今天而显示“当日导入”。
- 普通寒暄、学习建议咨询和澄清问题必须作为普通聊天处理，不得自动生成题组或写入题目；只有明确词表、截图词表、显式“出题 / 练习 / 刷题 / 考我”等学习动作才进入正式组卷流程。
- 启动链路必须适配中文路径、后台运行、日志落盘和 HTTP（HyperText Transfer Protocol，超文本传输协议）健康检查。
- 内置考试包含英语四级/六级（CET-4/CET-6，大学英语四级/六级）、法语四级（CFT-4，大学法语四级）、日语四级/六级（CJT4/CJT6，大学日语四级/六级）、雅思、托福、高考英语和自定义考试；同一 CET 官网考纲页必须按语种和级别匹配，不能把法语 2023 版误判为英语四/六级最新版。
- 截图词表导入后必须自动创建独立练习会话并生成完整考试式题组；词表解析需支持“单词独占一行 + 下一行释义”、`word n. 释义` 和 `word: 释义` 等常见 OCR（文字识别）/主聊天粘贴格式，并过滤手机状态栏、词书标题、底部导航等 UI（User Interface，用户界面）噪声；疑似截断英文词只有能唯一修复时才导入，缺少释义的词条必须跳过并返回诊断信息；题型应使用英文语境句、完形空格、阅读问题或同义改写，禁止退化为“选择中文释义 / 最合适理解”的词卡题。
- 主聊天栏粘贴 3 个以上截图词条时必须复用截图导入后台流程，自动创建截图练习会话、导入词表并生成题组；主聊天文本框支持拖入 TXT（纯文本格式）/Markdown（Markdown 文本格式）/PDF（Portable Document Format，便携式文档格式）/DOCX（Word 文档格式）/图片等文件并把抽取文本追加到输入框；前端等待状态需区分“截图解析中”和“题目生成中”。
- MinerU token 属于用户信息，只能写入本地 `.env` 的 `MINERU_TOKEN`；设置页需要提供官方获取地址 `https://mineru.net/apiManage/token` 和 API 文档地址 `https://mineru.net/apiManage/docs`，后端接口只能返回是否已配置和脱敏预览，禁止返回明文 token。
- 右侧“截图导入”和设置页“手动导入试卷”必须支持文件拖拽导入：截图导入拖入文件后进入待解析队列，支持多张图片/多个文件继续追加；只有用户点击“解析文本”后才抽取 OCR（文字识别）/文本并填入识别文本框；手动导入试卷拖入文件后上传到后端，保存到 `papers/<考试>/raw` 并生成 `papers/<考试>/parsed` 解析 JSON（JSON 数据交换格式）。
- 答题提交后必须让 Evaluator Tutor（判题讲解 Agent）结合当前会话上下文、用户背景和程序判定生成个性化讲解；模型不可用时才回退基础判题，且不得丢失作答记录。刚答完的题目必须作为普通聊天回顾卡片保留，显示用户选择、正确答案和对错状态；只有当前待答题使用置顶/吸附题卡。
- 聊天输入区需要展示当前上下文容量占用，默认上限 1,000,000 token（令牌），支持保存自定义上限和主动压缩上下文；LLMLingua（提示词压缩库）作为可选增强，默认使用本地抽取式摘要兜底。
- 主聊天和右侧分支消息必须通过安全的 Markdown（标记语言）渲染组件展示基础格式，包括加粗、内联代码、列表、标题和代码块；禁止用不可信模型内容直接写入 HTML（超文本标记语言）。
- 历年真题以 `exam_assets` 中的试卷记录和 `papers/<考试>/raw`、`papers/<考试>/parsed` 中的原始/解析资产为准，默认选择近 3 年真题；出题 Agent（智能体）必须参考当前选中的真题解析结果和已勾选题型，但不得复刻或长段引用完整真题原文。
- 用户题目数据库支持自定义用户数据文件夹和迁移：模型生成给用户作答的题目、会话、作答、知识项和统计仍写入同一个 SQLite（轻量数据库）运行库；设置页“数据”页签和 CLI（命令行接口）可迁移当前库或初始化空库，Web（网页）设置页应提供本机文件夹选择按钮辅助填写目录。

## GitHub（代码托管平台）

- 仓库地址：`https://github.com/q2955161835-debug/lang-drill-agent.git`
- 仓库状态：Private（私有）

## 读取顺序

进入项目后按以下顺序读取：
1. `AGENTS.md`：项目长期规则和目录职责。
2. `doc/项目地图.md`：当前模块、数据口径和运行入口。
3. `doc/验收标准.md`：功能、交互、自动测试和人工验收清单。
4. `README.md`：对外说明、安装启动和用户视角功能。
5. 与任务直接相关的源码、测试、脚本和进展记录。

## 目录结构与职责

- `backend/langdrill_agent/`：共享后端核心。CLI（命令行接口）、API（接口）、服务层、Agent（智能体）、模型配置、学习算法和数据库访问都在这里。
- `backend/langdrill_agent/api.py`：FastAPI（Web API 框架）入口，负责 bootstrap（初始化加载）、chat（聊天学习）、branch（分支）、profile（用户档案）、model-config（模型配置）、MinerU 配置、exam/syllabus（考试与考纲）、phone-mirror（手机映像）、screenshot（截图导入）、文件文本抽取和数据路径选择接口。
- `backend/langdrill_agent/cli.py`：命令行入口，提供 init（初始化）、serve（启动服务）、status（状态）、chat（终端聊天）、data-paths（数据路径）和 backup-user-data（备份用户数据）。
- `backend/langdrill_agent/services.py`：学习状态机、题组推进、作答写入、掌握度更新、会话生命周期和业务编排。
- `backend/langdrill_agent/services.py` 中的 `PastPaperService`：历年真题试卷资产、默认近三年选择、题型开关、手动导入、重新解析和联网搜索导入索引。
- `backend/langdrill_agent/paper_assets.py`：历年真题目录、原始文件保存、PDF（Portable Document Format，便携式文档格式）/DOCX（Word 文档格式）/Markdown（Markdown 文本格式）/图片文件文本抽取、解析 JSON（JSON 数据交换格式）生成和短摘录提取；配置 `MINERU_TOKEN` 时使用 MinerU 精准解析，否则使用 MinerU 轻量解析；图片 OCR（文字识别）失败时回退 RapidOCR（本地文字识别），复杂文档依赖可选 MinerU CLI。
- `backend/langdrill_agent/learning_stats.py`：长期学习统计服务，按当前考试聚合题目完成、词汇掌握和整体正确率。
- `backend/langdrill_agent/context.py`：上下文容量、会话上下文快照、主动压缩、使用统计和 token（令牌）统计口径。
- `backend/langdrill_agent/data_paths.py`：用户数据目录、题目 SQLite（轻量数据库）路径状态、迁移、空库初始化、本机文件夹选择和 `.env` 路径账本更新。
- `backend/langdrill_agent/agents.py`：Orchestrator（调度器）、Question Author（出题 Agent）和 Evaluator Tutor（判题讲解 Agent）的实现。
- `backend/langdrill_agent/task_router.py`：用户意图识别与任务路由。
- `backend/langdrill_agent/providers.py`：模型供应商配置、API Key（接口密钥）读取和模型调用适配。
- `backend/langdrill_agent/screenshot_import.py`：截图 OCR（文字识别）文本到知识项的解析与导入，支持词条换行、词性内联和冒号分隔格式。
- `backend/langdrill_agent/phone_mirror.py`：adb（安卓调试桥）/scrcpy（手机映像工具）环境检测和启动准备。
- `backend/langdrill_agent/migrations/`：SQLite（轻量数据库）schema（数据库结构）初始化脚本。
- `frontend/`：React（前端框架）+ TypeScript（类型化 JavaScript）+ Vite（前端构建工具）网页前端。
- `frontend/src/App.tsx`：前端主入口，负责三栏布局、聊天、设置、初始化、当前题吸附显示、已答题回顾卡片和右侧工作台接入。
- `frontend/src/components/`：前端可复用组件，当前重点是 `RightWorkbench.tsx`、`ContextMenu.tsx` 和 `MarkdownText.tsx`。
- `papers/`：按考试类型分开的历年真题资产目录骨架；`raw/` 存原始试卷或粘贴文本，`parsed/` 存解析 JSON（JSON 数据交换格式），实际导入内容默认不提交。
- `scripts/dev/`：开发期启动与维护脚本。`start-dev.ps1` 是一键启动主逻辑，`start.bat` 只作为 Windows 双击入口。
- `src-tauri/`：Tauri（桌面壳）Windows 桌面封装骨架。
- `doc/`：项目地图、验收标准、人工验收清单、桌面打包说明和进展记录。
- `doc/进展记录/`：阶段性工作记录，包含完成内容、文件清单、错误汇报、验证结果和回退方案。
- `try/`：自动测试、调试脚本和临时验证文件；该目录内文件必须只服务于测试/调试，可清理后不影响项目运行。
- `测试数据/`：从正式运行路径迁出的开发/联调/污染数据，按时间戳分类保存；该目录禁止提交，可清理但清理前应确认不再需要回溯。
- `archive/optimized-out/`：已从运行路径移除的旧功能归档，只作历史参考。
- `logs/`：本地运行日志，禁止提交。
- `data/`、`data_backups/`：历史项目内数据库位置和用户数据备份目录，数据库与备份禁止提交。
- 运行时不再默认从项目内 `data/langdrill_agent.db` 自动复制旧库；只有显式设置 `LANGDRILL_MIGRATE_LEGACY_DB=1` 才执行旧库迁移，避免污染新用户库。

## 核心数据流

1. 用户从 Web（网页）或 CLI（命令行接口）发送学习请求。
2. API（接口）进入服务层，服务层读取用户档案、当前考试、会话、题组和知识项。
3. Orchestrator（调度器）判断任务类型，不把用户输入拼入 system prompt（系统提示词）。
4. Question Author（出题 Agent）一次生成完整题组，Validator（校验器）通过后写入数据库；截图词表自动练习只使用本次截图词表作为优先内容池，避免旧会话词汇污染选项。
5. 组卷阶段读取当前考试的考纲版本、已选择历年真题试卷、解析章节、短摘录和已勾选题型；提示词只携带来源、题型、解析摘要和必要短摘录，禁止把完整真题作为默认发布内容。
6. 聊天栏图片输入按当前模型 `vision` 能力分流：视觉模型走多模态模型调用；非视觉模型走 `/api/files/extract-text` 并由 MinerU/RapidOCR 提取文本后再进入普通聊天或截图词表流程。
7. 前端以吸附题卡展示当前待答题；用户作答后写入 attempts（作答记录），更新 questions（题目状态）和 mastery（掌握度），并把上一题结构化快照写入助手消息 payload（附加数据）供回顾。
8. 简单题由程序判分，复杂题进入 Evaluator Tutor（判题讲解 Agent）。
9. 答题讲解统一由 Evaluator Tutor（判题讲解 Agent）基于程序判定、当前题、用户背景和会话上下文生成；若模型不可用，回退基础讲解但仍保存作答；前端在讲解消息中渲染已答题回顾卡片，不把已答题继续置顶。
10. 系统自动返回下一道待答题；显式“下一题 / 继续 / 下一个”只读取当前题组库存，不重新初始化学习面板。
11. Bootstrap（初始化加载）、chat（聊天）、profile（用户档案）、session delete（会话删除）接口返回 `learning_stats`；chat/session/context 接口返回 `token_usage`，其中 chat/session/context 的上下文容量字段必须按当前会话计算，用于长期面板、设置页和上下文容量圆圈实时刷新。

## 启动与停止

一键启动：

```powershell
.\start.bat
```

启动规则：
- `start.bat` 只负责调用 `scripts/dev/start-dev.ps1`。
- `scripts/dev/start-dev.ps1` 负责创建 `.venv`、安装依赖、写入开发期默认 MiMo（小米米魔）配置、保留并规范化已有 API Key（接口密钥）、初始化数据库、清理端口、后台启动服务、写入日志和等待 HTTP（超文本传输协议）健康检查。
- 浏览器只能在 `http://127.0.0.1:8000/docs` 与 `http://127.0.0.1:5173` 均可访问后打开。
- 后端日志：`logs/langdrill-backend.out.log` 与 `logs/langdrill-backend.err.log`。
- 前端日志：`logs/langdrill-frontend.out.log` 与 `logs/langdrill-frontend.err.log`。

停止服务：

```powershell
.\stop.bat
```

手动后端：

```powershell
.\.venv\Scripts\Activate.ps1
py -m langdrill_agent.cli init
py -m langdrill_agent.cli serve --reload
```

手动前端：

```powershell
cd frontend
npm run dev
```

## 常用命令

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
py -m langdrill_agent.cli status
py -m langdrill_agent.cli data-paths
py -m langdrill_agent.cli set-question-db-folder "D:\LangDrill\user-data" --migrate
py -m langdrill_agent.cli backup-user-data
cd frontend
npm install
npm run dev
```

## 测试命令

```powershell
py -m pytest try -q
py -m ruff check backend try
cd frontend
npm run build
```

针对启动脚本：

```powershell
py -m pytest try/test_startup_scripts.py -q
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev\start-dev.ps1 -NoBrowser -SkipInstall
```

## 允许修改范围

- 任务相关的 `backend/langdrill_agent/`、`frontend/src/`、`scripts/`、`doc/`、`try/`。
- 新增测试必须放入 `try/`。
- 新增开发脚本优先放入 `scripts/dev/`，并同步更新 `AGENTS.md` 与验收标准。
- 文档更新优先修改 `AGENTS.md`、`doc/项目地图.md`、`doc/验收标准.md`、`README.md` 和当天进展记录。

## 禁止修改范围

- 禁止提交 `.env`、真实 API Key（接口密钥）、token（令牌）、cookie（浏览器凭据）、数据库、日志、私有学习数据。
- 禁止把来源不明或版权不清的完整真题内容加入默认发布资产。
- 禁止把用户输入提升为 system prompt（系统提示词）同级规则。
- 禁止把旧 skill（技能）项目中的私有题库或完整真题原文直接搬入本项目。
- 禁止在未记录回退方案时做批量删除、结构性重构或高风险迁移。

## 环境变量账本

- `.env` 是真实环境变量账本，必须留在 `.gitignore` 中，禁止提交。
- `.env.example` 是假账本，只存变量名、占位值和必要说明。
- 新增、删除或改名环境变量时，同步更新 `.env.example`、代码读取逻辑、启动文档和部署说明。
- `start-dev.ps1` 只写入开发期默认 `LANGDRILL_DEFAULT_PROVIDER`、`LANGDRILL_DEFAULT_MODEL`、`LANGDRILL_PROVIDER_BASE_URL`，必须保留已有 `LANGDRILL_PROVIDER_API_KEY` 与 `LANGDRILL_PROVIDER_API_KEY_<PROVIDER_ID>` 形式的供应商专属密钥，并在保留时清理常见 `apikey:` / `Bearer:` 粘贴前缀。
- 默认真实供应商密钥变量：`LANGDRILL_PROVIDER_API_KEY_OPENAI`、`LANGDRILL_PROVIDER_API_KEY_CLAUDE`、`LANGDRILL_PROVIDER_API_KEY_DEEPSEEK`、`LANGDRILL_PROVIDER_API_KEY_MIMO`；自定义供应商使用同规则生成的动态变量名。
- `LANGDRILL_ENABLE_LLMLINGUA=1` 时，主动压缩上下文可尝试使用可选依赖 LLMLingua；未启用或不可用时使用本地抽取式摘要兜底。
- `LANGDRILL_PAPER_ROOT` 控制历年真题原始文件和解析 JSON（JSON 数据交换格式）根目录，默认 `./papers`；真实完整试卷建议保存在本地私有目录或保持 `.gitignore` 排除。
- `MINERU_TOKEN` 是 MinerU 精准解析 token，属于用户信息；真实值只允许写入 `.env` 或进程环境，不得提交或写入文档、进展记录和聊天代码块。
- `LANGDRILL_MIGRATE_LEGACY_DB=1` 时才允许从项目内历史 `data/langdrill_agent.db` 复制旧库到当前用户点目录；默认不迁移，避免污染无数据测试库。
- API Key（接口密钥）应保存纯密钥值；后端会清理常见粘贴前缀 `apikey:` / `Bearer:`，但发现换行或非 ASCII（非英文半角）字符时必须返回可读错误，不能让 `httpx` 请求头编码异常直接暴露给前端。
- 如怀疑敏感信息已经提交到 GitHub（代码托管平台），必须提醒用户撤销旧密钥、创建新密钥并清理 Git 历史。

## 验收标准与报告

- 功能验收以 `doc/验收标准.md` 为准。
- 用户体验回归以 `doc/manual-acceptance-checklist.md` 为准。
- 每个阶段性任务完成后，检查并更新相关验收项；新增功能必须新增验收项，删除功能必须移除或标记废弃。
- 最终报告必须说明本轮涉及的验收项、验证命令、验证结果、未通过项、未验证项和原因。

## 安全与回退

- 结构性修改前必须确认 Git（版本控制）状态，并提交一次变更前检查点。
- 高风险操作前更新 `doc/进展记录/YYYY-M-D.md`，写明高风险标记和回退方案。
- 除 Git（版本控制）外，高危操作备份统一保存到 `D:\0文件夹\备份` 的清晰时间戳子目录。
- 发现问题后先定位根因，再修改；连续三次调试无效后进行技术社区方案查找。
