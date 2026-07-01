# Lang Drill Agent（语言学习训练 Agent）

Lang Drill Agent（语言学习训练 Agent）是一个面向长期语言学习、刷题训练、错题复盘和考试备考的多 Agent（智能体）系统。它把 `语言学习-lang-drill-skill` 制作为可运行项目，同时支持 CLI（Command Line Interface，命令行接口）和 Web（网页）前端。

当前公开定位重点面向英语四级/六级（CET-4/CET-6，大学英语四级/六级）、法语四级（CFT-4，大学法语四级）与日语四级/六级（CJT4/CJT6，大学日语四级/六级）备考：围绕考纲词汇、语法范围、阅读/听力/翻译/写作题型、真题试卷资产、错题回流和间隔复习，把“每天刷什么、怎么判题、错题何时回来”沉淀为可追踪的学习流程。

系统采用“前端展示层 + 后端状态机 + 动态提示词组装 + 多 Agent（智能体）协作”的架构。数据库是唯一正式学习状态来源，聊天上下文只作为交互记录，不作为权威学习记忆。

## 项目定位

Lang Drill Agent（语言学习训练 Agent）不是单一巨型 prompt（提示词），而是一套可追踪、可验证、可扩展的学习系统：

- 用数据库保存学习目标、会话、题目、作答、错题、分支对话、考纲来源和模型调用记录。
- 用 Prompt Engine（提示词引擎）按任务动态组装规则，只注入当前任务需要的上下文。
- 用 Validator（校验器）独立检查结构化题目质量，避免题目、答案、讲解和 knowledge_tags（知识标签）直接裸写入库。
- 用 Token Accounting（令牌统计）记录模型、prompt_modules（提示词模块）、token（令牌）用量、耗时和校验结果，便于追踪质量问题。
- 用 CLI（命令行接口）和 Web（网页）共享同一个后端内核，避免维护两套业务逻辑。

## 核心能力

