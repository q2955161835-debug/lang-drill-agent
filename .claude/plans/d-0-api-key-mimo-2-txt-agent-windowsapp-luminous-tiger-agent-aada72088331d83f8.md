# 语言学习 Agent 项目架构探索报告

## 任务概述
探索 Lang Drill Agent（语言学习训练 Agent）项目的整体架构，包括技术栈、文件结构、配置文件、依赖工具、API 集成方式，并评估架构优缺点。

---

## 1. 项目定位与核心概念

Lang Drill Agent 是一个面向**长期语言学习、刷题训练、错题复盘和考试备考**的多 Agent 系统，重点支持：
- 英语四级/六级（CET-4/CET-6）
- 日语四级/六级（CJT4/CJT6）

**核心设计理念**：
- "前端展示层 + 后端状态机 + 动态提示词组装 + 多 Agent 协作"
- **数据库是唯一正式学习状态来源**，聊天上下文仅作交互记录
- 可追踪、可验证、可扩展

---

## 2. 技术栈

### 2.1 后端技术栈
| 技术 | 用途 |
|------|------|
| **Python 3.11+** | 核心语言 |
| **FastAPI** | Web API 框架 |
| **Typer** | CLI 框架 |
| **Pydantic** | 数据校验和模型定义 |
| **SQLite** | 轻量级关系数据库 |
| **python-dotenv** | 环境变量管理 |
| **httpx** | HTTP 客户端（用于调用模型 API） |

**构建工具**：
- `setuptools` + `wheel`：Python 包构建
- `pytest`：测试框架
- `ruff`：代码检查与格式化

### 2.2 前端技术栈
| 技术 | 版本 | 用途 |
|------|------|------|
| **React** | 19.1.0 | UI 框架 |
| **TypeScript** | 5.8.3 | 类型化开发 |
| **Vite** | 7.0.0 | 构建工具与开发服务器 |
| **GSAP** | 3.13.0 | 动画库（卡通果冻弹跳效果） |
| **@phosphor-icons/react** | 2.1.10 | 图标库 |

**前端特色**：
- 单页应用（SPA）
- 三栏布局（左侧学习面板、中间聊天区、右侧分支对话）
- GSAP 动画增强交互体验（果冻弹跳、卡通效果）

---

## 3. 项目文件结构

```
语言学习-lang-drill-agent/
├── backend/
│   └── langdrill_agent/        # 后端核心模块
│       ├── __init__.py
│       ├── agents.py           # 三个 Agent 实现
│       ├── algorithm.py        # mastery_score 算法
│       ├── api.py              # FastAPI 路由与接口
│       ├── cli.py              # Typer CLI 命令
│       ├── config.py           # 配置加载
│       ├── db.py               # 数据库初始化与事务管理
│       ├── migrations/         # 数据库 schema
│       │   └── 001_initial.sql
│       ├── models.py           # Pydantic 数据模型
│       ├── prompt_engine.py    # 提示词注册表与组装引擎
│       ├── providers.py        # 模型供应商抽象层（支持 Mock、OpenAI-compatible）
│       ├── services.py         # 业务服务层（Profile、Session、Question、ModelConfig）
│       ├── task_router.py      # 任务意图识别路由
│       ├── utils.py            # 工具函数（ID 生成、JSON 处理）
│       └── validator.py        # 题目结构校验
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # 主应用组件（5000+ 行）
│   │   ├── main.tsx            # 入口文件
│   │   └── styles.css          # 全局样式
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── data/                       # SQLite 数据库文件存放目录
├── doc/                        # 架构说明与进展记录
├── try/                        # 测试与调试文件
├── logs/                       # 运行日志
├── .env                        # 环境变量（密钥，不提交）
├── .env.example                # 环境变量示例
├── pyproject.toml              # Python 项目配置
├── README.md                   # 项目说明文档
├── AGENTS.md                   # Agent 架构说明
├── start.bat / stop.bat        # Windows 启动/停止脚本
└── LICENSE / COMMERCIAL.md     # 许可证（PolyForm 非商业）
```

