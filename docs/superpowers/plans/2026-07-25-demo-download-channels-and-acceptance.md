# Demo Download Channels and L3 Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show stable and experimental desktop downloads in `演示web2`, keep online experience experimental, validate both assets, and complete integrated L3 regression and project acceptance records.

**Architecture:** A typed release-channel manifest replaces the single download constant and feeds the existing header, hero, and installation UI without changing the site’s design language. Static tests enforce classification and the Pages workflow performs a live asset check; final acceptance verifies all four implementation plans together.

**Tech Stack:** React 19, TypeScript, Vite, Python/pytest, GitHub Actions, existing PowerShell/local startup scripts.

## Global Constraints

- `v0.1.2` is labelled stable only inside `演示web2`.
- The stable asset is `Lang.Drill.Agent_0.1.2_x64-setup.exe`.
- The experimental asset is `Lang.Drill.Agent_1.0.0-alpha.2_x64-setup.exe`.
- Online experience links remain `#/app` and are labelled experimental.
- Do not change GitHub Release metadata; both releases currently being marked prerelease upstream is not altered.
- Preserve the existing site layout, gradients, buttons, motion, and responsive behavior.
- Do not expose local paths, user data, tokens, or keys.

## File Structure

- Create `演示web2/src/releaseChannels.ts`: typed stable/experimental manifest.
- Modify `演示web2/src/App.tsx`: download selector and experimental online labels.
- Modify `演示web2/src/styles.css`: small selector/card styles using existing variables.
- Create `scripts/release/verify_demo_downloads.py`: static manifest and optional live URL verification.
- Create `tests/demo/test_demo_download_channels.py`: classification, URL and sanitization tests.
- Modify `.github/workflows/pages-demo-web2.yml`: run live asset verification before build.
- Modify `doc/验收/模块/验收-用户知识库与RAG.md`.
- Modify `doc/验收/模块/验收-分层记忆.md`.
- Modify `doc/验收/模块/验收-真实真题蒸馏与自适应调度.md`.
- Create `doc/验收/任务/验收-2026-07-25-真题知识库RAG记忆重构.md`, then move it to `doc/验收/归档/2026-07-25/` only after conclusion `通过`.
- Modify `doc/进展记录/2026-07-25.md`.
- Move completed spec/plans to `doc/归档/2026-07-25/` after implementation and acceptance, as required by project rules.

---

### Task 1: Replace the Single Demo Download with Two Channels

**Files:**
- Create: `演示web2/src/releaseChannels.ts`
- Modify: `演示web2/src/App.tsx`
- Modify: `演示web2/src/styles.css`
- Create: `tests/demo/test_demo_download_channels.py`

**Interfaces:**
- Produces: `releaseChannels.stable`, `releaseChannels.experimental`, `onlineExperience`.
- Consumes: existing button and section components in `App.tsx`.

- [ ] **Step 1: Add exact manifest tests**

```python
def test_demo_has_stable_and_experimental_downloads():
    text = RELEASE_CHANNELS.read_text(encoding="utf-8")
    assert 'label: "稳定版"' in text
    assert 'version: "v0.1.2"' in text
    assert "Lang.Drill.Agent_0.1.2_x64-setup.exe" in text
    assert 'label: "实验版"' in text
    assert 'version: "v1.0.0-alpha.2"' in text
    assert "Lang.Drill.Agent_1.0.0-alpha.2_x64-setup.exe" in text

def test_online_experience_remains_experimental():
    app = APP_TSX.read_text(encoding="utf-8")
    assert 'href="#/app"' in app
    assert "在线体验（实验版）" in app
    assert "稳定版在线体验" not in app

def test_demo_does_not_modify_release_metadata():
    changed_paths = {
        "演示web2/src/releaseChannels.ts",
        "演示web2/src/App.tsx",
        "演示web2/src/styles.css",
    }
    assert not any(".github/workflows/release-" in path for path in changed_paths)
```

- [ ] **Step 2: Run tests and verify missing manifest failure**

Run: `py -m pytest tests/demo/test_demo_download_channels.py -v`

Expected: FAIL because `releaseChannels.ts` does not exist.

- [ ] **Step 3: Add the exact typed release manifest**

