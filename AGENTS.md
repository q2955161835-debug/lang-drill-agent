# Lang Drill Agent 项目规则

## 项目目标

Lang Drill Agent 是语言学习刷题训练 Agent（智能体），目标是把旧 `语言学习-lang-drill-skill` 的学习流程沉淀为可运行、可测试、可追踪的本地应用。项目正式使用方式和对外定位以 Web（网页）三栏学习工作台为核心；Windows 桌面版通过 Tauri（桌面应用框架）承载同一 Web（网页）体验并启动本地 FastAPI（Web API 框架）后端；CLI（Command Line Interface，命令行接口）保留为开发、调试、自动化和数据维护辅助入口，不作为普通用户学习主路径。

当前核心优化方向：
- 以数据库作为唯一正式学习状态来源，保证题组、作答、掌握度、错题和会话历史可追踪。
- 正式刷题必须先生成完整题组并写入数据库，再逐题展示、逐题判分、自动推进下一题。
- Question Author（出题 Agent）调用模型失败、超时或返回不可用时，必须使用本地规则兜底生成完整考试式题组并写入数据库；组卷前 Orchestrator（调度器）规划模型失败或超时也不得阻断后续 Question Author（出题 Agent）写题，不能让正式练习、截图导入自动练习或主聊天词表练习在组卷阶段中断。
- 正式学习、截图导入、模型配置、题目数据库迁移和验收流程优先通过 Web（网页）完成；CLI（命令行接口）已有功能不删除，但只作为维护、调试和脚本化兜底。
- Web（网页）体验以三栏学习工作台为主：左侧学习状态，中间聊天与题目，右侧分支/手机映像/截图导入。
- 桌面版必须复用同一前端和后端业务能力，不改变 `start.bat`、`scripts/dev/start-dev.ps1`、Vite（前端构建工具）代理和浏览器访问路径的语义；桌面构建通过独立 `scripts/desktop/` 脚本和 `src-tauri/` 工程完成。
- Web（网页）三栏边界必须可拖拽调整并持久化左右栏宽度；折叠侧栏或切换右侧工作台页签时不得卸载工作台内部状态，截图导入的待解析队列、解析状态、识别文本和已解析可编辑词条卡必须保留。
- 右侧分支页必须同时支持右键/选中文本引用、普通点击路径和无引用直接追问；当前会话有待答题题卡时，应能直接基于当前题目创建分支引用，避免分支功能依赖浏览器右键或文本拖选能力；没有选择内容或引用卡时，用户也可以直接在分支输入框发送消息，后端必须以当前主会话消息作为背景；引用状态必须先展示在分支页，用户输入提示词后提交，或留空按默认提示词提交，禁止把选中文本直接作为用户消息发送。
- 模型配置支持默认四个真实供应商 OpenAI/GPT、Claude、DeepSeek（深度求索）、MiMo（小米米魔）和保存后才出现的自定义供应商；设置页可按当前 Base URL（基础网址）、API 格式和 API Key（接口密钥）从供应商模型列表接口自动获取可调用模型，并给每个模型维护聊天栏显示/隐藏开关，默认全部显示；若供应商未开放模型列表接口，刷新必须保留内置或已保存模型列表，不得把 404 HTML（超文本标记语言）错误页直接展示给用户；设置页允许在当前供应商下手动添加自定义模型，记录模型 ID、显示名、上下文容量和视觉能力，自定义模型可删除，内置或 API 返回模型不可删除；聊天栏模型选择只暴露已启用、已配置 API Key 且未隐藏的真实供应商/模型，Mock Provider（本地模拟供应商）只保留给自动测试和离线调试。
- 设置页必须维护 Agent 设置权限；截图导入、学习数据库写入、历年真题草稿、联网功能、考试目标和上下文容量等非敏感权限默认开启；模型配置、配置自定义模型、密钥、数据迁移、MinerU token 等敏感设置集中放在下方并默认关闭，开启后会话 Agent 也只能生成可确认草稿或打开对应设置动作，关键保存仍必须由用户确认执行。
- 联网功能必须与拓展 Skills（拓展技能）拆分：内置联网检索是始终开启的内置工具，不需要个人 API Key（接口密钥）或 token（令牌）；实际联网调用仍受“联网功能”权限控制。拓展 Skills 不再有全局总权限，Multi Search Engine（多搜索引擎）默认启用用于生成可审计搜索入口，其它拓展 Skill 默认关闭；所有拓展 Skill 都由“拓展 Skills”页的单项开关独立控制，不能影响内置工具是否可用。
- 设置页模型配置可声明当前模型是否具备视觉能力；聊天栏拖入图片时，具备视觉能力的模型直接接收图片附件，不具备视觉能力时前端必须走文件抽取链路交给 MinerU/RapidOCR（文档解析/本地文字识别）提取文本。
- 思考等级必须跟随当前模型的原生 reasoning（推理）配置；禁止把思考等级降级为提示词控制。没有原生档位或未自定义添加档位的模型，不在聊天栏暴露思考等级选择；聊天栏只保留思考等级选择器作为当前思考状态入口，不额外显示“当前：开启”这类重复状态标签。切换模型时必须按新模型能力刷新档位；内置原生档位不得删除，用户新增的自定义档位可删除并自动回退到当前模型默认档位；自定义模型默认无思考档位，用户可在当前模型下另行添加自定义思考档位。
- OpenAI/GPT 官方 provider（供应商）可使用 Chat Completions（聊天补全）中的 `developer` role（角色）承载上下文；DeepSeek（深度求索）、本地模型和自定义 OpenAI-compatible（OpenAI 兼容）供应商必须只发送兼容的 `system`/`user` 消息，把上下文合并进 user 内容，避免供应商拒收 `developer` role。
- 长期学习总面板必须展示真实学习统计：题目完成/总数、单词掌握/总数、整体正确率、考试倒计时和 token（令牌）累计；新聊天在正式发送前只作为本地草稿，不写入数据库会话列表。
- 左侧当日学习面板的当日词汇必须按词条去重统计；截图导入词条 `skin` 和自动生成题目的 `vocabulary:skin` 属于同一个词汇，不得重复计为 2 个。
- 长期学习总面板的“当日导入 / 快速开始 / 再来几题”按钮必须按当前查看的 `dailyPanel` 判断：当前面板为空时打开右侧截图导入并提示；已有未完成题组时显示“快速开始”并继续当前题组；当前题组已完成时显示“再来几题”，点击后先询问题型、来源和数量，不得直接调用模型生成题目；不能仅因日期不是今天而显示“当日导入”。
- 普通寒暄、学习建议咨询、澄清问题、已保存设置查询和产品/设置能力反馈必须作为普通聊天处理，主会话仍必须调用当前模型并写入 `model_calls`，不得用程序硬编码回复代替模型；用户询问学习设置、每日学习时长、当前模型、已开启权限、目标、基础、当前考试、考试时间或学习计划依据时，必须优先读取已保存上下文直接回答，字段为空才反问；只有明确词表、截图词表、显式“出题 / 练习 / 刷题 / 考我”等学习动作，以及“再来点题 / 来几道题 / 再练练”这类自然补题表达，才进入正式组卷流程；“再来几题 / 再来几道题”这类未指定数量和方向的模糊加练请求必须先询问题型、来源和数量，不直接组卷；只有明确打开、修改、配置、添加、保存或导入设置的动作才进入设置流程；设置流程中无法生成具体可确认草稿时，也必须调用当前模型结合产品说明书解释设置入口和保存边界，不得返回固定模板。
- 学习设置页必须提供“每日学习时长（分钟）”和独立可见的“自定义指令”输入框；每日学习时长保存到 `daily_minutes`，用于每日计划和默认题量换算；自定义指令保存到 `global_user_prompt`，用于约束模型回复风格、讲题方式和复习建议；该指令必须进入普通聊天、分支对话和 Evaluator Tutor（判题讲解 Agent）上下文，但不得覆盖安全规则、权限边界、题目正确答案或系统功能事实。
- 启动链路必须适配中文路径、后台运行、日志落盘和 HTTP（HyperText Transfer Protocol，超文本传输协议）健康检查。
- 内置考试包含英语四级/六级（CET-4/CET-6，大学英语四级/六级）、法语四级（CFT-4，大学法语四级）、日语四级/六级（CJT4/CJT6，大学日语四级/六级）、雅思、托福、高考英语和自定义考试；同一 CET 官网考纲页必须按语种和级别匹配，不能把法语 2023 版误判为英语四/六级最新版。
- 截图词表导入后必须自动创建独立练习会话并生成完整考试式题组；词表解析需支持“单词独占一行 + 下一行释义”、`word n. 释义` 和 `word: 释义` 等常见 OCR（文字识别）/主聊天粘贴格式，并过滤手机状态栏、词书标题、底部导航等 UI（User Interface，用户界面）噪声；疑似截断英文词只有能唯一修复时才导入，缺少释义的词条必须跳过并返回诊断信息；题型应使用英文语境句、完形空格、阅读问题或同义改写，禁止退化为“选择中文释义 / 最合适理解”的词卡题。
- 主聊天栏粘贴 3 个以上截图词条时必须复用截图导入后台流程，自动创建截图练习会话、导入词表并生成题组；主聊天文本框支持拖入 TXT（纯文本格式）/Markdown（Markdown 文本格式）/PDF（Portable Document Format，便携式文档格式）/DOCX（Word 文档格式）/图片等文件并把抽取文本追加到输入框；前端等待状态需区分“截图解析中”“正在确认练题意图”和“题目生成中”。
- 主聊天栏还必须支持粘贴图片、左下角上传按钮选择文件和拖拽文件三种输入方式；具备视觉能力的当前模型可把图片作为附件发送，不具备视觉能力时统一走文件抽取链路。
- MinerU token 属于用户信息，只能写入本地 `.env` 的 `MINERU_TOKEN`；设置页需要提供官方获取地址 `https://mineru.net/apiManage/token` 和 API 文档地址 `https://mineru.net/apiManage/docs`，后端接口只能返回是否已配置和脱敏预览，禁止返回明文 token。
- 右侧“截图导入”和设置页“手动导入试卷”必须支持拖拽文件和点击“选择文件”打开本机文件管理器：截图导入选择或拖入文件后进入待解析队列，支持多张图片/多个文件继续追加；只有用户点击“解析文本”后才抽取 OCR（文字识别）/文本并填入识别文本框；截图导入解析完成后必须展示可编辑词条卡，允许修改、删除和补充单词/释义，“导入并开始练习”必须以用户确认后的词条卡内容为准，按钮放在解析结果区最底部右侧，避免用户检查词卡前误触导入；解析结果区必须在导入控件下方自然向下延伸，由截图导入面板整体滚动，不得用单词卡内部滚动或高度挤压拖拽区、文件列表、路径和识别文本区域；设置页主动加入试卷必须先点击“加入试卷”展开导入栏和详细信息，再选择/拖入试卷文件或填写文本；确认加入后上传到后端，保存到 `papers/<考试>/raw` 并生成 `papers/<考试>/parsed` 解析 JSON（JSON 数据交换格式）。
- 答题提交后必须让 Evaluator Tutor（判题讲解 Agent）结合当前会话上下文、用户背景、自定义指令和程序判定生成个性化讲解；答题时用户填写的额外提问必须作为结构化 `user_extra_prompt` 进入判题提示词，且模型讲解必须优先直接回应该额外提问，再展开常规判题讲解；模型不可用时才回退基础判题，且不得丢失作答记录；回退必须在助手正文中明确标注“模型讲解未成功 / 程序基础判题”，并在消息 payload（附加数据）和 `model_calls.validation_status` 中记录兜底来源，禁止静默伪装为正常 Agent（智能体）讲解。刚答完的题目必须作为普通聊天回顾卡片保留，显示用户选择、正确答案和对错状态；只有当前待答题使用置顶/吸附题卡；“下一题已就绪”或本轮完成进度只能由程序追加一次，模型讲解不得自行输出题号进度。
- 用户输入“总结 / 复盘 / 今日表现”等总结意图时，必须调用当前模型并写入 `model_calls` 的 `summary` 任务记录；PromptAssembler（提示词组装器）必须携带当日同考试范围的完整数据库明细，包括会话、题目、作答、用户答案、正确答案、讲解、知识标签、当日计划和最近聊天，模型需生成详细 Markdown（标记语言）复盘、错题归因和下一轮建议。只有模型不可用时才允许返回明确标注的程序兜底摘要。
- 聊天输入区需要展示当前上下文容量占用，默认上限 1,000,000 token（令牌），上下文容量上限设置放在设置页“模型”页签，令牌页只展示使用台账；支持主动压缩上下文；LLMLingua（提示词压缩库）作为可选增强，默认使用本地抽取式摘要兜底。
- 内置系统提示词必须让模型知道 Lang Drill Agent 的真实功能和权限边界：可解释截图导入、主聊天词表/文件导入、题组生成、答题讲解、分支、联网来源、拓展 Skills（拓展技能）、设置草稿和上下文压缩；主会话和分支对话都必须通过 PromptAssembler（提示词组装器）携带产品说明书、脱敏当前模型配置、用户学习目标、学习背景、考试时间、权限状态、当前已开启权限对应工具说明、拓展 Skills 状态、当前题目、必要会话上下文和用户保存的自定义指令；用户询问产品功能、使用方式、当前供应商、模型、Base URL（基础网址）、API 格式、视觉能力或思考等级时必须直接回答，只有 API Key（接口密钥）、MinerU token、cookie、数据库密码等明文敏感信息不可读取或回显；用户画像默认只作为辅助上下文调节难度、例子和建议，除非用户询问学习设置、制定计划或画像与当前错误直接相关，不得每次显式复述目标分数、考试时间、学习背景或弱项；分支对话还必须继承主会话用户画像、当前题和主会话消息上下文，有选中文本时优先围绕选中文本，无选中文本时围绕主会话上下文回答，不得脱离用户目标；不得声称“无法访问题库”而忽略程序流程；模型配置、API Key（接口密钥）、MinerU token、数据库迁移和试卷保存仍必须由用户确认。
- 主聊天和右侧分支消息必须通过安全的 Markdown（标记语言）渲染组件展示基础格式，包括加粗、内联代码、列表、标题和代码块；禁止用不可信模型内容直接写入 HTML（超文本标记语言）。
- 历年真题以 `exam_assets` 中的试卷记录和 `papers/<考试>/raw`、`papers/<考试>/parsed` 中的原始/解析资产为准，默认选择近 3 年真题；出题 Agent（智能体）必须参考当前选中的真题解析结果和已勾选题型，但不得复刻或长段引用完整真题原文。
- 当前未接入听力题和语音模型；所有考试中的听力 / Listening 题型只作为预留项展示，必须默认关闭、不可勾选，且不得进入 `enabled_question_types` 或实际组卷。
- 用户题目数据库支持自定义用户数据文件夹和迁移：模型生成给用户作答的题目、会话、作答、知识项和统计仍写入同一个 SQLite（轻量数据库）运行库；Web（网页）设置页“数据”页签是推荐迁移入口，需提供本机文件夹选择按钮辅助填写目录，并在打开数据页时刷新 `/api/data-paths`，保证题目、作答、会话和知识项计数与当前数据库一致；CLI（命令行接口）保留同等迁移和初始化能力用于维护脚本与调试。

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

