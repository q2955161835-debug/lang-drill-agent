# 本机桌面编译产物 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本机生成当前 `v1.0.2` Windows x64 NSIS 安装包，将其保存到项目根目录，并把后续版本发布时的本机构建替换要求固化到项目规则。

**Architecture:** 继续复用 `scripts/desktop/build-desktop.ps1` 作为唯一桌面 release 构建入口，不增加启动器或第二套构建逻辑。根目录仅保存经过版本与哈希验证的当前 NSIS 单文件安装包；裸 release EXE 继续留在 Tauri 构建目录，与所需资源目录保持相邻。

**Tech Stack:** PowerShell、Tauri 2、Rust/Cargo、React/Vite、NSIS、Git

## Global Constraints

- 当前项目版本必须为 `1.0.2`。
- 根目录产物名称必须为 `Lang Drill Agent_1.0.2_x64-setup.exe`。
- 根目录只保留一个当前版本的 `Lang Drill Agent_*_x64-setup.exe`。
- 旧产物只能在新产物构建、版本校验、复制和 SHA256 校验全部通过后删除。
- 根目录安装包必须由 Git 忽略，不得提交。
- 不增加自动构建启动器，不把裸 release EXE 单独复制到根目录，不安装或卸载桌面应用。
- 保留用户已有的未跟踪 `.superpowers/` 内容，不修改、不删除。

---

### Task 1: 固化本机发布产物规则

**Files:**
- Modify: `.gitignore`
- Modify: `AGENTS.md:162-175`

**Interfaces:**
- Consumes: 现有 `scripts/desktop/build-desktop.ps1` 桌面构建入口。
- Produces: 根目录安装包 Git 忽略规则和后续版本发布约束。

- [ ] **Step 1: 运行忽略规则的失败检查**

Run:

```powershell
git check-ignore -v -- "Lang Drill Agent_1.0.2_x64-setup.exe"
```

Expected: 退出码为 `1`，没有匹配规则。

- [ ] **Step 2: 添加最小规则修改**

在 `.gitignore` 增加：

```gitignore
/Lang Drill Agent_*_x64-setup.exe
```

在 `AGENTS.md` 的“桌面版规则”增加：

```markdown
- 每次发布新版本时，必须在本机执行桌面 release 构建；构建和版本验证通过后，将最新 NSIS 安装包复制到项目根目录并替换根目录旧版本。根目录只保留当前版本安装包，安装包必须由 Git 忽略且禁止提交。
```

- [ ] **Step 3: 验证忽略行为和文本格式**

Run:

```powershell
git check-ignore -v -- "Lang Drill Agent_1.0.2_x64-setup.exe"
git diff --check
```

Expected: 第一条命令输出 `.gitignore` 中新增规则；第二条命令退出码为 `0`。

- [ ] **Step 4: 提交规则修改**

```powershell
git add -- .gitignore AGENTS.md
git commit -m "chore: require current local desktop artifact"
```

### Task 2: 本机构建并保存 v1.0.2 安装包

**Files:**
- Generate, ignored: `src-tauri/target/release/lang-drill-agent-desktop.exe`
- Generate, ignored: `src-tauri/target/release/bundle/nsis/Lang Drill Agent_1.0.2_x64-setup.exe`
- Generate, ignored: `Lang Drill Agent_1.0.2_x64-setup.exe`

**Interfaces:**
- Consumes: `scripts/desktop/build-desktop.ps1 -SkipInstall`、`src-tauri/tauri.conf.json` 中的 `version`。
- Produces: 根目录当前版本 NSIS 安装包。

- [ ] **Step 1: 确认项目声明版本**

Run:

```powershell
$tauri = Get-Content src-tauri\tauri.conf.json -Raw | ConvertFrom-Json
if ($tauri.version -ne "1.0.2") { throw "Expected 1.0.2, got $($tauri.version)" }
```

Expected: 退出码为 `0`。

- [ ] **Step 2: 执行完整桌面 release 构建**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\desktop\build-desktop.ps1 -SkipInstall
```

Expected: 退出码为 `0`，Tauri release EXE 与 NSIS 安装包生成成功。

- [ ] **Step 3: 验证构建目录产物**

Run:

```powershell
$releaseExe = Get-Item "src-tauri\target\release\lang-drill-agent-desktop.exe"
$installer = Get-Item "src-tauri\target\release\bundle\nsis\Lang Drill Agent_1.0.2_x64-setup.exe"
if ($releaseExe.VersionInfo.ProductVersion -ne "1.0.2") { throw "Release EXE version mismatch" }
if ($installer.Length -le 0) { throw "Installer is empty" }
Get-FileHash -Algorithm SHA256 -LiteralPath $installer.FullName
```

Expected: release EXE 产品版本为 `1.0.2`，安装包存在且非空，并输出 SHA256。

- [ ] **Step 4: 复制并验证根目录产物**

Run:

```powershell
$root = (Resolve-Path ".").Path
$source = Join-Path $root "src-tauri\target\release\bundle\nsis\Lang Drill Agent_1.0.2_x64-setup.exe"
$destination = Join-Path $root "Lang Drill Agent_1.0.2_x64-setup.exe"
Copy-Item -LiteralPath $source -Destination $destination -Force
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
$destinationHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash
if ($sourceHash -ne $destinationHash) { throw "Root installer hash mismatch" }
```

Expected: 根目录副本存在，且 SHA256 与构建目录原件完全一致。

- [ ] **Step 5: 验证成功后移除根目录旧版本**

Run:

```powershell
$root = (Resolve-Path ".").Path
$current = Join-Path $root "Lang Drill Agent_1.0.2_x64-setup.exe"
$old = Get-ChildItem -LiteralPath $root -File -Filter "Lang Drill Agent_*_x64-setup.exe" |
  Where-Object { $_.FullName -ne $current }