---

## 4. 核心配置文件

### 4.1 后端配置（`pyproject.toml`）
```toml
[project]
name = "langdrill-agent"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "typer>=0.12.0",
  "pydantic>=2.7.0",
  "python-dotenv>=1.0.0",
  "httpx>=0.27.0"
]

[project.scripts]
langdrill = "langdrill_agent.cli:app"

[tool.setuptools]
package-dir = {"" = "backend"}
```

### 4.2 环境变量（`.env.example`）
```bash
LANGDRILL_DB_PATH=./data/langdrill_agent.db
LANGDRILL_USER_NAME=boss
LANGDRILL_DEFAULT_PROVIDER=mock
LANGDRILL_DEFAULT_MODEL=mock-tutor-v1
LANGDRILL_PROVIDER_BASE_URL=https://api.example.com/v1
LANGDRILL_PROVIDER_API_KEY=provider-key-placeholder

# 支持 OpenAI-compatible 接口
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1

# 本地模型支持
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
```

### 4.3 前端配置（`package.json`）
- **dev**: `vite --host 127.0.0.1`
- **build**: `tsc -b && vite build`
- 无 ESLint/Prettier 配置，依赖 Vite 默认行为

---

## 5. 数据库架构（SQLite）

### 核心表结构
1. **user_profiles**：用户配置（称呼、目标语言、考试、学习背景、人格设置）
2. **study_sessions**：学习会话（按日期分组、daily_plan_json）
3. **messages**：聊天消息（user/assistant）
4. **questions**：题目（类型、选项、答案、讲解、knowledge_tags）
5. **attempts**：作答记录（正确性、反馈、掌握度变化）
6. **knowledge_items**：知识点（term、mastery_score、due_at）
7. **mastery_events**：掌握度变化事件
8. **branch_conversations / branch_messages**：分支对话
9. **model_calls**：模型调用审计（token 用量、耗时、校验状态）
10. **app_settings**：应用级设置（模型配置、自定义提供商）
11. **syllabus_sources**：考纲来源（官方链接、可信等级）

---

## 6. 三 Agent 架构

### Agent 1：Orchestrator（调度器）
- **职责**：识别用户意图、选择任务流程、读取学习状态、动态组装提示词模块
- **核心方法**：`handle_daily_drill()`
- **不直接**：生成题目、修改答案、跳过校验

### Agent 2：Question Author（出题 Agent）
- **职责**：根据当日学习内容、复习内容、考纲规则、真题风格生成结构化题目
- **核心方法**：`ensure_first_question()`
- **输出**：符合 `Question` JSON Schema 的题目
- **质量保证**：通过 `QuestionValidator` 校验，失败时使用 fallback 题目

### Agent 3：Evaluator Tutor（判题讲解 Agent）
- **职责**：复杂题型判分、错误诊断、讲解生成、错题归因、当日总结
- **核心方法**：`evaluate()`
- **简化逻辑**：简单选择题由程序直接判定，避免无意义 token 消耗

**协作方式**：
- Orchestrator 识别任务类型（`task_router.py`）
- Question Author 生成题目后入库
- Evaluator Tutor 负责判题与反馈
- 所有 Agent 共享同一数据库连接（`transaction()` 上下文管理器）

---

## 7. 模型 API 集成方式

### 7.1 提供商抽象层（`providers.py`）
**`ModelProvider` 类**：
- 支持 `mock` 模式（本地模拟，无需密钥）
- 支持 `openai-compatible` 模式（统一接口）

**请求格式**：
```python
payload = {
    "model": self.model,
    "messages": [
        {"role": "system", "content": system},
        {"role": "developer", "content": dumps({"context_pack": pack.context_pack})},
        {"role": "user", "content": pack.user_content}
    ]
}
# 结构化输出时添加：
if pack.output_schema:
    payload["response_format"] = {"type": "json_object"}
```