- `backend/langdrill_agent/`：共享后端核心。API（接口）、服务层、Agent（智能体）、模型配置、学习算法和数据库访问都在这里；CLI（命令行接口）只作为同一后端核心的辅助维护入口。
- `backend/langdrill_agent/api.py`：FastAPI（Web API 框架）入口，负责 bootstrap（初始化加载）、chat（聊天学习）、branch（分支）、profile（用户档案）、model-config（模型配置）、MinerU 配置、exam/syllabus（考试与考纲）、phone-mirror（手机映像）、screenshot（截图导入）、文件文本抽取、数据路径选择接口、产品说明上下文和脱敏模型配置上下文。
- `backend/langdrill_agent/cli.py`：辅助命令行入口，保留 init（初始化）、serve（启动服务）、status（状态）、chat（终端聊天）、data-paths（数据路径）和 backup-user-data（备份用户数据）等既有功能，用于维护、调试和自动化兜底。
- `backend/langdrill_agent/services.py`：学习状态机、题组推进、作答写入、掌握度更新、会话生命周期、Agent 设置权限、拓展 Skills（拓展技能）状态、试卷导入草稿和业务编排。
- `backend/langdrill_agent/services.py` 中的 `PastPaperService`：历年真题试卷资产、默认近三年选择、题型开关、手动导入和重新解析；英语四/六级默认真题来源网站为 `https://www.guojiya.cn/#exams`。
- `backend/langdrill_agent/services.py` 中的 `SkillRegistryService`：发现拓展 Skills（拓展技能）并维护单个拓展 Skill 开启/关闭状态；Multi Search Engine（多搜索引擎）作为无密钥推荐技能默认启用，其它拓展 Skill 默认关闭；状态中单独返回始终开启的内置必备工具。
- `backend/langdrill_agent/web_search.py`：内置无密钥联网检索实现，普通聊天明确请求联网、搜索或最新信息时由 API（接口）注入可核验网页来源；该内置工具始终可用，实际调用受“联网功能”权限控制，不依赖拓展 Skills 开关。
- `backend/langdrill_agent/paper_assets.py`：历年真题目录、原始文件保存、PDF（Portable Document Format，便携式文档格式）/DOCX（Word 文档格式）/Markdown（Markdown 文本格式）/图片文件文本抽取、解析 JSON（JSON 数据交换格式）生成和短摘录提取；配置 `MINERU_TOKEN` 时使用 MinerU 精准解析，否则使用 MinerU 轻量解析；图片 OCR（文字识别）失败时回退 RapidOCR（本地文字识别），复杂文档依赖可选 MinerU CLI。
- `backend/langdrill_agent/learning_stats.py`：长期学习统计服务，按当前考试聚合题目完成、词汇掌握和整体正确率。
- `backend/langdrill_agent/context.py`：上下文容量、会话上下文快照、主动压缩、使用统计和 token（令牌）统计口径。
- `backend/langdrill_agent/data_paths.py`：用户数据目录、题目 SQLite（轻量数据库）路径状态、迁移、空库初始化、本机文件夹选择和 `.env` 路径账本更新。
- `backend/langdrill_agent/agents.py`：Orchestrator（调度器）、Question Author（出题 Agent）和 Evaluator Tutor（判题讲解 Agent）的实现。
- `backend/langdrill_agent/task_router.py`：用户意图识别与任务路由；设置路由只处理明确打开、修改、配置、添加、保存或导入设置的动作，读取学习设置、模型或权限状态的问题必须留在普通聊天模型路径。
- `backend/langdrill_agent/providers.py`：模型供应商配置、API Key（接口密钥）读取和模型调用适配。
- `backend/langdrill_agent/screenshot_import.py`：截图 OCR（文字识别）文本到知识项的解析与导入，支持词条换行、词性内联和冒号分隔格式。
- `backend/langdrill_agent/phone_mirror.py`：adb（安卓调试桥）/scrcpy（手机映像工具）环境检测和启动准备。
- `backend/langdrill_agent/migrations/`：SQLite（轻量数据库）schema（数据库结构）初始化脚本。
- `frontend/`：React（前端框架）+ TypeScript（类型化 JavaScript）+ Vite（前端构建工具）网页前端。
- `frontend/src/api.ts`：前端 API（接口）基础地址。默认空字符串，Web（网页）模式继续走相对 `/api` 和 Vite（前端构建工具）代理；桌面构建通过 `VITE_LANGDRILL_API_BASE=http://127.0.0.1:18080` 指向桌面本地后端。
- `frontend/public/assets/`：前端静态资源目录，当前保存深色主题背景图、浅色/深色 logo（标志）等无需打包导入的公开资产；浏览器 favicon（页签图标）使用 `frontend/public/favicon-light.png` 和 `frontend/public/favicon-dark.png`；聊天气泡使用浅蓝紫/深蓝紫专用颜色，不能把用户/助手消息退回纯白或纯黑。
- `演示web/`：独立产品展示网站，不重构或替代 `frontend/` 主应用；使用 React（前端框架）+ TypeScript（类型化 JavaScript）+ Vite（前端构建工具）+ GSAP（网页动画库）构建静态站点，视觉参考 Platform/Linear 的克制 SaaS（软件即服务）质感，包含默认跟随系统的双主题、动态单词银河、滚动组卷演示、脱敏截图画廊、GitHub/安装包入口和可探索的三栏工作台 mock（模拟）前端。该站点用于 GitHub Pages（GitHub 静态站点）等静态托管，不连接真实后端，不读取 `.env`，演示模型回复为固定模拟内容，并用虚构默认路径展示设置和拓展 Skills（拓展技能）。
- `logo/`：用户提供的浅色/深色 logo（标志）源图目录；替换品牌时应从这里重新生成 `frontend/public/assets/logo-light.png`、`frontend/public/assets/logo-dark.png`、`frontend/public/favicon-light.png`、`frontend/public/favicon-dark.png` 和 `src-tauri/icons/icon.ico`。
- `frontend/src/App.tsx`：前端主入口，负责可拖拽三栏布局、聊天、主聊天粘贴图片/拖拽文件/上传按钮导入、设置、初始化、当前题吸附显示、已答题回顾卡片、上下文容量圆环、Agent 设置权限、拓展 Skills（拓展技能）状态页和右侧工作台接入。
- `frontend/src/components/`：前端可复用组件，当前重点是 `RightWorkbench.tsx`、`ContextMenu.tsx` 和 `MarkdownText.tsx`；`RightWorkbench.tsx` 折叠和页签切换必须隐藏但不卸载内部面板状态。
- `papers/`：按考试类型分开的历年真题资产目录骨架；`raw/` 存原始试卷或粘贴文本，`parsed/` 存解析 JSON（JSON 数据交换格式），实际导入内容默认不提交。
- `scripts/dev/`：Web（网页）开发期启动与维护脚本。`start-dev.ps1` 是一键启动主逻辑，`start.bat` 只作为 Windows 双击入口。
- `scripts/desktop/`：桌面版开发、构建和运行时准备脚本。`build-desktop.ps1` 构建 NSIS（Windows 安装器）；`dev-desktop.ps1` 启动 Tauri（桌面应用框架）开发模式；`start-backend.ps1` 在用户目录准备 Python（编程语言）运行时、虚拟环境、依赖、独立 `.env`、数据库、日志和 `papers`（试卷资产目录）。
- `src-tauri/`：Tauri（桌面应用框架）Windows 桌面封装工程，负责窗口配置、资源打包、启动/停止本地后端、后端健康检查和 NSIS（Windows 安装器）产物生成；当前首版为 unsigned（未代码签名）内测包，MSI（Windows Installer，Windows 安装包）保留为后续目标。
- `doc/`：本地维护目录，保存项目地图、验收标准、人工验收清单、桌面打包说明、长版 README（项目说明文档）、脱敏截图资产和进展记录；该目录已加入 `.gitignore`，不再提交到 GitHub（代码托管平台），但本地仍按项目规则维护。
- `doc/进展记录/`：本地阶段性工作记录，包含完成内容、文件清单、错误汇报、验证结果和回退方案；记录文件不再进入 GitHub 提交。
- `try/`：自动测试、调试脚本和临时验证文件；该目录内文件必须只服务于测试/调试，可清理后不影响项目运行。
- `测试数据/`：从正式运行路径迁出的开发/联调/污染数据，按时间戳分类保存；该目录禁止提交，可清理但清理前应确认不再需要回溯。
- `archive/optimized-out/`：已从运行路径移除的旧功能归档，只作历史参考。
- `logs/`：本地运行日志，禁止提交。
- `data/`、`data_backups/`：历史项目内数据库位置和用户数据备份目录，数据库与备份禁止提交。
- 运行时不再默认从项目内 `data/langdrill_agent.db` 自动复制旧库；只有显式设置 `LANGDRILL_MIGRATE_LEGACY_DB=1` 才执行旧库迁移，避免污染新用户库。

