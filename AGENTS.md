# Lang Drill Agent 项目规则

## 项目目标

本项目把 `D:\1Folder\语言学习-lang-drill\语言学习-lang-drill-skill` 的语言刷题 skill（技能）制作为可运行 agent（智能体），提供共享后端内核、CLI（Command Line Interface，命令行接口）和 Web（网页）前端。

## GitHub（代码托管）

- 仓库地址：`https://github.com/q2955161835-debug/lang-drill-agent.git`
- 仓库状态：Private（私有）

## 核心约束

- 数据库是唯一正式学习状态来源。
- CLI（Command Line Interface，命令行接口）与 Web（网页）共享 `backend/langdrill_agent` 后端核心。
- 用户输入只进入 `user_content`，不得拼入 system prompt（系统提示词）。
- `.env` 是真实环境变量账本，必须留在 `.gitignore` 中；`.env.example` 只放占位值。
- 测试、调试和临时文件放入 `try/`。
- 正式刷题流程必须先生成完整题组并写入数据库，再逐题展示给用户。
- 答题后必须立即写入 attempt（作答记录）、更新 mastery（掌握度）并自动返回下一道待答题；不得要求用户额外输入“下一题”才推进。
- 用户显式输入“下一题 / 继续 / 下一个”时，只读取当前题组的下一道库存题，不得重新初始化今日学习面板。

## 目录结构与职责

- `backend/langdrill_agent/`：共享后端内核、API（接口）、CLI（命令行接口）、服务层、Agent（智能体）和学习状态机。
- `backend/langdrill_agent/migrations/`：SQLite（轻量数据库）schema（数据库结构）初始化脚本。
- `frontend/src/`：React（前端框架）+ TypeScript（类型化 JavaScript）网页前端。
- `frontend/src/components/`：右侧工作台等可复用 UI（用户界面）组件。
- `archive/optimized-out/`：已从运行路径移除的旧功能归档。
- `doc/`：项目地图、验收标准、进展记录和说明文档。
- `doc/进展记录/`：按日期记录阶段性工作、错误汇报、验证结果和回退方案。
- `try/`：测试、调试和冒烟脚本；仅存可删除的验证文件。

## 核心入口

- 后端 API（接口）：`backend/langdrill_agent/api.py`
- 后端服务层：`backend/langdrill_agent/services.py`
- Agent（智能体）实现：`backend/langdrill_agent/agents.py`
- 任务路由：`backend/langdrill_agent/task_router.py`
- 前端主入口：`frontend/src/App.tsx`
- 一键启动：`start.bat`
- 一键停止：`stop.bat`

## 常用命令

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
py -m langdrill_agent.cli init
py -m langdrill_agent.cli serve --reload
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

## 验收标准

- 刷题验收以 `doc/验收标准.md` 为准。
- 用户体验回归清单以 `doc/manual-acceptance-checklist.md` 为准。
- 每次阶段性任务完成后，同步更新相关验收项和 `doc/进展记录/YYYY-M-D.md`。

## 安全与数据边界

- 不提交 `.env`、真实 API key（接口密钥）、数据库、日志或用户私有学习数据。
- 真题和考纲只保存来源、年份、可信等级和版权边界；不默认发布来源不明的完整真题内容。
- 旧 skill（技能）项目只能作为流程参考，不能把旧项目私有题目或完整真题原文直接搬入本 agent（智能体）。