- 日常学习面板：按当天会话日期显示学习计划、题量、准确率、复习内容和摘要。
- 长期学习总面板：展示当前考试的题目完成/总数、单词掌握/总数、整体正确率、考试倒计时和累计 token（令牌）。
- 聊天式学习入口：像常见 AI（人工智能）聊天工具一样输入普通寒暄、学习建议、今日学习内容、答案或追问；普通聊天不会自动生成题组，只有明确词表或显式“出题 / 练习 / 刷题 / 考我”等学习动作才进入组卷。
- 结构化出题：Question Author（出题 Agent）按今日学习内容、复习内容、考纲规则和真题试卷解析结果生成题目。
- 历年真题参考：默认选择当前考试近 3 年真题试卷；用户可在考纲设置中勾选参考试卷、添加来源网站，点击“加入试卷”展开导入栏后选择/拖入本地试卷文件或粘贴已提取文本，系统会保存到 `papers/<考试>/raw` 并生成 `papers/<考试>/parsed` 解析 JSON（JSON 数据交换格式），同时控制组卷阶段允许生成的题型。
- 判题讲解：Evaluator Tutor（判题讲解 Agent）负责复杂题型判分、错误诊断、讲解、错题归因和当日总结。
- 分支对话：拖选文本或右键消息后开启右侧分支小窗，共享必要主上下文，默认不写回主会话，可继续发送分支消息。
- 手机映像与截图导入：右侧工作台预留 scrcpy（开源手机映像工具）/adb（安卓调试桥）手机操控链路，并支持把手机背词截图的 OCR（文字识别）文本导入为知识项后自动创建考试式练习题组；截图导入面板可把多张图片、PDF（Portable Document Format，便携式文档格式）、DOCX（Word 文档格式）或文本文件拖入待解析队列，也可点击“选择文件”从本机文件管理器选择，点击“解析文本”后再统一抽取内容。
- 快速开始：长期学习总面板底部提供“当日导入 / 快速开始”。当前查看的会话或当日面板没有导入/题组时打开右侧截图导入并给出本地提示；当前面板已有内容时自动发送“继续当前题组”。
- 主聊天截图导入：用户把 3 个以上截图词条直接粘贴到主聊天栏时，后端复用侧边栏截图导入流程，自动创建截图练习会话、导入词表并生成题组；主聊天文本框也可拖入文件并把抽取文本追加到输入框；支持“单词独占一行 + 下一行释义”、`word n. 释义` 和 `word: 释义` 等常见格式。
- 聊天图片分流：设置页可声明当前模型是否支持图片输入；支持视觉的模型会直接接收聊天栏拖入图片，不支持视觉的模型会先走 MinerU/RapidOCR（文档解析/本地文字识别）抽取文本。
- 上下文与压缩：聊天输入框发送按钮左侧显示上下文容量圆圈，默认上限 1,000,000 token（令牌）；设置页可修改上限，圆圈弹窗可主动压缩上下文。LLMLingua（提示词压缩库）作为可选增强，默认使用本地抽取式摘要兜底。
- 题目数据库目录：设置页“数据”页签可查看当前 SQLite（轻量数据库）运行库路径、题目/作答/会话计数、数据库大小，可通过本机文件夹选择器填写保存位置，并把题目数据库迁移到自定义文件夹或初始化新的空库。
- 题目吸附显示：当前正在回答的题目在聊天滚动时保持可见，避免题目被滑走。
- 可拖拽三栏工作台：左侧学习栏和右侧工作台边界可拖拽调整并持久化宽度；折叠右侧栏或切换分支/截图导入页签不会丢失截图导入队列、解析状态或识别文本。
- 模型供应商配置：支持 Mock（本地模拟）、OpenAI-compatible（OpenAI 兼容）、国内常见供应商、本地模型和自定义 Base URL（基础网址）/API Key（接口密钥）/模型名称；设置页可明确把当前供应商和模型设为默认模型。
- Agent 设置权限：设置页提供“权限”页签；截图导入、学习数据库写入、历年真题草稿、联网功能、考试目标和上下文容量等非敏感权限默认开启；Skills（技能）默认关闭，模型配置、配置自定义模型、API Key（接口密钥）、MinerU token、数据迁移等敏感设置默认关闭，开启后关键保存仍由用户手动确认。
- Skills（技能）：设置页提供 Skills 页签，分开展示内置联网检索和本地 Skills；内置联网检索只受“联网功能”权限控制且默认开启，本地 Skills 默认关闭，需要先开启 Skills 权限再逐个启用具体技能。
- 学习算法基础：内置 `mastery_score V1`（掌握度 V1），预留 FSRS（Free Spaced Repetition Scheduler，免费间隔重复调度器）接入点。

## 三 Agent（智能体）架构

### Agent 1：Orchestrator（调度器）

负责识别用户意图、选择任务流程、读取学习状态、选择提示词模块、调用工具和其他 Agent（智能体）。它不直接生成正式题目，不直接修改题目答案，不跳过数据库校验。

### Agent 2：Question Author（出题 Agent）

负责根据今日学习内容、复习内容、考纲规则、真题试卷解析结果、题量预算和 knowledge_tags（知识标签）生成结构化题目。输出必须符合 JSON Schema（JSON 结构规范），并由 Validator（校验器）校验后才能持久化。

### Agent 3：Evaluator Tutor（判题讲解 Agent）

负责复杂题型判分、错误诊断、讲解生成、错题归因、当日总结和学习反馈。简单选择题可由程序直接判定，减少无意义 token（令牌）消耗。

## 架构组件

- Frontend（前端）：React（前端框架） + TypeScript（类型化 JavaScript） + Vite（前端构建工具） + GSAP（GreenSock Animation Platform，动画库）。
- Backend（后端）：FastAPI（Web API 框架） + Typer（CLI 框架） + Pydantic（数据校验） + SQLite（轻量数据库）。
- Prompt Registry（提示词注册表）：维护提示词模块的 `id`、`version`、`scope`、`task_type`、`exam_id`、`priority`、`token_budget`、`dependencies`、`content`、`enabled`。
- Prompt Assembly（提示词组装）：按任务组装 core rules（核心规则）、task rules（任务规则）、exam rules（考试规则）、selected context（选中上下文）、output schema（输出结构）和 user preferences（用户偏好）。
- Context Pack（上下文包）：只携带当前用户目标、当前考试、当前会话状态、当前题目或候选知识点、相关考纲片段、最近错误摘要、必要输出格式和禁止事项。
- Question Validation（题目校验）：独立检查题目结构、答案、讲解、knowledge_tags（知识标签）和题型字段。
- Audit/Reconciliation（审计与对账）：保留模型调用、token（令牌）用量、提示词模块、耗时和校验结果。

