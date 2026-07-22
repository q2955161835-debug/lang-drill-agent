# Agent 能力扩展实施总路线图

状态：活动计划；第 01～04 阶段已通过，正在实施第 05 阶段。全部功能验收完成后再移入归档。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有学习状态机的前提下，分阶段交付 RAG、真实真题、蒸馏与自适应调度、记忆、复杂任务、Pi 创造模式、签名更新和三语产品体验，并发布 `v1.0.0-experimental.1`。

**Architecture:** 保留现有 TaskRouter 与领域 Agent，在其下增加共享运行时服务；Pi 是按需调用的全局能力覆盖层。所有阶段通过 SQLite 正式状态、统一 Run/Trace、流式事件和权限审计连接。

**Tech Stack:** Python 3.11、FastAPI、Pydantic 2、SQLite/FTS5、React 19、TypeScript 5、Vite 7、Tauri 2、Pi Coding Agent RPC、PowerShell、GitHub Actions。

## Global Constraints

- SQLite 是学习、任务、记忆、检索和审计的唯一正式事实源。
- 创造模式关闭时，现有聊天、组卷、答题、讲解、复盘、截图导入和数据迁移必须回归通过。
- 用户明确内容和当前导入资料高于真题频率；冷门启用题型在滚动窗口内不得饥饿。
- Pi 默认无独立持久会话，不复制长期 API Key，不绕过 `ToolPolicyGateway`。
- UI 语言只改变界面；不得改变模型回复、题目或讲解语言。
- 完整真题仅保存在用户数据目录；公开仓库不提交版权状态不明的原文。
- 所有数据库、权限、桌面安装和更新改动按 L3 验收。
- 最终版本统一为 `1.0.0-experimental.1`；GitHub Release 必须标记 Pre-release，并在标题和正文标注“实验版 / Experimental”。
- `演示web2` 更新到最新能力，但继续不读取 `.env`、不连接真实后端、不显示真实路径或密钥。

---

## Plan Set

1. `01-运行时基础与模块拆分-实施计划.md`
2. `02-用户知识库与RAG-实施计划.md`
3. `03-真实真题蒸馏与自适应调度-实施计划.md`
4. `04-分层记忆-实施计划.md`
5. `05-复杂任务闭环-实施计划.md`
6. `06-Pi创造模式权限与自我扩展-实施计划.md`
7. `07-更新国际化演示与实验版发布-实施计划.md`

## Dependency Gates

```text
01 Runtime Foundation [通过：2026-07-22]
├── 02 Knowledge/RAG [通过：2026-07-22]
├── 03 Past Papers/Distillation [通过：2026-07-22]
├── 04 Memory [通过：2026-07-22]
└── 05 Agent Runs
      └── 06 Pi Creative Runtime

02 + 03 + 04 + 05 + 06
└── 07 Update/i18n/Demo/Release
```

每份计划通过自己的测试和任务验收后才进入下游。任何阶段若结论为“有条件通过”，默认不得进入依赖它的阶段。

## Specification Coverage

| 已确认需求 | 实施计划 | 主要验收证据 |
|---|---|---|
| 先补运行时、可靠性、Trace 和流式基础 | 01 | 迁移幂等、Run API/SSE、回归测试 |
| 用户学习文档知识库与 RAG | 02 | 导入、FTS/混合召回、可定位引用 |
| 真实试卷自动导入、解析 Markdown、检索和蒸馏 | 03 | 真实资产口径、题目级证据、蒸馏版本 |
| 用户资料优先且热门/冷门题型均有覆盖 | 03 | 来源配额、热门上限、冷门下限、coverage debt |
| 可开关、可配置、可审计的成熟记忆 | 04 | 四门写入、证据/历史、Provider 单主写 |
| 复杂任务计划—执行—验证—重规划—恢复 | 05 | 完成条件、工具证据、暂停/恢复/重启 |
| 创造模式全局覆盖但不改学习主流程 | 05、06 | 路由共存、普通学习全回归 |
| Pi 读写/编辑/命令行与 Codex 式权限档位 | 06 | 四档矩阵、审批绑定、硬限制测试 |
| 首装捆绑、失败禁用、一键安装修复 | 06 | 原子安装、故障展示、修复和回滚 |
| 自我扩展、自我升级、复杂编程绑定 Superpowers | 05、06 | Skill 选择、Git 检查点、测试失败回滚 |
| 中/英/日 UI 与三语 README | 07 | 词典完整性、内容语言隔离、互链测试 |
| 设置检查更新和安装更新 | 07 | Tauri 签名更新状态机与失败恢复 |
| 最新演示网页与实验性大版本发布 | 07 | 脱敏构建、Pages、Pre-release 与版本一致性 |

## Plan Self-review

- [x] 七个分计划均给出具体文件、接口、失败测试、实现步骤、验证命令和提交边界。
- [x] 正式测试统一进入受版本控制的 `tests/`；`try/` 只保留本地一次性实验。
- [x] 数据库迁移编号固定为 `002` 至 `007`，依赖顺序无冲突。
- [x] 通用网关名称统一为 `AgentRuntimeGateway`，权限入口统一为 `ToolPolicyGateway`。
- [x] 所有前端测试命令以 `npm --prefix` 执行，不依赖跨 Shell 的目录状态。
- [x] 未保留未决标记、伪代码占位步骤或无法验证的“完成”表述。
- [x] 最终发布门槛明确阻止在 L3 验收、签名更新或 P0/P1 问题未通过时发布。

## Release Gate

- [ ] 所有 7 份计划任务完成并提交。
- [ ] Backend 全量 `pytest`、Ruff、Frontend build/test、Tauri build、桌面 VM 安装验收通过。
- [ ] L3 跨模块人工验收通过；无未解决 P0/P1 安全或数据问题。
- [ ] 版本号在 `pyproject.toml`、`frontend/package.json`、`src-tauri/Cargo.toml`、`src-tauri/tauri.conf.json`、README 和演示站一致。
- [ ] `演示web2` 构建通过并经脱敏检查。
- [ ] GitHub Actions 生成带 Tauri Updater 签名的 NSIS 产物与 `latest.json`。
- [ ] 创建 `v1.0.0-experimental.1` Git tag 和 GitHub Pre-release。
- [ ] Release notes 明确实验能力、已知限制、备份建议、创造模式风险与回退方式。
- [ ] Pages workflow 成功发布最新版演示站。