```ts
export type DemoReleaseChannel = {
  id: "stable" | "experimental";
  label: "稳定版" | "实验版";
  version: string;
  description: string;
  downloadUrl: string;
};

export const releaseChannels = {
  stable: {
    id: "stable",
    label: "稳定版",
    version: "v0.1.2",
    description: "适合优先考虑稳定性的本地安装。",
    downloadUrl:
      "https://github.com/q2955161835-debug/lang-drill-agent/releases/download/v0.1.2/Lang.Drill.Agent_0.1.2_x64-setup.exe",
  },
  experimental: {
    id: "experimental",
    label: "实验版",
    version: "v1.0.0-alpha.2",
    description: "包含最新 Agent、记忆、知识库与创造模式能力。",
    downloadUrl:
      "https://github.com/q2955161835-debug/lang-drill-agent/releases/download/v1.0.0-alpha.2/Lang.Drill.Agent_1.0.0-alpha.2_x64-setup.exe",
  },
} satisfies Record<"stable" | "experimental", DemoReleaseChannel>;

export const onlineExperience = {
  channel: "experimental" as const,
  href: "#/app",
  label: "在线体验（实验版）",
};
```

- [ ] **Step 4: Reuse existing visual language in all download locations**

In the header, keep one compact primary download button pointing to experimental and label it `下载实验版 v1.0.0-alpha.2`. In Hero, use `onlineExperience` for the online button and link the secondary download to the experimental channel.

Replace the installation section’s single button with:

```tsx
<div className="release-channel-grid" aria-label="桌面版下载选择">
  {Object.values(releaseChannels).map(channel => (
    <article className={`release-channel-card ${channel.id}`} key={channel.id}>
      <span>{channel.label}</span>
      <strong>{channel.version}</strong>
      <p>{channel.description}</p>
      <a className={channel.id === "experimental"
        ? "button primary-button large"
        : "button ghost-button large"} href={channel.downloadUrl}>
        <DownloadSimple size={20} />
        下载 {channel.label}
      </a>
    </article>
  ))}
</div>
```

Use existing `--surface`, `--line-strong`, `--radius-*`, `--accent*`, `--text`, and `--muted-strong` variables. Do not introduce a new color system.

- [ ] **Step 5: Test, build and commit**

Run:

```powershell
py -m pytest tests/demo/test_demo_download_channels.py tests/demo/test_demo_sanitization.py -v
Set-Location 演示web2
npm run build
```

Expected: PASS, build exit 0, and both version strings appear in `dist` assets.

```powershell
git add 演示web2/src/releaseChannels.ts 演示web2/src/App.tsx 演示web2/src/styles.css tests/demo/test_demo_download_channels.py
git commit -m "feat: show stable and experimental demo downloads"
```

---

### Task 2: Validate Download Assets During Pages Build

**Files:**
- Create: `scripts/release/verify_demo_downloads.py`
- Modify: `tests/demo/test_demo_download_channels.py`
- Modify: `.github/workflows/pages-demo-web2.yml`

**Interfaces:**
- Produces: `python scripts/release/verify_demo_downloads.py [--live]`.
- Consumes: URLs exported in `releaseChannels.ts`.

- [ ] **Step 1: Add parser and live-check unit tests**

```python
def test_verifier_extracts_two_https_release_assets():
    urls = load_download_urls(RELEASE_CHANNELS)
    assert len(urls) == 2
    assert all(url.startswith("https://github.com/") for url in urls)
    assert all("/releases/download/" in url for url in urls)

def test_live_check_accepts_redirect_then_200(monkeypatch):
    responses = iter([FakeResponse(302, location="https://objects.example/asset"),
                      FakeResponse(200)])
    monkeypatch.setattr(download_verifier, "open_request", lambda request: next(responses))
    assert download_verifier.verify_url("https://github.com/release.exe") is None
```

- [ ] **Step 2: Run tests and verify missing script failure**

Run: `py -m pytest tests/demo/test_demo_download_channels.py -v`

Expected: FAIL importing `scripts.release.verify_demo_downloads`.

- [ ] **Step 3: Implement static and live validation**

```python
def load_download_urls(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    urls = re.findall(r'downloadUrl:\s*"([^"]+)"', text)
    if len(urls) != 2 or len(set(urls)) != 2:
        raise RuntimeError("expected exactly two distinct demo download URLs")
    return urls

def verify_url(url: str) -> None:
    request = urllib.request.Request(url, method="HEAD",
        headers={"User-Agent": "lang-drill-demo-link-check/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}: {url}")
    except urllib.error.HTTPError as exc:
        if exc.code not in {405, 403}:
            raise
        fallback = urllib.request.Request(url,
            headers={"Range": "bytes=0-0",
                     "User-Agent": "lang-drill-demo-link-check/1"})
        with urllib.request.urlopen(fallback, timeout=30) as response:
            if response.status not in {200, 206}:
                raise RuntimeError(f"HTTP {response.status}: {url}")
```