## 日常学习流程

1. 用户打开 Web（网页）前端，空白上下文展示长期学习总面板。
2. 用户在聊天栏发送今日学习内容、答案或学习请求。
3. Orchestrator（调度器）创建或读取当日会话，初始化当日学习面板。
4. 后端选择今日新学内容、到期复习、低掌握度知识点和错题回流内容。
5. Question Author（出题 Agent）一次生成完整正式题组，Validator（校验器）通过后整套入库。
6. 前端只展示当前待答题；题目卡片跟随最新回复显示，等待模型时显示 thinking（思考）加载。
7. 用户作答后，程序先做客观判定并写入作答事实，再交给 Evaluator Tutor（判题讲解 Agent）结合用户背景、当前会话上下文和题目解释生成个性化讲解。
8. 系统回写作答结果、错题归因、掌握度和 token（令牌）记录，并自动返回下一道待答题。
9. 题目完成后生成当日总结，并给出学习反馈和下一步复习建议。

截图词表导入流程：右侧工作台可先拖入多张截图/文档，也可点击“选择文件”从本机文件管理器选择；文件会停留在待解析队列中；点击“解析文本”后才进行 OCR（文字识别）/文本抽取并填入识别文本框。确认文本后点击“导入并开始练习”，后端会新建截图词表练习会话、写入本次词表、自动生成完整题组并展示第 1 题。主聊天栏粘贴 3 个以上截图词条也会复用同一导入流程。词表可使用“单词独占一行 + 下一行释义”、`word n. 释义` 或 `word: 释义` 格式；解析器会过滤手机状态栏、词书标题、底部导航等 UI（User Interface，用户界面）噪声，能唯一匹配时修复截断英文词，缺少释义的词条会跳过并返回诊断信息。题目必须是考试式语境题，例如英文句子空缺、阅读语境选择或同义改写，不能只是中文释义匹配。

## Web（网页）前端

Web（网页）前端包含三个主区域：

- 左侧模块：当日学习面板、按日期分组的会话列表、可折叠/可拖拽调宽侧边栏和左下角设置入口。
- 中间模块：主聊天界面、长期学习总面板、题目框、聊天栏和题目吸附显示。
- 右侧模块：分支对话界面，默认折叠，未创建分支时显示“目前没有分支对话”。
- 右侧工作台：包含分支、手机映像、截图导入和语音预留；右侧栏可拖拽调宽，折叠或切换页签时保留截图导入和分支草稿状态；旧组词器和 Anki（记忆卡工具）导出已归档，不再进入运行路径。
- 聊天输入区：模型快捷配置中的思考等级下拉是当前原生 thinking level（思考等级）的显示与切换入口，切换模型时按新模型能力刷新档位，不额外追加“当前：开启”这类重复状态标签；输入框右下角发送按钮左侧显示上下文容量白色占比圆环，悬浮可查看占用和执行上下文压缩。
- 主题背景：浅色主题使用 CSS（层叠样式表）微纹理；深色主题使用 `frontend/public/assets/dark-theme-bg.jpg` 作为低对比深色微纹理背景，避免纯黑背景压暗学习界面。

设置面板包含：

