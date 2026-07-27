# 本机桌面编译产物设计

## 目标

- 使用当前仓库源码在本机完整构建 Lang Drill Agent `v1.0.2` Windows x64 桌面安装包。
- 将最新 NSIS 单文件安装包复制到项目根目录，便于本机查找和使用。
- 在项目长期规则中明确：发布新版本时必须在本机重新构建，并用新产物替换根目录旧版本。

## 产物约定

- 根目录产物名称使用 Tauri 当前版本生成的标准名称：`Lang Drill Agent_<版本>_x64-setup.exe`。
- 根目录只保留一个当前版本安装包；新版本完成构建和验证后，删除根目录旧版本安装包。
- 原始 release 可执行文件依赖 `app/` 和 `desktop-runtime/` 资源目录，因此不将裸 `lang-drill-agent-desktop.exe` 单独复制到根目录。
- 根目录安装包仅作为本机编译产物保存，通过 `.gitignore` 排除，不提交到 Git。

## 构建与替换流程

1. 从项目根目录运行现有 `scripts/desktop/build-desktop.ps1 -SkipInstall`。
2. 构建成功后检查：
   - `src-tauri/target/release/lang-drill-agent-desktop.exe` 的产品版本为当前项目版本；
   - `src-tauri/target/release/bundle/nsis/` 中存在当前版本安装包；
   - 安装包非空，并可计算 SHA256。
3. 将当前版本安装包复制到项目根目录。
4. 比较根目录副本与构建目录原件的 SHA256，确认完全一致。
5. 仅在上述验证全部通过后，移除根目录其它旧版本安装包。

## 项目规则

在 `AGENTS.md` 的桌面构建规则中增加：

> 每次发布新版本时，必须在本机执行桌面 release 构建；构建和版本验证通过后，将最新 NSIS 安装包复制到项目根目录，并替换根目录旧版本。根目录只保留当前版本安装包，安装包不得提交 Git。

同时在 `.gitignore` 增加根目录安装包忽略规则。

## 验收

- 桌面构建命令退出码为 `0`。
- release EXE 的 `ProductVersion` 为 `1.0.2`。
- 构建目录和项目根目录均存在 `Lang Drill Agent_1.0.2_x64-setup.exe`。
- 两份安装包的 SHA256 完全一致。
- 根目录不存在其它版本的 `Lang Drill Agent_*_x64-setup.exe`。
- `git status` 不显示根目录安装包。
- `AGENTS.md` 已记录后续版本发布时的本机构建与替换规则。

## 非目标

- 不增加自动检测或自动构建启动器。
- 不将裸 release EXE 复制到项目根目录。
- 不安装或卸载桌面应用。
- 不推送 GitHub，除非用户另行确认。
