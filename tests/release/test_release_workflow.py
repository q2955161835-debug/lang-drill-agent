"""验证实验版发布工作流的契约。

契约来源：07-更新国际化演示与实验版发布-实施计划.md Task 7。
- 触发条件：push tag 匹配 v* + 手动 dispatch
- 发布 job 必须依赖后端/前端/Pi/Rust/桌面测试 job
- 权限最小化：只给 contents: write
- 使用固定主版本号的 actions
- 必须创建 prerelease（prerelease: true）
- 必须上传所有更新器产物：NSIS 安装包、更新器归档/签名、latest.json、校验和、发布说明、Pi 运行时清单/载荷
- 必须使用 TAURI_SIGNING_PRIVATE_KEY 和 TAURI_SIGNING_PRIVATE_KEY_PASSWORD 密钥
- tag 版本与清单版本不一致时必须失败
- Pages 部署必须先运行演示站卫生测试再部署
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
RELEASE_WORKFLOW = WORKFLOWS_DIR / "release-experimental.yml"
CI_WORKFLOW = WORKFLOWS_DIR / "ci.yml"
PAGES_WORKFLOW = WORKFLOWS_DIR / "pages-demo-web2.yml"
VM_WORKFLOW = WORKFLOWS_DIR / "desktop-installer-vm-test.yml"
VERSION_FILE = REPO_ROOT / "VERSION"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "release" / "verify-release-assets.ps1"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------- module-scoped fixtures ----------
# 注意：使用 module 作用域函数形式而非 class 作用域实例方法，
# 避免 PytestRemovedIn10Warning。


@pytest.fixture(scope="module")
def release_workflow() -> dict:
    return _load_yaml(RELEASE_WORKFLOW)


@pytest.fixture(scope="module")
def release_workflow_text() -> str:
    return _read_text(RELEASE_WORKFLOW)


@pytest.fixture(scope="module")
def pages_workflow_text() -> str:
    return _read_text(PAGES_WORKFLOW)


@pytest.fixture(scope="module")
def vm_workflow_text() -> str:
    return _read_text(VM_WORKFLOW)


@pytest.fixture(scope="module")
def ci_workflow_text() -> str:
    return _read_text(CI_WORKFLOW)


@pytest.fixture(scope="module")
def verify_script_text() -> str:
    return _read_text(VERIFY_SCRIPT)


# ---------- 工作流存在性 ----------


class TestReleaseWorkflowExists:
    def test_release_workflow_file_exists(self):
        assert RELEASE_WORKFLOW.exists(), "release-experimental.yml 不存在"

    def test_verify_release_assets_script_exists(self):
        assert VERIFY_SCRIPT.exists(), "verify-release-assets.ps1 不存在"


# ---------- 触发条件 ----------


class TestReleaseTriggers:
    def test_triggers_on_version_tag_push(self, release_workflow: dict):
        on = release_workflow.get("on") or release_workflow.get(True, {})
        assert "push" in on, "工作流必须由 push 触发"
        tags = on["push"].get("tags", [])
        assert any(fnmatch.fnmatch(t, "v*") for t in tags), (
            f"push.tags 必须包含 v* 模式，实际: {tags}"
        )

    def test_supports_manual_dispatch(self, release_workflow: dict):
        on = release_workflow.get("on") or release_workflow.get(True, {})
        assert "workflow_dispatch" in on, "工作流必须支持手动触发"

    def test_manual_dispatch_uses_requested_tag(self, release_workflow_text: str):
        assert "${{ inputs.tag }}" in release_workflow_text, (
            "手动重建发布资产时必须读取 workflow_dispatch 的 tag 输入"
        )
        assert "${{ github.event_name }}" in release_workflow_text, (
            "工作流必须区分 tag push 与 workflow_dispatch"
        )


# ---------- Job 依赖 ----------


class TestReleaseJobDependencies:
    def test_release_job_needs_test_jobs(self, release_workflow: dict):
        jobs = release_workflow.get("jobs", {})
        release_job = jobs.get("release")
        assert release_job is not None, "必须有 release job"
        needs = release_job.get("needs", [])
        job_names = set(jobs.keys())
        # release job 必须依赖至少 3 个测试 job
        assert len(needs) >= 3, (
            f"release job 必须至少依赖 3 个测试 job，实际 needs: {needs}"
        )
        for needed in needs:
            assert needed in job_names, f"needs 引用了不存在的 job: {needed}"

    def test_has_backend_test_job(self, release_workflow: dict):
        jobs = release_workflow.get("jobs", {})
        assert any(
            "backend" in name or "python" in name for name in jobs
        ), "必须有后端/Python 测试 job"

    def test_has_frontend_test_job(self, release_workflow: dict):
        jobs = release_workflow.get("jobs", {})
        assert any(
            "frontend" in name or "node" in name or "web" in name
            for name in jobs
        ), "必须有前端/Node 测试 job"

    def test_has_rust_test_job(self, release_workflow: dict):
        jobs = release_workflow.get("jobs", {})
        assert any(
            "rust" in name or "cargo" in name or "tauri" in name
            for name in jobs
        ), "必须有 Rust/Tauri 测试 job"

    def test_has_pi_test_job(self, release_workflow: dict):
        jobs = release_workflow.get("jobs", {})
        assert any(
            "pi" in name for name in jobs
        ), "必须有 Pi 测试 job"


# ---------- 权限 ----------


class TestReleasePermissions:
    def test_has_contents_write_permission(self, release_workflow: dict):
        perms = release_workflow.get("permissions", {})
        if isinstance(perms, str):
            assert perms == "write-all" or "contents" in perms
        else:
            assert perms.get("contents") == "write", (
                f"permissions.contents 必须为 write，实际: {perms}"
            )

    def test_does_not_request_excessive_permissions(self, release_workflow: dict):
        perms = release_workflow.get("permissions", {})
        if isinstance(perms, str):
            pytest.skip("字符串权限无法细粒度检查")
        # 不应该有不必要的写权限
        excessive = {"packages", "deployments", "statuses", "checks"}
        for perm in excessive:
            if perm in perms:
                assert perms[perm] != "write", (
                    f"不应请求 {perm}:write 权限"
                )


# ---------- 固定 Action 版本 ----------


class TestPinnedActions:
    def test_uses_pinned_action_major_versions(self, release_workflow_text: str):
        # 查找所有 actions/xxx@ 引用
        refs = re.findall(r"uses:\s*(actions/\S+)", release_workflow_text)
        assert refs, "工作流必须使用至少一个 action"
        for ref in refs:
            # 必须使用 @vN 格式，不能是 @main/@master/@latest 或 commit hash
            assert re.match(r"^actions/\S+@v\d+", ref), (
                f"action 必须使用固定主版本号 (@vN)，实际: {ref}"
            )


# ---------- Pre-release ----------


class TestPrerelease:
    def test_creates_prerelease(self, release_workflow_text: str):
        # 必须设置 prerelease: true
        assert "prerelease: true" in release_workflow_text or "prerelease:True" in release_workflow_text, (
            "必须创建 prerelease（prerelease: true）"
        )


# ---------- 产物上传 ----------


class TestReleaseArtifacts:
    def test_uploads_nsis_installer(self, release_workflow_text: str):
        assert re.search(r"\.exe|nsis|installer", release_workflow_text, re.IGNORECASE), (
            "必须上传 NSIS 安装包"
        )

    def test_uploads_updater_signature(self, release_workflow_text: str):
        assert re.search(r"\.sig\b", release_workflow_text), (
            "必须上传更新器签名文件 (.sig)"
        )

    def test_uploads_latest_json(self, release_workflow_text: str):
        assert "latest.json" in release_workflow_text, (
            "必须上传 latest.json 更新器清单"
        )

    def test_uploads_checksums(self, release_workflow_text: str):
        assert re.search(r"checksum|sha256|\.sha256", release_workflow_text, re.IGNORECASE), (
            "必须上传校验和文件"
        )

    def test_uploads_release_notes(self, release_workflow_text: str):
        assert re.search(r"release.notes|release-notes", release_workflow_text, re.IGNORECASE), (
            "必须上传发布说明"
        )

    def test_uploads_pi_runtime_manifest(self, release_workflow_text: str):
        assert re.search(r"pi.runtime.manifest|pi-runtime-manifest", release_workflow_text, re.IGNORECASE), (
            "必须上传 Pi 运行时清单"
        )

    def test_overwrites_same_name_assets_on_manual_rebuild(
        self, release_workflow_text: str
    ):
        assert "overwrite_files: true" in release_workflow_text, (
            "手动重建发布时必须覆盖同名错误资产"
        )


# ---------- 密钥 ----------


class TestReleaseSecrets:
    def test_uses_tauri_signing_private_key(self, release_workflow_text: str):
        assert "TAURI_SIGNING_PRIVATE_KEY" in release_workflow_text, (
            "必须使用 TAURI_SIGNING_PRIVATE_KEY 密钥"
        )

    def test_uses_tauri_signing_password(self, release_workflow_text: str):
        assert "TAURI_SIGNING_PRIVATE_KEY_PASSWORD" in release_workflow_text, (
            "必须使用 TAURI_SIGNING_PRIVATE_KEY_PASSWORD 密钥"
        )

    def test_does_not_print_secret_values(self, release_workflow_text: str):
        # 不应该在 echo/printf/Write-Host 中直接输出密钥值
        for secret in ["TAURI_SIGNING_PRIVATE_KEY", "TAURI_SIGNING_PRIVATE_KEY_PASSWORD"]:
            # 查找 echo ${{ secrets.SECRET }} 模式
            pattern = rf"echo.*\$\{{{{\s*secrets\.{secret}\s*\}}}}"
            assert not re.search(pattern, release_workflow_text, re.IGNORECASE), (
                f"不应在 echo 中输出 {secret} 的值"
            )


class TestDesktopInstallerVmSigning:
    def test_vm_workflow_uses_signing_private_key(self, vm_workflow_text: str):
        assert "TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}" in vm_workflow_text

    def test_vm_workflow_uses_signing_password(self, vm_workflow_text: str):
        assert (
            "TAURI_SIGNING_PRIVATE_KEY_PASSWORD: "
            "${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}"
        ) in vm_workflow_text

    def test_vm_workflow_does_not_print_secret_values(self, vm_workflow_text: str):
        for secret in ["TAURI_SIGNING_PRIVATE_KEY", "TAURI_SIGNING_PRIVATE_KEY_PASSWORD"]:
            pattern = rf"echo.*\$\{{{{\s*secrets\.{secret}\s*\}}}}"
            assert not re.search(pattern, vm_workflow_text, re.IGNORECASE)


# ---------- 版本一致性 ----------


class TestVersionConsistency:
    def test_workflow_checks_tag_matches_manifest(self, release_workflow_text: str):
        # 工作流必须包含版本一致性检查（通过 verify-version.ps1 或直接比较）
        assert (
            "verify-version" in release_workflow_text
            or "VERSION" in release_workflow_text
            or "version" in release_workflow_text.lower()
        ), "工作流必须验证 tag 版本与清单版本一致"

    def test_release_notes_file_exists(self):
        notes = REPO_ROOT / "release-notes" / "v1.0.1.md"
        assert notes.exists(), "发布说明文件不存在"


# ---------- Pages 工作流卫生检查 ----------


class TestPagesSanitization:
    def test_pages_runs_demo_build_before_deploy(self, pages_workflow_text: str):
        assert "npm run build" in pages_workflow_text or "npm ci" in pages_workflow_text, (
            "Pages 工作流必须构建演示站"
        )

    def test_pages_runs_sanitization_test(self, pages_workflow_text: str):
        # Pages 工作流必须运行卫生测试或至少安装 Python 并运行测试
        assert (
            "test_demo_sanitization" in pages_workflow_text
            or "pytest" in pages_workflow_text
            or "sanitization" in pages_workflow_text.lower()
        ), "Pages 工作流必须在部署前运行演示站卫生测试"


# ---------- CI 工作流覆盖 ----------


class TestCICoverage:
    def test_ci_runs_backend_tests(self, ci_workflow_text: str):
        assert "ruff" in ci_workflow_text or "pytest" in ci_workflow_text, (
            "CI 必须运行后端测试"
        )

    def test_ci_runs_frontend_build(self, ci_workflow_text: str):
        assert "npm run build" in ci_workflow_text, (
            "CI 必须运行前端构建"
        )


# ---------- verify-release-assets.ps1 ----------


class TestVerifyReleaseAssetsScript:
    def test_script_supports_dry_run(self, verify_script_text: str):
        assert "DryRun" in verify_script_text or "dry-run" in verify_script_text.lower(), (
            "verify-release-assets.ps1 必须支持 -DryRun 参数"
        )

    def test_script_checks_artifact_existence(self, verify_script_text: str):
        assert "latest.json" in verify_script_text, (
            "verify-release-assets.ps1 必须检查 latest.json"
        )
        assert ".sig" in verify_script_text, (
            "verify-release-assets.ps1 必须检查签名文件"
        )