- 模型提供商、Base URL（基础网址）、API Key（接口密钥）、模型名称、自定义模型入口、当前模型视觉能力和 MinerU token（用户信息）配置。
- 使用统计，展示累计 token（令牌）、会话数、消息数、活跃天数、连续天数、最常用模型、近 30 天活动热力、模型用量分布和上下文容量上限。
- 数据，展示当前用户数据目录、题目数据库路径、测试数据目录、数据库大小和核心表计数；支持打开本机文件夹选择器、迁移当前数据库到自定义文件夹或初始化空库。
- 当前考试、目标语言、考试时间、学习目标和学习背景。
- 考纲与历年真题：展示当前考纲、当前参考的历年真题试卷、来源网站、原始试卷路径、解析 JSON（JSON 数据交换格式）路径、点击“加入试卷”后展开的文件选择/拖拽/文本导入入口、重新解析入口和从考纲/试卷提炼出的题型勾选项；英语四/六级默认来源网站为 `https://www.guojiya.cn/#exams`。
- 权限：控制会话 Agent 可触发的程序能力；非敏感权限默认开启，Skills 扩展权限默认关闭，敏感设置权限默认关闭且集中展示，授权后仍只填入草稿，所有敏感保存动作需要用户确认。
- Skills：分开展示内置联网检索、本地 Skills（技能）根目录、已安装技能、无密钥技能数量和单个 Skill 启用/关闭开关；内置联网检索不依赖本地 Skills 开关。
- 个性化设置、全局提示词、Agent（智能体）性格选择和自定义人格提示词。
- 学习算法、联网检查、分支写回策略、字体大小、主题颜色和跟随系统主题。
- 重新打开初始化设置入口。

## CLI（命令行接口）

CLI（命令行接口）适合脚本化、终端工作流和快速调试：

```powershell
py -m langdrill_agent.cli status
py -m langdrill_agent.cli data-paths
py -m langdrill_agent.cli set-question-db-folder "D:\LangDrill\user-data" --migrate
py -m langdrill_agent.cli backup-user-data
py -m langdrill_agent.cli chat "今天学习まで、から和に的区别"
py -m langdrill_agent.cli import-skill --source "D:\1Folder\语言学习-lang-drill\语言学习-lang-drill-skill"
```

## 安装

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
cd frontend
npm install
```

## 启动

Windows 一键启动：

```powershell
.\start.bat
```

`start.bat` 是轻量入口，实际启动逻辑在 `scripts/dev/start-dev.ps1`。脚本会自动初始化默认英语/CET-4 档案，保留并规范化已有 API Key（接口密钥），清理 `5173` / `8000` 端口，在后台启动后端 `http://127.0.0.1:8000` 和前端 `http://127.0.0.1:5173`，等待两个 HTTP（HyperText Transfer Protocol，超文本传输协议）健康检查通过后再打开浏览器。

运行日志写入：

- 后端：`logs/langdrill-backend.out.log` / `logs/langdrill-backend.err.log`
- 前端：`logs/langdrill-frontend.out.log` / `logs/langdrill-frontend.err.log`

停止服务：

```powershell
.\stop.bat
```

手动启动后端：

```powershell
.\.venv\Scripts\Activate.ps1
py -m langdrill_agent.cli init --display-name boss --target-language 英语 --exam-id cet4 --exam-name 大学英语四级
py -m langdrill_agent.cli serve --reload
```

手动启动前端：

```powershell
cd frontend
npm run dev
```

默认访问 `http://127.0.0.1:5173`。

## 模型供应商

`.env.example` 只保存占位变量。真实 key（密钥）写入 `.env`，不要提交。API Key（接口密钥）建议只填写纯密钥；后端会兼容清理误粘贴的 `apikey:` / `Bearer:` 前缀，若包含换行或中文冒号等非 ASCII（非英文半角）字符会返回可读错误。

支持模式：

- `mock`：本地模拟，无需 key（密钥），只用于自动测试和离线调试；普通 Web（网页）启动会回到真实默认供应商。
- `openai`：OpenAI/GPT，默认 OpenAI-compatible Chat Completions（OpenAI 兼容聊天补全）格式。
- `claude`：Claude，默认 Anthropic Messages（Anthropic 消息接口）格式。
- `deepseek`：DeepSeek（深度求索），默认 OpenAI-compatible Chat Completions（OpenAI 兼容聊天补全）格式。
- `mimo`：Xiaomi MiMo（小米 MiMo），默认 Anthropic Messages（Anthropic 消息接口）格式。
- 自定义供应商只有在设置页点击“添加供应商”并保存后才出现。