Default mode performs static validation only; `--live` checks both assets and exits nonzero on failure.

- [ ] **Step 4: Add the Pages workflow gate**

Add after Python dependency installation:

```yaml
      - name: Verify demo download assets
        run: python scripts/release/verify_demo_downloads.py --live
```

Keep existing permissions and deployment steps unchanged.

- [ ] **Step 5: Run static tests and one live verification, then commit**

Run:

```powershell
py -m pytest tests/demo/test_demo_download_channels.py tests/demo/test_demo_sanitization.py -v
py scripts/release/verify_demo_downloads.py --live
```

Expected: both release asset checks print `OK` and exit 0.

```powershell
git add scripts/release/verify_demo_downloads.py tests/demo/test_demo_download_channels.py .github/workflows/pages-demo-web2.yml
git commit -m "ci: verify demo download assets"
```

---

### Task 3: Run the Integrated Automated L3 Suite

**Files:**
- Modify only code/tests required to resolve failures caused by this feature set.

**Interfaces:**
- Consumes: deliverables from all four plans.
- Produces: reproducible automated verification evidence for the task acceptance record.

- [ ] **Step 1: Run backend targeted suites**

Run:

```powershell
py -m pytest tests/test_resource_import_staging.py tests/test_knowledge_api.py tests/test_knowledge_retrieval.py tests/test_past_papers_api.py tests/test_past_paper_ingestion.py tests/test_past_paper_retrieval.py tests/test_embedding_settings.py tests/test_embedding_catalog.py tests/test_embedding_downloads.py tests/test_embedding_api.py tests/test_hybrid_retrieval.py tests/test_memory_presets.py tests/test_memory_api.py tests/test_memory_hooks.py tests/test_memory_retrieval.py -v
```

Expected: PASS.

- [ ] **Step 2: Run backend full regression**

Run: `py -m pytest -q`

Expected: all tests PASS. If an optional real model test is marked, the mark and reason must explicitly say that it is covered by the manual L3 step; missing base dependencies are failures, not skips.

- [ ] **Step 3: Run frontend focused and full suites**

Run:

```powershell
Set-Location frontend
npm test -- --run src/components/ResourceImportQueue.test.tsx src/features/knowledge/KnowledgeSettings.test.tsx src/features/pastPapers/PastPaperLibrary.test.tsx src/features/embeddings/EmbeddingSettings.test.tsx src/features/memory/MemorySettings.test.tsx
npm test
npm run build
```

Expected: all tests PASS and build exits 0.

- [ ] **Step 4: Run demo and release regression**

Run:

```powershell
Set-Location ..
py -m pytest tests/demo tests/release -v
Set-Location 演示web2
npm run build
```

Expected: PASS and demo build exits 0.

- [ ] **Step 5: Run static quality checks and commit only required fixes**

Run:

```powershell
Set-Location ..
py -m ruff check backend tests
git diff --check
git status --short
```

Expected: Ruff and whitespace checks PASS. Existing unrelated dirty desktop-script changes remain unstaged.

If a check fails, return to the owning task, modify only that task’s listed files, rerun its exact focused command, and use that task’s exact `git add` list before committing `fix: resolve resource rag memory regressions`.

---

### Task 4: Perform Manual L3 Acceptance on the Local Service

**Files:**
- Create: `doc/验收/任务/验收-2026-07-25-真题知识库RAG记忆重构.md`

**Interfaces:**
- Consumes: local frontend `http://127.0.0.1:5173` and backend health/API.
- Produces: exact pass/fail evidence, resource metrics and remaining risks.

- [ ] **Step 1: Start and health-check the real local service**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start-dev.ps1 -SkipInstall -NoBrowser
Invoke-WebRequest http://127.0.0.1:8000/docs -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:5173 -UseBasicParsing
```

Expected: both responses return HTTP 200. Open `http://127.0.0.1:5173`, not a demo URL.

- [ ] **Step 2: Verify staged imports**

Manual checks:

1. Drop one PDF and one screenshot into knowledge.
2. Drop one PDF and one screenshot into the true-paper library.
3. Confirm files appear locally before parse and no formal document count changes.
4. Parse each item; inspect text preview, diagnostics and domain metadata.
5. Edit title/year/language, confirm only selected items, and verify counts/assets update.
6. Force one unsupported/empty/failed file and verify other queue items remain usable.
7. Restart the app and verify confirmed items persist while expired/cancelled staging data does not appear.

Expected: every step matches the approved staged flow; no formal write occurs before confirmation.

- [ ] **Step 3: Verify RAG and the real Qwen model**

Manual checks:

1. Confirm initial mode is off and search reports FTS.
2. Search Hugging Face for `Qwen/Qwen3-Embedding-0.6B`.
3. Inspect license, revision, size, compatibility, target directory and disk availability.
4. Decline the first confirmation and verify no download starts.
5. Confirm download, record downloaded bytes and elapsed time, then explicitly enable it.
6. Record first-load time and process memory.
7. Decline the first reindex confirmation; verify indexes remain stale and search stays FTS.
8. Confirm reindex for knowledge, true papers and memory; verify hybrid mode.
9. Restart and verify selected model/revision/index status persists.
10. Break the local model directory or cloud endpoint and verify a visible FTS fallback.

Expected: Qwen loads with remote code disabled, identity matches index state, and failures never claim hybrid success.

- [ ] **Step 4: Verify memory and demo channels**

Manual checks:

1. Confirm standard is selected and reports configured 10,000 tokens.
2. Switch to economy and deep; confirm effective budget and 30% reserve display.
3. Disable each of 关于我、学习记录、使用习惯 and verify mapped items are excluded.
4. Cancel group clear once, then confirm it and verify only that group is archived.
5. Expand a memory item and inspect evidence, source, update time and revision history.
6. Open the built/demo site and verify stable `v0.1.2`, experimental `v1.0.0-alpha.2`, and online experience labelled experimental.
7. Click both download links and verify the expected installer filenames.

Expected: all behaviors and labels match the specification.

- [ ] **Step 5: Record exact acceptance outcome**

The task record must include:

- involved modules;
- L3 level;
- each automated command with pass counts;
- each manual step with pass/fail;
- Qwen size, download time, first-load time and memory;
- fallback and restart results;
- secret scan result;
- problems/risks;
- final conclusion exactly one of `通过`, `有条件通过`, `不通过`, `阻塞`, `未执行`.

Do not merge `main` for `有条件通过` without explicit user authorization.

---

### Task 5: Update Long-Lived Acceptance, Progress, and Archive Records

**Files:**
- Modify: `doc/验收/模块/验收-用户知识库与RAG.md`
- Modify: `doc/验收/模块/验收-分层记忆.md`
- Modify: `doc/验收/模块/验收-真实真题蒸馏与自适应调度.md`
- Move after pass: `doc/验收/任务/验收-2026-07-25-真题知识库RAG记忆重构.md` to `doc/验收/归档/2026-07-25/`
- Modify: `doc/进展记录/2026-07-25.md`
- Move after pass: approved spec and four plans to `doc/归档/2026-07-25/`

**Interfaces:**
- Produces: project-local maintenance evidence required by `AGENTS.md`.

- [ ] **Step 1: Update module acceptance scenarios**

Add verifiable scenarios:

- Knowledge: multi-file drop, preview-before-confirm, screenshots, FTS/RAG modes, model management, stale/reindex/fallback.
- True papers: local files/screenshots, preview metadata, explicit confirmation, remote sync regression.
- Memory: three modes, 30% reserve, three groups, provenance and confirmed clear.

Each scenario includes steps, expected result, automated command and manual check.

- [ ] **Step 2: Update the progress record once**

Append one minute-precision period with:

- completed implementation;
- file list and purpose;
- tests and acceptance conclusion;
- errors and resolution;
- model storage path and any out-of-workspace writes;
- rollback commit/branch.

- [ ] **Step 3: Archive only after successful implementation**

Move:

- `docs/superpowers/specs/2026-07-25-resource-import-rag-memory-design.md`
- all five files under `docs/superpowers/plans/` for this feature
- the passed task acceptance record

to their required `doc/归档/2026-07-25/` and `doc/验收/归档/2026-07-25/` locations. Remove the tracked active copies in the same commit so stale plans do not remain.

- [ ] **Step 4: Verify documentation consistency**

Run:

```powershell
rg -n "v0\\.1\\.2|v1\\.0\\.0-alpha\\.2|5,000|10,000|30%|Qwen/Qwen3-Embedding-0.6B|trust_remote_code" doc docs 演示web2/src
git diff --check
```

Expected: values are consistent; no active plan remains after archival.

- [ ] **Step 5: Commit the tracked archive changes**

Because `doc/` is intentionally Git-ignored, stage only removal of the tracked active spec/plans; keep local acceptance/progress archives untracked unless repository policy changes.

```powershell
git add -u docs/superpowers
git commit -m "docs: archive completed resource rag memory plans"
```

Then invoke `superpowers:requesting-code-review`, address findings, rerun the L3 suite, and use `superpowers:finishing-a-development-branch` for the verified merge/cleanup flow.
