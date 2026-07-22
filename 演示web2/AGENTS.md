# AGENTS.md — 演示web2 产品展示站

本目录是 lang-drill-agent 的第二版独立产品展示网站，与 `../演示web/` 并存、不同风格。父项目 AGENTS.md 位于 `../AGENTS.md`（工作区外，只读引用），GitHub 仓库 `https://github.com/q2955161835-debug/lang-drill-agent`（Public，公开）。

## 项目目标

把 lang-drill-agent 产品包装为面向 GitHub Pages 的静态展示站：动态单词银河、滚动组卷工作流演示、脱敏截图画廊、1:1 还原主应用前端 mock、GitHub/安装包入口。核心痛点包装：背词与刷题分离 → 导入即练习闭环。不连接真实后端，不读取 `.env`，不暴露真实主机路径。

## 文件夹结构与职责

```
演示web2/
├── index.html              # landing 落地页入口（前置主题脚本读取 langdrill-site2-theme）
├── app.html                # mock 演示前端入口（前置主题脚本读取 themeMode，与 frontend 一致）
├── vite.config.ts          # Vite 多入口配置，base 默认 /lang-drill-agent/，VITE_BASE_PATH 可覆盖
├── package.json            # name=langdrill-agent-product-site-2，dev 端口 4273
├── tsconfig.json           # 标准 React + Vite 配置
├── tsconfig.node.json      # Node 类型声明（含 @types/node）
├── .gitignore              # 忽略 node_modules/dist
├── public/
│   ├── favicon-light.png   # 浅色主题页签图标（来自 frontend/public）
│   ├── favicon-dark.png    # 深色主题页签图标
│   └── assets/
│       ├── logo-light.png           # 浅色 logo
│       ├── logo-dark.png            # 深色 logo
│       ├── dark-theme-bg.jpg        # 深色主题背景图
│       ├── hero-bg-texture.jpg      # 生成的英雄区质感纹理图（text_to_image API）
│       └── screenshots/             # 脱敏截图（light-/dark- 前缀，12 张 × 2 主题）
└── src/
    ├── main.tsx            # landing 入口，hash 路由 #/app 切换到 MockFrame（iframe 隔离）
    ├── App.tsx             # landing 主组件（约 800 行）：Header/Hero/Workflow/PainPoint/Features/Showcase/DemoCTA/Install/Footer/CursorGlow
    ├── styles.css          # Framer 深色光晕风样式（约 1100 行）：CSS 变量双主题、aurora、word-galaxy、workflow、feature-card glow、cursor-glow、reveal
    ├── app-main.tsx        # mock 入口，导入 ./mock/App 和 ./mock/styles.css
    └── mock/               # frontend/src/ 的整包复制，仅替换 api.ts 为本地 mock
        ├── App.tsx         # 1:1 还原主应用前端（约 5000 行，不修改）
        ├── api.ts          # 替换为本地 mock：所有端点返回固定数据
        ├── fileImport.ts   # frontend 原文件
        ├── types.ts        # frontend 原文件
        ├── styles.css      # frontend 原样式
        ├── vite-env.d.ts   # Vite 类型声明
        └── components/
            ├── ContextMenu.tsx
            ├── MarkdownText.tsx
            └── RightWorkbench.tsx
```

## 关键依赖

- React 19 + react-dom
- TypeScript 5.x
- Vite 7.x
- gsap + @gsap/react（useGSAP）+ gsap/ScrollTrigger
- @phosphor-icons/react
- @types/node（dev，vite.config.ts 需要）

## 数据流

1. Landing（`index.html`）加载 `src/main.tsx` → 渲染 `src/App.tsx`
2. 用户点击"进入演示前端"或访问 `#/app` → `MockFrame` 渲染 iframe，src 指向 `${BASE_URL}app.html`
3. Mock（`app.html`）加载 `src/app-main.tsx` → 导入 `src/mock/App.tsx`（1:1 还原 frontend）
4. Mock App 调用 `src/mock/api.ts` 中的函数 → 返回固定演示数据（220ms 模拟延迟）
5. `/api/chat` 永远返回固定 ASSISTANT_INTRO（自我介绍 + 网页版开发中提示）
6. `/api/skills` 返回 skill1（已启用）+ skill2（待启用），路径虚构为 `~/LangDrill/skills/...`
7. `/api/screenshot/parse` 返回 5 个演示词条（achieve/challenge/appropriate/efficient/sustainable）

## 运行与部署

```bash
# 安装
npm install

# 本地开发（默认 base=/lang-drill-agent/，访问 http://127.0.0.1:4273/lang-drill-agent/）
npm run dev

# 本地预览 production build（无 base 前缀）
$env:VITE_BASE_PATH="./"; npm run dev

# 构建（输出到 dist/，base=/lang-drill-agent/）
npm run build

# 预览 production build
npm run preview
```

GitHub Pages 部署：推送到 `main` 后由 `../.github/workflows/pages-demo-web2.yml` 执行 `npm ci` 和 `npm run build`，上传 `演示web2/dist/` 到 GitHub Pages（GitHub 静态站点），URL 为 `https://q2955161835-debug.github.io/lang-drill-agent/`。仓库 Pages 设置需使用 GitHub Actions（GitHub 自动化）作为发布源。

## 执行规则

- **读取顺序**：先读本 AGENTS.md → 再读 `src/App.tsx`（landing）和 `src/mock/api.ts`（mock 数据）
- **允许修改范围**：`src/App.tsx`、`src/styles.css`、`src/main.tsx`、`src/app-main.tsx`、`index.html`、`app.html`、`vite.config.ts`、`tsconfig*.json`、`package.json`、`public/`
- **禁止修改范围**：`src/mock/` 目录下除 `api.ts` 外的所有文件（必须与 `frontend/src/` 保持 1:1 一致）
- **mock api.ts 修改原则**：只允许调整返回的演示数据内容，不允许引入真实 API 调用、真实文件读取或真实网络请求
- **测试命令**：`npm run build`（TypeScript 编译 + Vite 打包，必须零错通过）
- **验收标准**：landing 双主题切换正常、单词银河动画流畅、滚动工作流演示完整、`#/app` mock iframe 加载且 1:1 还原、模型回复为固定自我介绍、skill 显示 skill1/skill2 占位
- **安全约束**：不暴露真实主机路径、不读取 `.env`、不连接真实后端、不提交敏感信息

## 工作区外常用文件地址

- 父项目 AGENTS.md：`../AGENTS.md`（只读引用）
- frontend 主应用源码：`../frontend/src/`（mock 复制来源）
- 脱敏截图原始目录：`../测试数据/演示数据库/产品网站演示-20260703/product-screenshots/`
- GitHub 仓库：`https://github.com/q2955161835-debug/lang-drill-agent`（Public，公开）