网页设置和聊天栏快捷配置都会写入后端模型配置；供应商、模型名称和 Base URL（基础网址）同步写入本地 `.env`：

- `LANGDRILL_DEFAULT_PROVIDER`：当前供应商。
- `LANGDRILL_DEFAULT_MODEL`：当前模型名称。
- `LANGDRILL_PROVIDER_BASE_URL`：当前 Base URL（基础网址）。
- `LANGDRILL_PROVIDER_API_KEY`：当前 API Key（接口密钥）兼容变量。
- `LANGDRILL_PROVIDER_API_KEY_OPENAI`、`LANGDRILL_PROVIDER_API_KEY_CLAUDE`、`LANGDRILL_PROVIDER_API_KEY_DEEPSEEK`、`LANGDRILL_PROVIDER_API_KEY_MIMO`：默认真实供应商专属 API Key（接口密钥）。
- `LANGDRILL_ENABLE_LLMLINGUA`：设为 `1` 后，主动压缩上下文会尝试使用可选依赖 LLMLingua；未启用时使用本地抽取式摘要。
- `LANGDRILL_PAPER_ROOT`：历年真题原始文件和解析 JSON（JSON 数据交换格式）的根目录；默认 `./papers`。
- `LANGDRILL_MIGRATE_LEGACY_DB`：设为 `1` 才从项目内历史 `data/langdrill_agent.db` 复制旧库；默认不复制，避免无污染测试库被旧数据污染。
- `MINERU_TOKEN`：MinerU 精准解析 token，属于用户信息，只写入本地 `.env` 或进程环境；设置页只显示是否已配置和脱敏预览。官方 token 获取地址：[https://mineru.net/apiManage/token](https://mineru.net/apiManage/token)，API 文档：[https://mineru.net/apiManage/docs](https://mineru.net/apiManage/docs)。

可选安装上下文压缩增强：

```powershell
pip install -e .[context-compression]
```

可选安装真题文件解析增强：

```powershell
pip install -e .[paper-parsing]
```

内置解析器优先处理 Markdown（Markdown 文本格式）/TXT（纯文本格式）；安装增强依赖后可解析 PDF（Portable Document Format，便携式文档格式）、DOCX（Word 文档格式）和图片本地 OCR（文字识别）。若本机安装 MinerU CLI（MinerU 命令行工具），配置 `MINERU_TOKEN` 时会优先使用 `mineru-open-api extract` 精准解析；未配置 token 时使用 `mineru-open-api flash-extract` 轻量解析：

```powershell
npm install -g mineru-open-api
```

拖拽上传的试卷文件、截图文件和非视觉模型下的聊天图片会先走后端文本抽取；TXT（纯文本格式）/Markdown（Markdown 文本格式）直接读取，PDF（便携式文档格式）优先使用 `pypdf`，DOCX（Word 文档格式）使用 `python-docx`，图片优先使用 MinerU CLI（MinerU 命令行工具）并在失败时回退到 RapidOCR（本地文字识别），PPTX（PowerPoint 文档格式）和 XLSX（Excel 工作簿格式）仍依赖可选 MinerU CLI。解析结果只保留组卷需要的章节、题型、短摘录、摘要、来源和路径。

聊天栏快捷模型选择只显示已启用、已配置 API Key（接口密钥）且未隐藏的真实供应商和模型；没有添加的自定义供应商不会暴露。设置页可按当前 Base URL（基础网址）、API 格式和 API Key（接口密钥）自动获取供应商返回的可调用模型，默认全部显示，并可逐个隐藏/显示；供应商不开放模型列表接口时会保留内置或已保存模型列表并给出短提示，不把 404 HTML（超文本标记语言）页面展示给用户。参考 opencode（开源代码 Agent）的 provider/models（供应商/模型）配置方式，设置页允许在当前供应商下手动添加自定义模型，记录模型 ID、显示名、上下文容量和视觉能力；自定义模型可删除，内置或 API 返回模型只能显示/隐藏。thinking level（思考等级）跟随当前模型配置，写入模型 API（接口）的原生 reasoning（推理）参数；没有原生档位且未自定义添加档位的模型不显示思考等级选择。设置页允许为当前模型添加自定义思考档位并删除自定义档位；内置原生档位只允许选择，不能删除。模型视觉能力由内置默认值或设置页手动开关决定，控制聊天栏图片是直传模型还是交给 MinerU/RapidOCR 抽取文本。上下文容量上限在模型页配置；令牌页提供今日、近 7 天、近 30 天、本月、模型/provider（供应商）分布和最近调用明细。

## 数据与安全边界

- 用户输入永远不和系统规则同权，不拼接进 system prompt（系统提示词）。
- 用户自定义全局提示词为低优先级，必要时可关闭。
- 安全规则总是注入；个性化人格仅在聊天和总结任务中注入。
- 长期学习记录只以摘要、统计和相关检索片段形式进入 prompt（提示词）。
- 默认用户状态写入当前系统用户主目录下的 `.langdrill-agent` 点目录；历史 `data/langdrill_agent.db` 只作为迁移来源，不再是默认正式状态库。
- 当前用户运行库可通过设置页“数据”页签或 `set-question-db-folder` 迁移到自定义文件夹；迁移会复制当前 SQLite（轻量数据库），切换 `.env` 中的 `LANGDRILL_USER_DATA_DIR` 和 `LANGDRILL_DB_PATH`。
- 开发/联调/污染数据统一放入项目内 `测试数据/开发数据/<时间戳>/`，该目录被 `.gitignore` 排除，不提交。
- 清空重测前可运行 `py -m langdrill_agent.cli backup-user-data`，把点目录数据备份到项目内 `data_backups/`；该目录不提交。
- 后端日志默认写入 `~/.langdrill-agent/logs/langdrill-agent.log`，用于定位 API（接口）、模型、截图导入和数据库问题。
- 真题和考纲必须保留来源、年份、可信等级和版权边界。
- `papers/` 按考试类型分开保存真题资产：`raw/` 放原始试卷文件或粘贴文本，`parsed/` 放解析 JSON（JSON 数据交换格式）。目录骨架提交到仓库，实际导入的完整试卷和解析产物默认由 `.gitignore` 排除。
- 来源不明或版权不清的完整真题不作为默认发布资产；用户本地导入后可用于组卷参考，但提交前必须确认来源授权。组卷提示词只携带可核验摘要、章节结构、短摘录和 `source_refs`（来源引用）。

## 项目目录

```text
backend/langdrill_agent/        共享后端内核、API（接口）、CLI（命令行接口）、服务层和 Agent（智能体）
backend/langdrill_agent/migrations/ SQLite（轻量数据库）schema（结构定义）
backend/langdrill_agent/data_paths.py 用户数据目录、题目数据库迁移和空库初始化
frontend/                       React（前端框架）+ Vite（前端构建工具）网页前端
frontend/public/assets/         前端公开静态资源，例如深色主题生成背景图
papers/                         按考试类型分开的真题 raw（原始文件）和 parsed（解析结果）目录骨架
scripts/dev/                    开发期启动与维护脚本
src-tauri/                      Tauri（桌面壳）Windows 桌面封装骨架
doc/                            架构说明、项目地图、进展记录和 README（说明文档）资源
try/                            测试和调试文件，可清理
测试数据/                       开发/联调/污染数据归档目录，不提交
archive/optimized-out/          已下线旧功能模块归档
logs/                           本地运行日志，不提交
```

## 验证

```powershell
py -m ruff check backend try
py -m pytest try
py -m pytest try/test_startup_scripts.py -q
py try\full_chain_smoke.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev\start-dev.ps1 -NoBrowser -SkipInstall
cd frontend
npm run build
```

## License（许可证）

本项目为 source-available（源码可见）项目。非商业用途按 PolyForm Noncommercial License 1.0.0（PolyForm 非商业许可证 1.0.0）授权；商业用途需要单独取得书面商业许可。详见 `LICENSE` 和 `COMMERCIAL.md`。
