"""演示站 (演示web2) 脱敏与一致性测试。

验证两件事：

1. 脱敏：演示站源码不得访问 ``.env``、真实后端 URL、``%APPDATA%``、用户路径、
   API Key / token、subprocess 或 Tauri updater 执行，也不得导入生产 API 模块。
2. 一致性：``演示web2/src/mock/`` 下除 ``api.ts`` 外的 UI 文件必须与
   ``frontend/src/`` 对应文件在路径归一化后逐字节一致。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_SRC = REPO_ROOT / "演示web2" / "src"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
MOCK_SRC = DEMO_SRC / "mock"

# ---------- 工具函数 ----------


def _read_files(root: Path) -> list[tuple[Path, str]]:
    """递归读取 root 下所有源码文件，返回 (相对路径, 内容) 列表。"""
    results: list[tuple[Path, str]] = []
    if not root.is_dir():
        return results
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".ts", ".tsx", ".css", ".html"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        results.append((path, content))
    return results


def _all_demo_files() -> list[tuple[Path, str]]:
    """读取演示站 src/ 下所有源码文件（含 landing 和 mock）。"""
    return _read_files(DEMO_SRC)


def _rel(p: Path) -> str:
    """返回相对于演示站 src/ 的相对路径字符串，用正斜杠。"""
    try:
        return str(p.relative_to(DEMO_SRC)).replace("\\", "/")
    except ValueError:
        return str(p)


# ---------- 脱敏测试 ----------


@pytest.fixture(scope="module")
def demo_files() -> list[tuple[Path, str]]:
    """读取演示站 src/ 下所有源码文件（含 landing 和 mock）。"""
    return _all_demo_files()


class TestSanitization:
    """演示站不得包含真实环境访问、密钥或后端连接。"""

    def test_no_process_env_access(self, demo_files: list[tuple[Path, str]]) -> None:
        """禁止使用 Node.js process.env 读取环境变量。"""
        offenders: list[str] = []
        for path, content in demo_files:
            if path.suffix == ".d.ts":
                continue
            if re.search(r"\bprocess\.env\b", content):
                offenders.append(_rel(path))
        assert not offenders, f"演示站禁止使用 process.env: {offenders}"

    def test_no_dotenv_import(self, demo_files: list[tuple[Path, str]]) -> None:
        """禁止加载 dotenv 或读取 .env 文件。"""
        offenders: list[str] = []
        for path, content in demo_files:
            if re.search(r'\bfrom\s+["\']dotenv["\']', content) or re.search(r'\brequire\s*\(\s*["\']dotenv["\']', content):
                offenders.append(_rel(path))
            if re.search(r'\.env["\']', content) and "vite-env" not in path.name:
                offenders.append(_rel(path))
        assert not offenders, f"演示站禁止加载 dotenv 或读取 .env 文件: {offenders}"

    def test_no_custom_vite_env_vars(self, demo_files: list[tuple[Path, str]]) -> None:
        """禁止读取 VITE_LANGDRILL_* 自定义环境变量（仅允许 Vite 内置 BASE_URL/MODE/DEV/PROD）。"""
        offenders: list[str] = []
        for path, content in demo_files:
            if path.suffix == ".d.ts":
                continue
            # 匹配 import.meta.env.VITE_LANGDRILL_... 的运行时访问
            if re.search(r"import\.meta\.env\.VITE_LANGDRILL", content):
                offenders.append(_rel(path))
        assert not offenders, f"演示站禁止读取 VITE_LANGDRILL_* 自定义环境变量: {offenders}"

    def test_no_real_backend_urls(self, demo_files: list[tuple[Path, str]]) -> None:
        """禁止出现真实后端 URL（127.0.0.1:8000 / 18080 / localhost:8000 等）。"""
        offenders: list[str] = []
        forbidden_urls = [
            r"127\.0\.0\.1:8000",
            r"127\.0\.0\.1:18080",
            r"localhost:8000",
            r"localhost:18080",
            r"0\.0\.0\.0:8000",
            r"0\.0\.0\.0:18080",
        ]
        pattern = "|".join(forbidden_urls)
        for path, content in demo_files:
            if re.search(pattern, content):
                offenders.append(_rel(path))
        assert not offenders, f"演示站禁止出现真实后端 URL: {offenders}"

    def test_no_appdata_or_user_paths(self, demo_files: list[tuple[Path, str]]) -> None:
        """禁止出现真实用户路径。

        ``%APPDATA%`` / ``APPDATA`` 作为信息性文本出现在 i18n 翻译字符串中是允许的
        （例如"桌面版数据保存到 %APPDATA%"只是给用户看的说明文字）。
        实际的环境变量访问由 test_no_process_env_access 覆盖，
        文件系统访问由 test_no_file_system_access 覆盖。
        本测试只检查真实主机路径（开发机路径、用户目录）。
        """
        offenders: list[str] = []
        forbidden_patterns = [
            r"D:\\1Folder",
            r"C:\\Users\\",
            r"/home/\w",
            r"/Users/\w",
        ]
        for path, content in demo_files:
            for pat in forbidden_patterns:
                if re.search(pat, content):
                    offenders.append(f"{_rel(path)} (匹配: {pat})")
        assert not offenders, f"演示站禁止出现真实用户路径: {offenders}"

    def test_no_api_keys_or_tokens(self, demo_files: list[tuple[Path, str]]) -> None:
        """禁止出现真实 API Key / Token 密钥值。

        环境变量名（如 ``"MINERU_TOKEN"`` 字符串标签）允许出现在 UI 标签中，
        因为那只是告诉用户该设置哪个环境变量；禁止的是真实密钥值。
        ``process.env`` 访问已由 test_no_process_env_access 覆盖。
        """
        offenders: list[str] = []
        forbidden_patterns = [
            r"\bsk-or-[a-zA-Z0-9]{10,}",
            r"\bsk-proj-[a-zA-Z0-9]{10,}",
            r"\bsk-[a-zA-Z0-9]{20,}",
            r"Bearer\s+[a-zA-Z0-9]{10,}",
        ]
        for path, content in demo_files:
            for pat in forbidden_patterns:
                if re.search(pat, content):
                    offenders.append(f"{_rel(path)} (匹配: {pat})")
        assert not offenders, f"演示站禁止出现真实 API Key / Token 值: {offenders}"

    def test_no_subprocess_execution(self, demo_files: list[tuple[Path, str]]) -> None:
        """禁止使用 Node.js subprocess（child_process / execSync / spawnSync）。"""
        offenders: list[str] = []
        forbidden_patterns = [
            r"\bchild_process\b",
            r"\bexecSync\b",
            r"\bspawnSync\b",
            r"require\s*\(\s*['\"]child_process['\"]",
        ]
        for path, content in demo_files:
            for pat in forbidden_patterns:
                if re.search(pat, content):
                    offenders.append(f"{_rel(path)} (匹配: {pat})")
        assert not offenders, f"演示站禁止使用 subprocess: {offenders}"

    def test_tauri_updater_only_in_updater_ts(
        self, demo_files: list[tuple[Path, str]]
    ) -> None:
        """Tauri updater / process 插件引用只能出现在 mock/features/update/updater.ts。"""
        offenders: list[str] = []
        allowed_rel = "mock/features/update/updater.ts"
        for path, content in demo_files:
            rel = _rel(path)
            if rel == allowed_rel:
                continue
            if re.search(r"@tauri-apps/plugin-updater", content):
                offenders.append(f"{rel} (plugin-updater)")
            if re.search(r"@tauri-apps/plugin-process", content):
                offenders.append(f"{rel} (plugin-process)")
            if re.search(r"tauri_plugin_updater", content):
                offenders.append(f"{rel} (rust tauri_plugin_updater)")
        assert not offenders, (
            f"Tauri updater 引用只能出现在 {allowed_rel}: {offenders}"
        )

    def test_no_production_api_imports(
        self, demo_files: list[tuple[Path, str]]
    ) -> None:
        """禁止从 mock 目录外导入生产 API 模块（如 ../../api 之外的 ../../backend）。"""
        offenders: list[str] = []
        for path, content in demo_files:
            rel = _rel(path)
            if not rel.startswith("mock/"):
                continue
            # 禁止导入 ../../backend、../../../backend、../../api（主 api.ts 由 mock 替换）
            # 但允许 ../../api（指向 mock/api.ts，这是 mock 内部的相对路径）
            # 实际上 mock 内部的 ../../api 指向 mock/api.ts，是允许的
            # 禁止的是逃逸到 mock 目录外的导入
            if re.search(r'from\s+["\']\.\.\/\.\.\/\.\.\/', content):
                offenders.append(f"{rel} (三级以上相对导入)")
            if re.search(r'from\s+["\']\.\.\/\.\.\/\.\.\/\.\.\/', content):
                offenders.append(f"{rel} (四级以上相对导入)")
            # 禁止直接导入 backend 模块
            if re.search(r'from\s+["\'].*backend', content):
                offenders.append(f"{rel} (导入 backend)")
        assert not offenders, f"演示站禁止导入生产 API 模块: {offenders}"

    def test_no_file_system_access(self, demo_files: list[tuple[Path, str]]) -> None:
        """禁止使用 Node.js fs 模块直接访问文件系统。"""
        offenders: list[str] = []
        forbidden_patterns = [
            r'\bfrom\s+["\']fs["\']',
            r'\bfrom\s+["\']fs/promises["\']',
            r'\bfrom\s+["\']node:fs["\']',
            r'\brequire\s*\(\s*["\']fs["\']',
            r"\breadFileSync\b",
            r"\bwriteFileSync\b",
            r"\breadFile\b",
            r"\bwriteFile\b",
        ]
        for path, content in demo_files:
            for pat in forbidden_patterns:
                if re.search(pat, content):
                    offenders.append(f"{_rel(path)} (匹配: {pat})")
        assert not offenders, f"演示站禁止直接访问文件系统: {offenders}"


# ---------- 一致性测试 ----------


def _should_skip_for_parity(rel_path: str) -> bool:
    """判断前端源文件是否应跳过 mock 一致性比较。"""
    # 根 api.ts 由 mock 替换
    if rel_path == "api.ts":
        return True
    # 根 main.tsx 由演示站 app-main.tsx 替换
    if rel_path == "main.tsx":
        return True
    # 测试文件不入 mock
    if re.match(r"^.*\.test\.(ts|tsx)$", rel_path):
        return True
    # stringInventory 是前端构建期测试工具，不入 mock
    if rel_path == "i18n/stringInventory.test.ts":
        return True
    return False


def _normalize(content: str) -> str:
    """归一化行尾（CRLF → LF）后返回。"""
    return content.replace("\r\n", "\n").replace("\r", "\n")


@pytest.fixture(scope="module")
def frontend_source_files() -> list[tuple[str, str]]:
    """返回 (相对路径, 归一化内容) 列表，仅包含需要同步的文件。"""
    results: list[tuple[str, str]] = []
    if not FRONTEND_SRC.is_dir():
        return results
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".ts", ".tsx", ".css", ".d.ts"}:
            continue
        rel = str(path.relative_to(FRONTEND_SRC)).replace("\\", "/")
        if _should_skip_for_parity(rel):
            continue
        try:
            content = _normalize(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
        results.append((rel, content))
    return results


class TestMockParity:
    """mock/ 下除 api.ts 外的 UI 文件必须与 frontend/src/ 一致。"""

    def test_mock_directory_exists(self) -> None:
        """mock 目录必须存在。"""
        assert MOCK_SRC.is_dir(), f"mock 目录不存在: {MOCK_SRC}"

    def test_all_frontend_ui_files_have_mock_counterpart(
        self, frontend_source_files: list[tuple[str, str]]
    ) -> None:
        """前端每个需同步的 UI 文件在 mock 中必须有对应文件。"""
        missing: list[str] = []
        for rel, _ in frontend_source_files:
            mock_path = MOCK_SRC / rel
            if not mock_path.is_file():
                missing.append(rel)
        assert not missing, f"mock 中缺少以下前端 UI 文件: {missing}"

    def test_mock_ui_files_match_frontend_source(
        self, frontend_source_files: list[tuple[str, str]]
    ) -> None:
        """mock 中每个 UI 文件的内容必须与前端源文件一致（行尾归一化后）。"""
        mismatches: list[str] = []
        for rel, expected in frontend_source_files:
            mock_path = MOCK_SRC / rel
            if not mock_path.is_file():
                continue
            try:
                actual = _normalize(mock_path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError):
                mismatches.append(f"{rel} (读取失败)")
                continue
            if actual != expected:
                mismatches.append(rel)
        assert not mismatches, (
            f"以下 mock 文件与前端源文件不一致，请运行 sync-demo-web2.ps1 同步: {mismatches}"
        )

    def test_mock_has_no_extra_ui_files(
        self, frontend_source_files: list[tuple[str, str]]
    ) -> None:
        """mock 中不应有前端已删除的遗留文件（除 api.ts）。"""
        expected_rels = {rel for rel, _ in frontend_source_files}
        expected_rels.add("api.ts")  # mock 专有
        extra: list[str] = []
        if MOCK_SRC.is_dir():
            for path in sorted(MOCK_SRC.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix not in {".ts", ".tsx", ".css", ".d.ts"}:
                    continue
                rel = str(path.relative_to(MOCK_SRC)).replace("\\", "/")
                if rel not in expected_rels:
                    extra.append(rel)
        assert not extra, f"mock 中存在前端已删除的遗留文件: {extra}"


# ---------- 演示站元数据测试 ----------


class TestDemoMetadata:
    """演示站版本元数据必须与发布版本一致。"""

    def test_demo_version_file_exists(self) -> None:
        """demoVersion.ts 必须存在。"""
        assert (DEMO_SRC / "demoVersion.ts").is_file(), "demoVersion.ts 不存在"

    def test_demo_version_matches_release(self) -> None:
        """demoVersion.ts 的版本号必须与 VERSION 文件一致。"""
        version_file = REPO_ROOT / "VERSION"
        assert version_file.is_file(), "VERSION 文件不存在"
        release_version = version_file.read_text(encoding="utf-8").strip()

        demo_ts = DEMO_SRC / "demoVersion.ts"
        content = demo_ts.read_text(encoding="utf-8")
        assert f'version: "{release_version}"' in content, (
            f"demoVersion.ts 版本号与 VERSION 不一致: 期望 {release_version}"
        )

    def test_demo_channel_is_experimental(self) -> None:
        """demoVersion.ts 的 channel 必须为 experimental。"""
        demo_ts = DEMO_SRC / "demoVersion.ts"
        content = demo_ts.read_text(encoding="utf-8")
        assert 'channel: "experimental"' in content, (
            "demoVersion.ts channel 必须为 experimental"
        )