## 核心数据流

1. 用户通过 Web（网页）三栏学习工作台发送正式学习请求；CLI（命令行接口）仅在维护、调试或自动化场景复用同一后端能力。
2. API（接口）进入服务层，服务层读取用户档案、当前考试、会话、题组和知识项。
3. Orchestrator（调度器）判断任务类型，不把用户输入拼入 system prompt（系统提示词）。
4. Question Author（出题 Agent）一次生成完整题组，Validator（校验器）通过后写入数据库；模型调用失败、超时或题组不合格时使用本地规则兜底生成完整题组并继续写库；截图词表自动练习只使用本次截图词表作为优先内容池，避免旧会话词汇污染选项。
5. 组卷阶段读取当前考试的考纲版本、已选择历年真题试卷、解析章节、短摘录和已勾选题型；提示词只携带来源、题型、解析摘要和必要短摘录，禁止把完整真题作为默认发布内容。
6. 聊天栏图片输入按当前模型 `vision` 能力分流：视觉模型走多模态模型调用；非视觉模型走 `/api/files/extract-text` 并由 MinerU/RapidOCR 提取文本后再进入普通聊天或截图词表流程；输入方式包括拖拽、粘贴和左下角上传按钮选择文件。
7. 普通聊天明确请求联网、搜索或最新信息时，API（接口）在“联网功能”权限开启下调用内置联网检索，把网页摘要和来源注入模型上下文；拓展 Skills（拓展技能）开关不参与该内置能力判断。
8. 前端以吸附题卡展示当前待答题；用户作答后写入 attempts（作答记录），更新 questions（题目状态）和 mastery（掌握度），并把上一题结构化快照写入助手消息 payload（附加数据）供回顾。
9. 简单题由程序判分，复杂题进入 Evaluator Tutor（判题讲解 Agent）。
10. 答题讲解统一由 Evaluator Tutor（判题讲解 Agent）基于程序判定、当前题、用户背景和会话上下文生成；若模型不可用，回退基础讲解但仍保存作答，并必须显式标注模型讲解未成功、记录 `answer_feedback.source='program_fallback'` 与 `model_calls.validation_status='provider_error_fallback'`；前端在讲解消息中渲染已答题回顾卡片，不把已答题继续置顶。
11. 系统自动返回下一道待答题；显式“下一题 / 继续 / 下一个”只读取当前题组库存，不重新初始化学习面板。
12. Bootstrap（初始化加载）、chat（聊天）、profile（用户档案）、session delete（会话删除）接口返回 `learning_stats`；chat/session/context 接口返回 `token_usage`，其中 chat/session/context 的上下文容量字段必须按当前会话计算，用于长期面板、设置页和上下文容量圆圈实时刷新。

