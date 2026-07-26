"""演示站下载渠道分类与一致性测试。

验证三件事：

1. ``演示web2/src/releaseChannels.ts`` 只声明稳定版 (v0.1.2) 与实验版
   (v1.0.2) 两个下载渠道，历史版本不出现在演示网页。
2. ``演示web2/src/App.tsx`` 的在线体验入口仍指向 ``#/app`` 并标注为实验版，
   不得出现“稳定版在线体验”字样。
3. 页眉与首页下载按钮默认指向稳定版；本任务不得修改 GitHub Release 元数据工作流。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_SRC = REPO_ROOT / "演示web2" / "src"
RELEASE_CHANNELS = DEMO_SRC / "releaseChannels.ts"
APP_TSX = DEMO_SRC / "App.tsx"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "release" / "verify_demo_downloads.py"


def test_release_channels_file_exists() -> None:
    """releaseChannels.ts 必须存在。"""
    assert RELEASE_CHANNELS.is_file(), f"缺少文件: {RELEASE_CHANNELS}"


def test_demo_has_only_stable_and_experimental_downloads() -> None:
    """releaseChannels.ts 只声明稳定版与实验版，不暴露历史下载渠道。"""
    text = RELEASE_CHANNELS.read_text(encoding="utf-8")
    assert 'label: "稳定版"' in text
    assert 'version: "v0.1.2"' in text
    assert "Lang.Drill.Agent_0.1.2_x64-setup.exe" in text
    assert 'label: "实验版"' in text
    assert 'version: "v1.0.2"' in text
    assert "Lang.Drill.Agent_1.0.2_x64-setup.exe" in text
    assert 'label: "历史版本"' not in text
    assert "v1.0.0-alpha.2" not in text


def test_release_channels_provide_two_distinct_https_urls() -> None:
    """两个渠道的 downloadUrl 必须是两个不同的 GitHub Release 直链。"""
    import re

    text = RELEASE_CHANNELS.read_text(encoding="utf-8")
    urls = re.findall(r'downloadUrl:\s*"([^"]+)"', text)
    assert len(urls) == 2, f"应有两个 downloadUrl，实际: {urls}"
    assert len(set(urls)) == 2, f"downloadUrl 重复: {urls}"
    for url in urls:
        assert url.startswith("https://github.com/"), url
        assert "/releases/download/" in url, url


def test_online_experience_remains_experimental() -> None:
    """在线体验入口仍指向 #/app 且标注为实验版。"""
    app = APP_TSX.read_text(encoding="utf-8")
    assert 'href="#/app"' in app
    assert "在线体验（实验版）" in app
    assert "稳定版在线体验" not in app


def test_header_and_hero_download_buttons_point_to_stable() -> None:
    """页眉与首页主下载按钮必须默认指向稳定版。"""
    app = APP_TSX.read_text(encoding="utf-8")
    assert "const DEFAULT_DOWNLOAD = releaseChannels.stable;" in app
    assert "下载稳定版 {DEFAULT_DOWNLOAD.version}" in app
    assert "下载 Windows 桌面版 {DEFAULT_DOWNLOAD.version}" in app
    assert "href={DEFAULT_DOWNLOAD.downloadUrl}" in app


def test_install_section_renders_public_channels_without_history() -> None:
    """安装区必须渲染稳定版与实验版卡片，不显示历史版本。"""
    app = APP_TSX.read_text(encoding="utf-8")
    assert "release-channel-grid" in app
    assert "release-channel-card" in app
    assert "下载 {channel.label}" in app
    channels = RELEASE_CHANNELS.read_text(encoding="utf-8")
    assert 'label: "稳定版"' in channels
    assert 'label: "实验版"' in channels
    assert 'label: "历史版本"' not in channels
    assert "v1.0.0" not in app


def test_demo_does_not_modify_release_metadata() -> None:
    """本任务不得修改 GitHub Release 元数据工作流。"""
    changed_paths = {
        "演示web2/src/releaseChannels.ts",
        "演示web2/src/App.tsx",
        "演示web2/src/styles.css",
    }
    assert not any(".github/workflows/release-" in path for path in changed_paths)
    # 额外保护：release 工作流文件本身不被本任务删除
    if WORKFLOWS_DIR.is_dir():
        for workflow in WORKFLOWS_DIR.glob("release-*.yml"):
            assert workflow.is_file(), f"release 工作流被删除: {workflow}"


# ---------- 下载资产验证脚本测试 ----------


def _load_verifier():
    """从 scripts/release/verify_demo_downloads.py 动态加载验证模块。"""
    if not VERIFY_SCRIPT.is_file():
        raise ImportError(f"验证脚本不存在: {VERIFY_SCRIPT}")
    spec = importlib.util.spec_from_file_location(
        "verify_demo_downloads", VERIFY_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载验证脚本: {VERIFY_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    """模拟 urllib 响应，支持 status / headers / 上下文管理。"""

    def __init__(self, status: int, location: str | None = None) -> None:
        self.status = status
        self.code = status
        self.headers: dict[str, str] = {}
        if location is not None:
            self.headers["Location"] = location

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_verifier_extracts_two_https_release_assets() -> None:
    """load_download_urls 必须从 releaseChannels.ts 解析出两个 GitHub Release 直链。"""
    verifier = _load_verifier()
    urls = verifier.load_download_urls(RELEASE_CHANNELS)
    assert len(urls) == 2
    assert len(set(urls)) == 2
    for url in urls:
        assert url.startswith("https://github.com/"), url
        assert "/releases/download/" in url, url


def test_live_check_accepts_redirect_then_200(monkeypatch) -> None:
    """verify_url 应能跟随 302 重定向并最终接受 200。"""
    verifier = _load_verifier()
    responses = iter(
        [
            _FakeResponse(302, location="https://objects.example/asset"),
            _FakeResponse(200),
        ]
    )
    monkeypatch.setattr(
        verifier, "open_request", lambda request: next(responses)
    )
    assert verifier.verify_url("https://github.com/release.exe") is None


def test_live_check_raises_on_permanent_failure(monkeypatch) -> None:
    """verify_url 在收到 404 等永久失败时应抛出异常。"""
    verifier = _load_verifier()
    monkeypatch.setattr(
        verifier,
        "open_request",
        lambda request: _FakeResponse(404),
    )
    with __import__("pytest").raises(RuntimeError):
        verifier.verify_url("https://github.com/missing.exe")


def test_verifier_cli_default_mode_is_static(monkeypatch, capsys) -> None:
    """不带 --live 时只做静态校验，不发起网络请求。"""
    verifier = _load_verifier()
    monkeypatch.setattr(
        verifier, "verify_url", lambda url: (_ for _ in ()).throw(AssertionError("不应发起网络请求"))
    )
    monkeypatch.setattr("sys.argv", ["verify_demo_downloads.py"])
    exit_code = verifier.main()
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_pages_workflow_runs_live_verification() -> None:
    """pages-demo-web2.yml 必须在构建前运行 verify_demo_downloads.py --live。"""
    workflow = WORKFLOWS_DIR / "pages-demo-web2.yml"
    assert workflow.is_file(), "pages-demo-web2.yml 不存在"
    text = workflow.read_text(encoding="utf-8")
    assert "verify_demo_downloads.py --live" in text
    assert "Verify demo download assets" in text