### 7.2 支持的供应商（15+ 个）
| 供应商 | Base URL | 示例模型 |
|--------|----------|----------|
| **OpenAI** | `https://api.openai.com/v1` | gpt-5.5, gpt-4o |
| **DeepSeek** | `https://api.deepseek.com` | deepseek-v4-pro, deepseek-reasoner |
| **Qwen（通义千问）** | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen3-max |
| **Zhipu AI** | `https://open.bigmodel.cn/api/paas/v4` | glm-4.5 |
| **Moonshot（Kimi）** | `https://api.moonshot.cn/v1` | kimi-k2-turbo-preview |
| **Xiaomi MiMo** | `https://api.xiaomimimo.com/v1` | mimo-v2.5-pro |
| **本地模型** | `http://localhost:11434/v1` | qwen2.5:7b, deepseek-r1:8b |
| **自定义** | 用户填写 | 用户填写 |

### 7.3 动态提示词组装（`prompt_engine.py`）
**`PromptRegistry`**：维护提示词模块（id、version、scope、task_type、exam_id、priority、token_budget、dependencies、content、enabled）

**`PromptAssembler`**：按任务类型组装提示词包（`PromptPack`）：
- `system_modules`：核心规则 + 任务规则 + 考试规则 + 人格设置
- `context_pack`：当前用户目标、会话状态、题目、考纲片段、错误摘要
- `user_content`：用户实际输入
- `output_schema`：结构化输出约束

---

## 8. API 接口设计（`api.py`）

### 8.1 核心端点
| 路由 | 方法 | 功能 |
|------|------|------|
| `/api/bootstrap` | GET | 初始化加载（profile、sessions、token_usage、providers、model_config） |
| `/api/initialize` | POST | 首次设置（模型、学习目标、考试） |
| `/api/chat` | POST | 发送消息（识别任务、出题、判题、讲解） |
| `/api/branch` | POST | 创建分支对话 |
| `/api/sessions` | GET | 获取所有会话列表 |
| `/api/sessions/{id}` | GET | 加载历史会话详情 |
| `/api/profile` | POST | 更新用户设置 |
| `/api/model-config` | POST | 保存模型配置 |
| `/api/config/providers/custom` | POST | 添加自定义提供商 |
| `/api/settings/defaults` | POST | 恢复默认设置 |

### 8.2 请求/响应示例

**发送消息**（`/api/chat`）：
```json
{
  "content": "今天学习まで、から和に的区别",
  "session_id": "ses_abc123",
  "selected_text": ""
}
```

**响应**：
```json
{
  "session_id": "ses_abc123",
  "message": {
    "id": "msg_xyz",
    "role": "assistant",
    "content": "已初始化今日学习面板，并准备好第一题。"
  },
  "daily_panel": {
    "date": "2026-06-26",
    "title": "今天学习まで、から和に的区别",
    "status": "active",
    "plan": { "new_content": [...], "review_content": [...] },
    "questions_total": 5,
    "questions_done": 0,
    "accuracy": 0
  },
  "active_question": {
    "id": "q_123",
    "prompt": "选择最符合语境的助词...",
    "options": ["A. まで", "B. から", "C. に"],
    ...
  },
  "token_usage": { "input": 1234, "output": 567, "total": 1801 }
}
```

---

## 9. CLI 命令（`cli.py`）

```bash
# 初始化
py -m langdrill_agent.cli init --display-name boss --target-language 日语 --exam-id cjt4

# 查看状态
py -m langdrill_agent.cli status

# 聊天模式
py -m langdrill_agent.cli chat "今天学习..."

# 启动 Web 服务
py -m langdrill_agent.cli serve --reload

# 导入 skill 资产
py -m langdrill_agent.cli import-skill --source "D:\path\to\skill"
```

---

## 10. 前端架构（App.tsx）

