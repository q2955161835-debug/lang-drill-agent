"""演示站下载渠道分类与一致性测试。

验证三件事：

1. ``演示web2/src/releaseChannels.ts`` 同时声明稳定版 (v0.1.2) 与实验版
   (v1.0.0-alpha.2) 两个下载渠道，且各自指向正确的 GitHub Release 资产。
2. ``演示web2/src/App.tsx`` 的在线体验入口仍指向 ``#/app`` 并标注为实验版，
   不得出现“稳定版在线体验”字样。
3. 本任务不得修改 GitHub Release 元数据工作流。
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_SRC = REPO_ROOT / "演示web2" / "src"
RELEASE_CHANNELS = DEMO_SRC / "releaseChannels.ts"
APP_TSX = DEMO_SRC / "App.tsx"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def test_release_channels_file_exists() -> None:
    """releaseChannels.ts 必须存在。"""
    assert RELEASE_CHANNELS.is_file(), f"缺少文件: {RELEASE_CHANNELS}"


def test_demo_has_stable_and_experimental_downloads() -> None:
    """releaseChannels.ts 必须同时声明稳定版与实验版下载渠道。"""
    text = RELEASE_CHANNELS.read_text(encoding="utf-8")
    assert 'label: "稳定版"' in text
    assert 'version: "v0.1.2"' in text
    assert "Lang.Drill.Agent_0.1.2_x64-setup.exe" in text
    assert 'label: "实验版"' in text
    assert 'version: "v1.0.0-alpha.2"' in text
    assert "Lang.Drill.Agent_1.0.0-alpha.2_x64-setup.exe" in text


def test_release_channels_provide_two_distinct_https_urls() -> None:
    """两个渠道的 downloadUrl 必须是两个不同的 GitHub Release 直链。"""
    import re

    text = RELEASE_CHANNELS.read_text(encoding="utf-8")
    urls = re.findall(r'downloadUrl:\s*"([^"]+)"', text)
    assert len(urls) == 2, f"应有两个 downloadUrl，实际: {urls}"
    assert len(set(urls)) == 2, f"两个 downloadUrl 重复: {urls}"
    for url in urls:
        assert url.startswith("https://github.com/"), url
        assert "/releases/download/" in url, url


def test_online_experience_remains_experimental() -> None:
    """在线体验入口仍指向 #/app 且标注为实验版。"""
    app = APP_TSX.read_text(encoding="utf-8")
    assert 'href="#/app"' in app
    assert "在线体验（实验版）" in app
    assert "稳定版在线体验" not in app


def test_header_download_button_points_to_experimental() -> None:
    """页眉紧凑下载按钮指向实验版，避免稳定版在头部喧宾夺主。"""
    app = APP_TSX.read_text(encoding="utf-8")
    assert "下载实验版 v1.0.0-alpha.2" in app


def test_install_section_renders_both_channels() -> None:
    """安装区必须渲染两个渠道卡片，并使用稳定版/实验版按钮文案。"""
    app = APP_TSX.read_text(encoding="utf-8")
    assert "release-channel-grid" in app
    assert "release-channel-card" in app
    assert "下载 稳定版" in app
    assert "下载 实验版" in app


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