## 启动与停止

Web（网页）一键启动：

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

桌面版开发启动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\desktop\dev-desktop.ps1 -SkipInstall
```

桌面版安装包构建：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\desktop\build-desktop.ps1 -SkipInstall
```

桌面版规则：
- 桌面后端固定监听 `http://127.0.0.1:18080`；端口被非 Lang Drill Agent 进程占用时必须给出清晰错误。
- 首次启动优先复用本机已有 Python 3.11+（编程语言运行时）；本机没有可用 Python 时，才在 `%LOCALAPPDATA%\Lang Drill Agent\runtime` 下载并准备 Python 3.11.9、虚拟环境和后端依赖。使用 3.11.9 是因为 Python 3.11.15（编程语言版本）官方未提供 Windows 二进制安装器。
- 桌面后端启动脚本必须强制 `PYTHONUTF8=1` 与 `PYTHONIOENCODING=utf-8`，避免 Windows（视窗系统）非 UTF-8（统一编码）重定向环境下中文 CLI（命令行接口）输出导致初始化失败。
- 桌面版真实配置和用户数据写入 `%APPDATA%\Lang Drill Agent\.env`、`data`、`logs` 和 `papers`，不写安装目录，不污染 Web（网页）开发期 `.env` 与数据库。
- 桌面窗口关闭时必须停止本次拥有的后端进程；异常时通过用户目录日志定位原因。

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
cd ..
cd 演示web
npm install
npm run dev
cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\desktop\build-desktop.ps1 -SkipInstall
```

## 测试命令

```powershell
py -m pytest try -q
py -m ruff check backend try
cd frontend
npm run build
cd ..
cd 演示web
npm run build
cd ..
cargo check --manifest-path src-tauri\Cargo.toml
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\desktop\build-desktop.ps1 -SkipInstall
py try/browser_acceptance_check.py
```

`try/browser_acceptance_check.py` 用 Playwright（浏览器自动化工具）验证设置页权限、拓展 Skills 单项开关、自定义模型增删、真题设置和截图导入状态保持；运行前需用 `LANGDRILL_DB_PATH=try\.cache\browser-acceptance\langdrill-agent.db`、`LANGDRILL_USER_DATA_DIR=try\.cache\browser-acceptance` 和 `LANGDRILL_SKILLS_ROOTS=try\.cache\browser-acceptance\skills` 启动服务，并确保 `http://127.0.0.1:8000` 与 `http://127.0.0.1:5173` 可访问。浏览器验收的临时文件统一写入 `try/.cache/`。

针对启动脚本：

```powershell
py -m pytest try/test_startup_scripts.py -q
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev\start-dev.ps1 -NoBrowser -SkipInstall
```

CI（持续集成）：

```powershell
# GitHub Actions 在 push 和 pull_request 时运行
py -m ruff check backend try
py -m pytest try -q
cd frontend
npm run build
```

## 允许修改范围

- 任务相关的 `backend/langdrill_agent/`、`frontend/src/`、`frontend/public/assets/`、`演示web/`、`scripts/`、`doc/`、`try/`。
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
- `LANGDRILL_ENV_FILE` 可指定真实 `.env` 文件路径；未设置时读取项目根目录 `.env`。桌面版必须设置到 `%APPDATA%\Lang Drill Agent\.env`，确保密钥、数据库路径和试卷资产目录与 Web（网页）开发环境隔离。
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
