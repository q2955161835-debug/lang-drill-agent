# Lang Drill Agent 项目规则

## 项目目标

Lang Drill Agent 是语言学习刷题训练 Agent（智能体），目标是把旧 `语言学习-lang-drill-skill` 的学习流程沉淀为可运行、可测试、可追踪的本地应用。项目同时提供 CLI（Command Line Interface，命令行接口）、Web（网页）前端和后续 Windows 桌面壳，服务于长期语言学习、考试备考、错题复盘、截图单词导入和间隔复习。

当前核心优化方向：
- 以数据库作为唯一正式学习状态来源，保证题组、作答、掌握度、错题和会话历史可追踪。
- 正式刷题必须先生成完整题组并写入数据库，再逐题展示、逐题判分、自动推进下一题。
- Web（网页）体验以三栏学习工作台为主：左侧学习状态，中间聊天与题目，右侧分支/手机映像/截图导入。
- 模型配置支持默认四个真实供应商 OpenAI/GPT、Claude、DeepSeek（深度求索）、MiMo（小米米魔）和保存后才出现的自定义供应商；聊天栏模型选择只暴露已启用且已配置 API Key（接口密钥）的真实供应商，Mock Provider（本地模拟供应商）只保留给自动测试和离线调试。
- 思考等级必须跟随当前模型的原生 reasoning（推理）配置；禁止把思考等级降级为提示词控制。没有原生档位或未自定义添加档位的模型，不在聊天栏暴露思考等级选择。
- 长期学习总面板必须展示真实学习统计：题目完成/总数、单词掌握/总数、整体正确率、考试倒计时和 token（令牌）累计；新聊天在正式发送前只作为本地草稿，不写入数据库会话列表。
- 启动链路必须适配中文路径、后台运行、日志落盘和 HTTP（HyperText Transfer Protocol，超文本传输协议）健康检查。
- 截图词表导入后必须自动创建独立练习会话并生成完整考试式题组；题型应使用英文语境句、完形空格、阅读问题或同义改写，禁止退化为“选择中文释义 / 最合适理解”的词卡题。
- 主聊天栏粘贴多行截图词表时必须复用截图导入后台流程，自动创建截图练习会话、导入词表并生成题组；前端等待状态需区分“截图解析中”和“题目生成中”。
- 答题提交后必须让 Evaluator Tutor（判题讲解 Agent）结合当前会话上下文、用户背景和程序判定生成个性化讲解；模型不可用时才回退基础判题，且不得丢失作答记录。
- 聊天输入区需要展示当前上下文容量占用，默认上限 1,000,000 token（令牌），支持保存自定义上限和主动压缩上下文；LLMLingua（提示词压缩库）作为可选增强，默认使用本地抽取式摘要兜底。

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
6. 如项目内存在 `external-skills-hub/SKILL.md`，先读取后再执行涉及技能扩展的工作；当前缺失时需在进展记录说明。

## 目录结构与职责

- `backend/langdrill_agent/`：共享后端核心。CLI（命令行接口）、API（接口）、服务层、Agent（智能体）、模型配置、学习算法和数据库访问都在这里。
- `backend/langdrill_agent/api.py`：FastAPI（Web API 框架）入口，负责 bootstrap（初始化加载）、chat（聊天学习）、branch（分支）、profile（用户档案）、model-config（模型配置）、exam/syllabus（考试与考纲）、phone-mirror（手机映像）和 screenshot（截图导入）接口。
- `backend/langdrill_agent/cli.py`：命令行入口，提供 init（初始化）、serve（启动服务）、status（状态）、chat（终端聊天）、data-paths（数据路径）和 backup-user-data（备份用户数据）。
- `backend/langdrill_agent/services.py`：学习状态机、题组推进、作答写入、掌握度更新、会话生命周期和业务编排。
- `backend/langdrill_agent/learning_stats.py`：长期学习统计服务，按当前考试聚合题目完成、词汇掌握和整体正确率。
- `backend/langdrill_agent/context.py`：上下文容量、会话上下文快照、主动压缩、使用统计和 token（令牌）统计口径。
- `backend/langdrill_agent/agents.py`：Orchestrator（调度器）、Question Author（出题 Agent）和 Evaluator Tutor（判题讲解 Agent）的实现。
- `backend/langdrill_agent/task_router.py`：用户意图识别与任务路由。
- `backend/langdrill_agent/providers.py`：模型供应商配置、API Key（接口密钥）读取和模型调用适配。
- `backend/langdrill_agent/screenshot_import.py`：截图 OCR（文字识别）文本到知识项的解析与导入。
- `backend/langdrill_agent/phone_mirror.py`：adb（安卓调试桥）/scrcpy（手机映像工具）环境检测和启动准备。
- `backend/langdrill_agent/migrations/`：SQLite（轻量数据库）schema（数据库结构）初始化脚本。
- `frontend/`：React（前端框架）+ TypeScript（类型化 JavaScript）+ Vite（前端构建工具）网页前端。
- `frontend/src/App.tsx`：前端主入口，负责三栏布局、聊天、设置、初始化、题目显示和右侧工作台接入。
- `frontend/src/components/`：前端可复用组件，当前重点是 `RightWorkbench.tsx` 和 `ContextMenu.tsx`。
- `scripts/dev/`：开发期启动与维护脚本。`start-dev.ps1` 是一键启动主逻辑，`start.bat` 只作为 Windows 双击入口。
- `src-tauri/`：Tauri（桌面壳）Windows 桌面封装骨架。
- `doc/`：项目地图、验收标准、人工验收清单、桌面打包说明和进展记录。
- `doc/进展记录/`：阶段性工作记录，包含完成内容、文件清单、错误汇报、验证结果和回退方案。
- `try/`：自动测试、调试脚本和临时验证文件；该目录内文件必须只服务于测试/调试，可清理后不影响项目运行。
- `archive/optimized-out/`：已从运行路径移除的旧功能归档，只作历史参考。
- `logs/`：本地运行日志，禁止提交。
- `data/`、`data_backups/`：历史项目内数据库位置和用户数据备份目录，数据库与备份禁止提交。

## 核心数据流

1. 用户从 Web（网页）或 CLI（命令行接口）发送学习请求。
2. API（接口）进入服务层，服务层读取用户档案、当前考试、会话、题组和知识项。
3. Orchestrator（调度器）判断任务类型，不把用户输入拼入 system prompt（系统提示词）。
4. Question Author（出题 Agent）一次生成完整题组，Validator（校验器）通过后写入数据库；截图词表自动练习只使用本次截图词表作为优先内容池，避免旧会话词汇污染选项。
5. 前端只展示当前待答题；用户作答后写入 attempts（作答记录），更新 questions（题目状态）和 mastery（掌握度）。
6. 简单题由程序判分，复杂题进入 Evaluator Tutor（判题讲解 Agent）。
7. 答题讲解统一由 Evaluator Tutor（判题讲解 Agent）基于程序判定、当前题、用户背景和会话上下文生成；若模型不可用，回退基础讲解但仍保存作答。
8. 系统自动返回下一道待答题；显式“下一题 / 继续 / 下一个”只读取当前题组库存，不重新初始化学习面板。
9. Bootstrap（初始化加载）、chat（聊天）、profile（用户档案）、session delete（会话删除）接口返回 `learning_stats`；chat/session/context 接口返回 `token_usage`，用于长期面板、设置页和上下文容量圆圈实时刷新。

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