### 10.1 状态管理
使用 React Hooks（`useState`）管理：
- `profile`：用户配置
- `sessions`：会话列表
- `messages`：当前会话消息
- `dailyPanel`：当日学习面板
- `activeQuestion`：当前题目
- `modelConfig`：模型配置
- `providers`：可用供应商列表
- `tokenUsage`：token 统计

### 10.2 三栏布局
1. **左侧栏**：
   - 当日学习面板（日期、题量、准确率）
   - 按日期分组的会话列表
   - 可折叠（localStorage 持久化状态）
   - 底部设置按钮

2. **中间主区**：
   - 空白上下文时显示长期学习总面板
   - 题目吸附显示区（`QuestionDock`）
   - 消息流（`MessageItem`）
   - 选中文本后显示分支对话 FAB
   - 底部输入框（支持 Shift+Enter 换行）

3. **右侧栏**：
   - 分支对话界面
   - 默认折叠，选中文本后可开启
   - 不写回主会话（可选择合并）

### 10.3 动画效果（GSAP）
- 消息卡片：果冻弹跳（`elastic.out`）
- 按钮：悬停放大旋转、点击缩放
- 面板：入场动画（`stagger` 交错）

---

## 11. 架构优缺点评估

### ✅ 优点

#### 11.1 清晰的职责分离
- **Agent 层**：三个 Agent 各司其职，避免单体巨型 prompt
- **服务层**：`ProfileService`、`SessionService`、`QuestionService`、`ModelConfigService` 封装业务逻辑
- **数据层**：SQLite 作为唯一事实来源，聊天上下文不作为权威记忆

#### 11.2 可追踪与审计
- `model_calls` 表记录每次模型调用的 token 用量、耗时、提示词模块、校验状态
- 所有题目通过 `QuestionValidator` 校验后才能入库
- 掌握度变化记录在 `mastery_events` 表

#### 11.3 灵活的模型供应商支持
- 统一 OpenAI-compatible 接口，支持 15+ 国内外供应商
- Mock 模式方便本地开发调试
- 用户可添加自定义提供商和模型

#### 11.4 动态提示词组装
- 提示词模块化管理（`PromptRegistry`）
- 按任务类型、考试类型、用户人格动态组装
- 避免注入完整历史上下文，减少 token 浪费

#### 11.5 前后端共享业务逻辑
- CLI 和 Web 共用同一套后端内核（`langdrill_agent`）
- 避免维护两套业务逻辑

#### 11.6 渐进增强的用户体验
- 题目吸附显示（滚动时保持可见）
- 分支对话（不污染主会话）
- GSAP 动画增强交互（不影响功能）

---

### ❌ 缺点与改进空间

#### 11.1 前端架构单体化
**问题**：
- `App.tsx` 超过 1000 行，包含多个子组件和复杂状态管理
- 未使用状态管理库（Redux、Zustand、Jotai）
- 设置对话框、初始化对话框、主应用逻辑耦合在同一文件

**建议**：
- 拆分为独立组件（`components/`）
- 引入轻量状态管理（Zustand 或 Context API）
- 将 API 调用抽象为 `services/api.ts`

#### 11.2 错误处理不够细致
**问题**：
- API 错误时仅显示简单错误消息
- 缺少重试机制
- 模型 API 失败时回退到 fallback 题目，但用户可能不知道

**建议**：
- 引入 `react-query` 或 `swr` 进行数据获取与缓存
- 增加错误边界（Error Boundary）
- 提供更详细的错误提示（区分网络错误、API 密钥无效、模型不可用）

#### 11.3 提示词模块未持久化到数据库
**问题**：
- `prompt_engine.py` 中的提示词模块硬编码在代码中
- 缺少 `PromptRegistry` 的数据库表结构
- 无法通过管理界面动态调整提示词

**建议**：
- 迁移 001 中增加 `prompt_modules` 表
- 提供提示词管理界面（Web 或 CLI）
- 支持 A/B 测试不同提示词版本

