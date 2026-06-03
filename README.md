# Lang Drill Agent

把 `语言学习-lang-drill-skill` 制作为可运行语言学习 agent，支持 CLI（Command Line Interface，命令行接口）和 Web（网页）前端。系统采用“前端展示层 + 后端状态机 + 动态提示词组装 + 多 Agent 协作”的架构。

## 当前实现

- 三 Agent：Orchestrator（调度器）、Question Author（出题 agent）、Evaluator Tutor（判题讲解 agent）。
- 共享后端核心：CLI 和 Web 共用 `backend/langdrill_agent`。
- Prompt Engine（提示词引擎）：按任务动态选择 prompt_modules（提示词模块），用户输入只进入 user_content。
- SQLite（轻量数据库）：学习状态、题目、作答、分支、考纲来源、模型调用和 token（令牌）统计都入库。
- Web 前端：左侧当日面板和日期会话、中央聊天和题目吸附、右侧分支对话、初始化与设置面板。
- 复习算法：内置 `mastery_score V1`，预留 FSRS（Free Spaced Repetition Scheduler，免费间隔重复调度器）接入点。

## 安装

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
cd frontend
npm install
```

## 启动

后端：

```powershell
.\.venv\Scripts\Activate.ps1
py -m langdrill_agent.cli init --display-name boss --target-language 日语 --exam-id cjt4 --exam-name 大学日语四级
py -m langdrill_agent.cli serve --reload
```

前端：

```powershell
cd frontend
npm run dev
```

默认访问 `http://127.0.0.1:5173`。

## CLI 常用命令

```powershell
py -m langdrill_agent.cli status
py -m langdrill_agent.cli chat "今天学习まで、から和に的区别"
py -m langdrill_agent.cli import-skill --source "D:\1Folder\语言学习-lang-drill\语言学习-lang-drill-skill"
```

## 模型供应商

`.env.example` 只保存占位变量。真实 key（密钥）写入 `.env`，不要提交。

支持模式：

- `mock`：本地模拟，无需 key（密钥）。
- `openai`：OpenAI-compatible（OpenAI 兼容）接口。
- `local`：本地 OpenAI-compatible（OpenAI 兼容）模型服务。
- DeepSeek（深度求索）、Qwen（通义千问）、Zhipu AI（智谱）、Moonshot（月之暗面）可按 OpenAI-compatible（OpenAI 兼容）方式配置。

网页设置中的模型配置会写入本地 `.env`：

- `LANGDRILL_DEFAULT_PROVIDER`：当前供应商。
- `LANGDRILL_DEFAULT_MODEL`：当前模型名称。
- `LANGDRILL_PROVIDER_BASE_URL`：当前 Base URL（基础网址）。
- `LANGDRILL_PROVIDER_API_KEY`：当前 API Key（接口密钥）。

模型名称在网页里同时提供供应商常见模型选项和自定义填写项。自定义模型不为空时优先使用自定义值，方便供应商新增模型后立即使用。

## 资料边界

真题和考纲以来源、年份、可信等级和版权边界入库。来源不明或版权不清的完整真题不作为默认发布资产，只做索引与风格参考。

## License（许可证）

本项目为 source-available（源码可见）项目。非商业用途按 PolyForm Noncommercial License 1.0.0（PolyForm 非商业许可证 1.0.0）授权；商业用途需要单独取得书面商业许可。详见 `LICENSE` 和 `COMMERCIAL.md`。
