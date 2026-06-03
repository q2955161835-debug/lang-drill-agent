# Lang Drill Agent 项目规则

## 项目目标

本项目把 `D:\1Folder\语言学习-lang-drill\语言学习-lang-drill-skill` 的语言刷题 skill 制作为可运行 agent，提供共享后端内核、CLI（Command Line Interface，命令行接口）和 Web（网页）前端。

## 核心约束

- 数据库是唯一正式学习状态来源。
- CLI 与 Web 共享 `backend/langdrill_agent` 后端核心。
- 用户输入只进入 `user_content`，不得拼入 system prompt（系统提示词）。
- `.env` 是真实环境变量账本，必须留在 `.gitignore` 中；`.env.example` 只放占位值。
- 测试、调试和临时文件放入 `try/`。

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