#### 11.4 缺少完整的测试覆盖
**问题**：
- `try/` 目录包含测试文件，但未集成到 CI
- 缺少前端单元测试（Vitest、React Testing Library）
- Agent 逻辑未覆盖边缘情况（如模型返回格式错误）

**建议**：
- 增加 pytest 测试用例覆盖核心业务逻辑
- 前端增加 Vitest + Testing Library
- Mock 模型响应进行端到端测试

#### 11.5 学习算法实现不完整
**问题**：
- `mastery_score V1` 仅基于简单公式
- FSRS 仅预留接入点，未实现
- 缺少间隔复习调度逻辑

**建议**：
- 实现 FSRS 算法（开源库：`py-fsrs`）
- 增加复习队列优先级调度
- 提供复习强度可视化

#### 11.6 分支对话功能未完善
**问题**：
- 分支对话仅创建记录，未实现完整对话流
- 无法合并分支到主会话
- 缺少分支历史管理

**建议**：
- 实现分支对话的完整交互循环
- 支持分支合并为主会话注释或复习卡片
- 左侧栏显示分支列表

#### 11.7 安全性与隐私
**问题**：
- API Key 存储在 `.env` 明文文件
- 缺少用户数据加密
- Web 界面无认证机制（仅本地使用）

**建议**：
- 使用系统密钥链存储敏感信息（`keyring` 库）
- 数据库敏感字段加密（如学习背景）
- 如需远程访问，增加 JWT 认证

#### 11.8 国际化（i18n）缺失
**问题**：
- 前端界面硬编码中文
- 后端日志、错误消息中英混杂
- 不支持多语言界面

**建议**：
- 前端引入 `react-i18next`
- 后端使用 `gettext` 或 `babel`
- 提供中英文双语支持

---

## 12. 技术债务与待办事项

### 高优先级
1. **实现提示词模块数据库持久化**
2. **完善 Question Author 的模型输出解析**（当前 fallback 比例较高）
3. **增加前端错误边界与重试机制**

### 中优先级
4. **拆分前端 App.tsx 为模块化组件**
5. **实现 FSRS 复习算法**
6. **完善分支对话功能**
7. **增加单元测试与集成测试**

### 低优先级
8. **国际化支持**
9. **密钥安全存储**
10. **性能优化（数据库索引、前端虚拟滚动）**

---

## 13. 总结

### 13.1 核心亮点
- **三 Agent 架构清晰**，职责分离良好
- **模型供应商灵活**，支持国内外 15+ 供应商
- **动态提示词组装**，按需注入上下文
- **数据库为事实来源**，可追踪、可审计
- **前后端共享逻辑**，CLI 与 Web 一致

### 13.2 主要挑战
- **前端架构需重构**：单体组件过大，缺少状态管理
- **提示词管理未持久化**：硬编码在代码中，难以动态调整
- **学习算法实现不完整**：FSRS 仅预留接口
- **测试覆盖不足**：缺少自动化测试与 CI/CD

### 13.3 推荐改进路径
1. 短期（1-2 周）：拆分前端组件 + 增加错误处理
2. 中期（1 个月）：提示词模块持久化 + FSRS 算法实现
3. 长期（3 个月）：完善测试覆盖 + 国际化 + 性能优化

---

## 附录：关键文件路径

### 后端核心
- `backend/langdrill_agent/api.py` - FastAPI 路由
- `backend/langdrill_agent/agents.py` - 三 Agent 实现
- `backend/langdrill_agent/providers.py` - 模型供应商抽象
- `backend/langdrill_agent/services.py` - 业务服务层
- `backend/langdrill_agent/prompt_engine.py` - 提示词组装

### 前端核心
- `frontend/src/App.tsx` - 主应用组件
- `frontend/src/styles.css` - 全局样式

### 配置
- `pyproject.toml` - Python 项目配置
- `.env.example` - 环境变量示例
- `frontend/package.json` - 前端依赖

### 文档
- `README.md` - 项目说明
- `AGENTS.md` - Agent 架构说明