foreach ($item in $old) {
  if ($item.DirectoryName -ne $root) { throw "Refusing to remove artifact outside project root" }
  Remove-Item -LiteralPath $item.FullName -Force
}
```

Expected: 仅删除项目根目录中命名匹配的旧版本安装包；当前 `v1.0.2` 产物保留。

### Task 3: 验收、进展与归档

**Files:**
- Create or update, ignored: `doc/验收/模块/验收-桌面版与发布产物.md`
- Create then archive, ignored: `doc/验收/归档/2026-07-28/验收-2026-07-28-本机v1.0.2桌面产物.md`
- Create or update, ignored: `doc/进展记录/2026-07-28.md`
- Move to archive, ignored: `doc/归档/2026-07-28/2026-07-28-desktop-local-artifact-design.md`
- Move to archive, ignored: `doc/归档/2026-07-28/2026-07-28-desktop-local-artifact-plan.md`
- Remove after archival: `docs/superpowers/specs/2026-07-28-desktop-local-artifact-design.md`
- Remove after archival: `docs/superpowers/plans/2026-07-28-desktop-local-artifact.md`

**Interfaces:**
- Consumes: Task 1 的规则修改、Task 2 的构建输出与验证证据。
- Produces: L1 任务验收记录、长期桌面发布产物验收项和本地进展记录。

- [ ] **Step 1: 执行本任务验收命令**

Run:

```powershell
$root = (Resolve-Path ".").Path
$expected = Join-Path $root "Lang Drill Agent_1.0.2_x64-setup.exe"
$target = Join-Path $root "src-tauri\target\release\bundle\nsis\Lang Drill Agent_1.0.2_x64-setup.exe"
$releaseExe = Get-Item (Join-Path $root "src-tauri\target\release\lang-drill-agent-desktop.exe")
$artifacts = @(Get-ChildItem -LiteralPath $root -File -Filter "Lang Drill Agent_*_x64-setup.exe")
if ($releaseExe.VersionInfo.ProductVersion -ne "1.0.2") { throw "Wrong release EXE version" }
if ($artifacts.Count -ne 1 -or $artifacts[0].FullName -ne $expected) { throw "Root artifact set is not current-only" }
if ((Get-FileHash $expected).Hash -ne (Get-FileHash $target).Hash) { throw "Installer hashes differ" }
git check-ignore -q -- $expected
if ($LASTEXITCODE -ne 0) { throw "Root installer is not ignored" }
```

Expected: 退出码为 `0`。

- [ ] **Step 2: 写入模块、任务和进展记录**

记录以下可验证结论：

```text
涉及模块：Windows 桌面版与发布产物
验收等级：L1
验证步骤：本机 release 构建、ProductVersion 检查、根目录产物唯一性、SHA256 一致性、Git 忽略检查
预期结果：根目录仅保留当前 v1.0.2 安装包，且与构建目录原件一致
最终结论：通过（仅当所有命令退出码为 0）
```

进展记录时间段使用本地时间，格式严格为 `YYYY-MM-DD HH:mm ~ YYYY-MM-DD HH:mm`。

- [ ] **Step 3: 归档已实现的设计与计划**

将设计和计划内容移动到 `doc/归档/2026-07-28/`，从 `docs/superpowers/` 删除；归档文件保留完整内容。

- [ ] **Step 4: 提交归档后的跟踪状态**

```powershell
git add -u -- docs/superpowers
git commit -m "docs: archive completed desktop artifact plan"
```

### Task 4: 完整验证并合并主线

**Files:**
- Verify only: all tracked project files

**Interfaces:**
- Consumes: Task 1–3 的最终工作树。
- Produces: 已验证并合并到 `main` 的规则修改，以及根目录本地 `v1.0.2` 安装包。

- [ ] **Step 1: 运行完整验证**

Run:

```powershell
py -m pytest -q
py -m ruff check backend tests scripts
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix runtime/pi-bridge test
cargo check --manifest-path src-tauri\Cargo.toml
```

Expected: 所有命令退出码为 `0`，没有失败测试或编译错误。

- [ ] **Step 2: 检查版本、哈希、Git 和差异**

Run:

```powershell
$root = (Resolve-Path ".").Path
$rootInstaller = Join-Path $root "Lang Drill Agent_1.0.2_x64-setup.exe"
$builtInstaller = Join-Path $root "src-tauri\target\release\bundle\nsis\Lang Drill Agent_1.0.2_x64-setup.exe"
Get-Item $rootInstaller | Select-Object FullName,Length,LastWriteTime
Get-FileHash -Algorithm SHA256 $rootInstaller,$builtInstaller
git check-ignore -v -- $rootInstaller
git diff --check
git status --short --branch
```

Expected: 两份哈希一致，根目录安装包被忽略，跟踪文件无未提交修改；仅允许保留任务开始前已存在的未跟踪 `.superpowers/`。

- [ ] **Step 3: 按项目规则合并 `main` 并删除任务分支**

```powershell
git switch main
git merge --no-ff codex/feature-local-desktop-artifact
```

在合并后的 `main` 重新执行 Task 4 Step 1 和 Step 2。全部通过后：

```powershell
git branch -d codex/feature-local-desktop-artifact
```

Expected: 修改已进入本地 `main`，任务分支已删除；不自动推送 GitHub。
