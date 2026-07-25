# Embedding Runtime and RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace environment-only embeddings with an explicit off/local/cloud configuration, safe Hugging Face discovery and download, and identity-bound hybrid retrieval for knowledge, true papers, and memory.

**Architecture:** A shared embeddings package owns settings, provider creation, model discovery, download jobs, health probes, and index identity. Existing knowledge, true-paper, and memory retrieval continue to own domain ranking while consuming one shared runtime; FTS5 remains the unconditional fallback.

**Tech Stack:** Python 3.11, FastAPI, SQLite, httpx, huggingface-hub, optional sentence-transformers, React 19, TypeScript, Vitest.

## Global Constraints

- Default mode is `off`.
- No model/runtime download, cloud call, activation, or reindex without explicit user action.
- Default recommendation is `Qwen/Qwen3-Embedding-0.6B`.
- `trust_remote_code=False` is not configurable.
- Search may show any Hugging Face model, but enablement requires feature-extraction compatibility, supported files, a visible license, and a successful fixed-dimension health probe.
- Identity is `provider + model_id + revision + dimensions`; vectors with another identity are never read.
- Download target defaults to `<LANGDRILL_USER_DATA_DIR>/models/embeddings`, not C drive unless the configured user data path is on C.
- Secrets live only in `.env`; API responses expose booleans and masked previews.
- FTS5 remains usable during downloads, index rebuilds, provider failures, and restarts.

## File Structure

- Create `backend/langdrill_agent/embeddings/models.py`: settings, identity, catalog and job contracts.
- Create `backend/langdrill_agent/embeddings/settings.py`: SQLite nonsecret settings and `.env` secret ledger.
- Create `backend/langdrill_agent/embeddings/providers.py`: local, Hugging Face cloud, OpenAI-compatible providers.
- Create `backend/langdrill_agent/embeddings/catalog.py`: recommendations, HF API search and compatibility assessment.
- Create `backend/langdrill_agent/embeddings/downloads.py`: download jobs, resume and cancellation checks.
- Create `backend/langdrill_agent/embeddings/runtime_install.py`: confirmed fixed-package local runtime installation.
- Create `backend/langdrill_agent/embeddings/runtime.py`: lazy provider cache, health probes and unload.
- Create `backend/langdrill_agent/embeddings/indexing.py`: index-state and confirmed rebuild orchestration.
- Create `backend/langdrill_agent/routers/embeddings.py`: settings, search, download, health and reindex APIs.
- Create `backend/langdrill_agent/migrations/007_embedding_runtime.sql`: download jobs and index state.
- Modify `backend/langdrill_agent/knowledge/embeddings.py`: retain math/index helpers, consume shared contracts.
- Modify knowledge, past-paper, and memory retrieval/context/router call sites.
- Modify `backend/langdrill_agent/api.py`, `pyproject.toml`, `.env.example`.
- Create `frontend/src/features/embeddings/{types.ts,api.ts,EmbeddingSettings.tsx,EmbeddingSettings.test.tsx}`.
- Modify `frontend/src/features/knowledge/KnowledgeSettings.tsx` and `frontend/src/styles.css`.
- Create `tests/test_embedding_settings.py`, `tests/test_embedding_catalog.py`, `tests/test_embedding_downloads.py`, `tests/test_embedding_api.py`.
- Modify `tests/test_hybrid_retrieval.py`, `tests/test_knowledge_retrieval.py`, `tests/test_past_paper_retrieval.py`, `tests/test_memory_retrieval.py`.

---

### Task 1: Store Explicit Embedding Settings and Identity

**Files:**
- Create: `backend/langdrill_agent/migrations/007_embedding_runtime.sql`
- Create: `backend/langdrill_agent/embeddings/__init__.py`
- Create: `backend/langdrill_agent/embeddings/models.py`
- Create: `backend/langdrill_agent/embeddings/settings.py`
- Modify: `.env.example`
- Modify: `backend/langdrill_agent/data_paths.py`
- Test: `tests/test_embedding_settings.py`

**Interfaces:**
- Produces: `EmbeddingMode`, `EmbeddingIdentity.key`, `EmbeddingSettings`, `EmbeddingSettingsService.get/save`.
- Consumes: `app_settings`, `config.env_file_path`, `config.load_settings`.

- [ ] **Step 1: Write default, secret, and identity tests**

```python
def test_embedding_settings_default_to_off(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("LANGDRILL_USER_DATA_DIR", str(tmp_path))
    settings = EmbeddingSettingsService(conn).get()
    assert settings.mode == "off"
    assert settings.model_id == ""
    assert settings.model_dir == str(tmp_path / "models" / "embeddings")
    assert settings.api_key_configured is False

def test_identity_changes_with_revision_or_dimensions():
    first = EmbeddingIdentity(provider="local", model_id="Qwen/Qwen3-Embedding-0.6B",
                              revision="abc", dimensions=1024)
    second = first.model_copy(update={"revision": "def"})
    third = first.model_copy(update={"dimensions": 768})
    assert len({first.key, second.key, third.key}) == 3

def test_save_writes_secret_only_to_env(conn, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setenv("LANGDRILL_ENV_FILE", str(env_file))
    saved = EmbeddingSettingsService(conn).save(
        EmbeddingSettingsPatch(mode="huggingface_cloud",
            model_id="sentence-transformers/all-MiniLM-L6-v2",
            api_key="hf_secret_value")
    )
    assert saved.api_key_configured is True
    assert "hf_secret_value" not in dumps(saved.model_dump())
    assert "hf_secret_value" in env_file.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests and verify missing-package failures**

Run: `py -m pytest tests/test_embedding_settings.py -v`

Expected: FAIL during import of `langdrill_agent.embeddings`.

- [ ] **Step 3: Add schema and exact contracts**

```sql
CREATE TABLE IF NOT EXISTS embedding_download_jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'model' CHECK(kind IN ('model', 'runtime')),
  model_id TEXT NOT NULL,
  revision TEXT NOT NULL,
  target_dir TEXT NOT NULL,
  status TEXT NOT NULL,
  files_total INTEGER NOT NULL DEFAULT 0,
  files_completed INTEGER NOT NULL DEFAULT 0,
  bytes_downloaded INTEGER NOT NULL DEFAULT 0,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  error_code TEXT NOT NULL DEFAULT '',
  error_detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS embedding_index_state (
  target TEXT PRIMARY KEY CHECK(target IN ('knowledge', 'past_papers', 'memory')),
  identity_key TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'fts_only',
  indexed_count INTEGER NOT NULL DEFAULT 0,
  error_code TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

```python
import json

EmbeddingMode = Literal["off", "local", "huggingface_cloud", "openai_compatible"]

class EmbeddingIdentity(BaseModel):
    provider: str
    model_id: str
    revision: str
    dimensions: int = Field(ge=1)

    @property
    def key(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

class EmbeddingSettings(BaseModel):
    mode: EmbeddingMode = "off"
    model_id: str = ""
    revision: str = ""
    dimensions: int = 0
    model_dir: str = ""
    base_url: str = ""
    api_key_configured: bool = False
    enabled_identity: EmbeddingIdentity | None = None

class EmbeddingSettingsPatch(BaseModel):
    mode: EmbeddingMode | None = None
    model_id: str | None = None
    revision: str | None = None
    dimensions: int | None = Field(default=None, ge=0)
    model_dir: str | None = None
    base_url: str | None = None
    api_key: str | None = None
```

- [ ] **Step 4: Implement settings and the secret ledger**

Store nonsecret JSON at `app_settings['embeddings.settings']`. Store only:

- `LANGDRILL_EMBEDDING_HF_TOKEN`
- `LANGDRILL_EMBEDDING_CLOUD_API_KEY`

in `env_file_path()`. Return `api_key_configured` and a four-character suffix preview, never the value.

```python
def update_env_value(path: Path, key: str, value: str) -> None:
    current: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                current_key, current_value = line.split("=", 1)
                current[current_key.strip()] = current_value
    if value:
        current[key] = value
    else:
        current.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"{item_key}={item_value}" for item_key, item_value in current.items()) + "\n",
        encoding="utf-8",
    )
```

```python
def save(self, patch: EmbeddingSettingsPatch) -> EmbeddingSettings:
    current = self.get()
    payload = current.model_copy(update=patch.model_dump(
        exclude={"api_key"}, exclude_none=True
    ))
    if patch.api_key is not None:
        key = ("LANGDRILL_EMBEDDING_HF_TOKEN"
               if payload.mode == "huggingface_cloud"
               else "LANGDRILL_EMBEDDING_CLOUD_API_KEY")
        update_env_value(env_file_path(), key, normalize_api_key(patch.api_key))
    self.conn.execute(
        """INSERT INTO app_settings(key,value_json,updated_at)
           VALUES ('embeddings.settings',?,CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
             updated_at=CURRENT_TIMESTAMP""",
        (dumps(payload.model_dump(exclude={"api_key_configured"})),),
    )
    return self.get()
```

Remove the deprecated `LANGDRILL_KNOWLEDGE_EMBEDDING_*` example block, add the two new keys to `.env.example` with placeholder values, and add them to `DataPathService._write_env` ordering so unrelated settings writes preserve them. Existing real `.env` keys are not deleted automatically; the new runtime ignores them until the user explicitly saves a new mode.

- [ ] **Step 5: Run tests and commit**

Run: `py -m pytest tests/test_embedding_settings.py tests/test_migration_runner.py tests/test_data_paths_knowledge.py -v`

Expected: PASS and no secret appears in test response payloads.

```powershell
git add backend/langdrill_agent/migrations/007_embedding_runtime.sql backend/langdrill_agent/embeddings backend/langdrill_agent/data_paths.py .env.example tests/test_embedding_settings.py
git commit -m "feat: add explicit embedding settings and identity"
```

---

### Task 2: Discover and Download Compatible Hugging Face Models

**Files:**
- Create: `backend/langdrill_agent/embeddings/catalog.py`
- Create: `backend/langdrill_agent/embeddings/downloads.py`
- Modify: `backend/langdrill_agent/embeddings/models.py`
- Modify: `pyproject.toml`
- Test: `tests/test_embedding_catalog.py`
- Test: `tests/test_embedding_downloads.py`

**Interfaces:**
- Produces: `EmbeddingModelCatalog.search/detail/recommendations`.
- Produces: `EmbeddingDownloadService.create/run/cancel/status`.
- Produces: `EmbeddingRuntimeInstallService.create/run/status`.
- Consumes: Hugging Face model API and `huggingface_hub.hf_hub_download`.

- [ ] **Step 1: Add catalog compatibility tests**

```python
def test_recommendations_start_with_qwen(fake_hf_client):
    catalog = EmbeddingModelCatalog(client=fake_hf_client)
    assert catalog.recommendations()[0].model_id == "Qwen/Qwen3-Embedding-0.6B"

def test_remote_code_only_model_cannot_be_enabled(fake_hf_client):
    fake_hf_client.model_info.return_value = model_info(
        model_id="unsafe/model", pipeline_tag="feature-extraction",
        siblings=["config.json", "modeling_custom.py"],
        library_name="transformers", license="apache-2.0",
    )
    detail = EmbeddingModelCatalog(client=fake_hf_client).detail("unsafe/model")
    assert detail.compatible is False
    assert "remote_code" in detail.blockers

def test_search_is_not_limited_to_recommendations(fake_hf_client):
    fake_hf_client.list_models.return_value = [model_info(model_id="org/custom-embed")]
    items = EmbeddingModelCatalog(client=fake_hf_client).search("custom")
    assert items[0].model_id == "org/custom-embed"
```

- [ ] **Step 2: Add resumable download and cancellation tests**

```python
def test_download_reuses_cached_files(conn, tmp_path, fake_hf_client):
    service = EmbeddingDownloadService(conn, hub=fake_hf_client)
    job = service.create("Qwen/Qwen3-Embedding-0.6B", "rev123", tmp_path, confirmed=True)
    service.run(job.id)
    assert service.status(job.id).status == "completed"
    assert fake_hf_client.hf_hub_download.call_count == 3

def test_cancel_is_checked_between_files(conn, tmp_path, fake_hf_client):
    service = EmbeddingDownloadService(conn, hub=fake_hf_client)
    job = service.create("org/model", "rev123", tmp_path, confirmed=True)
    service.cancel(job.id)
    service.run(job.id)
    assert service.status(job.id).status == "cancelled"
    fake_hf_client.hf_hub_download.assert_not_called()

def test_runtime_install_requires_confirmation(conn):
    service = EmbeddingRuntimeInstallService(conn, runner=Mock())
    with pytest.raises(ValueError, match="EMBEDDING_RUNTIME_INSTALL_CONFIRMATION_REQUIRED"):
        service.create(confirmed=False)

def test_runtime_install_uses_fixed_packages_only(conn, fake_runner):
    service = EmbeddingRuntimeInstallService(conn, runner=fake_runner)
    job = service.create(confirmed=True)
    service.run(job.id)
    command = fake_runner.call_args.args[0]
    assert command == [
        sys.executable, "-m", "pip", "install",
        "sentence-transformers>=5.0,<6",
        "safetensors>=0.5,<1",
    ]
```

- [ ] **Step 3: Run tests and verify missing implementations**

Run: `py -m pytest tests/test_embedding_catalog.py tests/test_embedding_downloads.py -v`

Expected: FAIL with missing catalog/download/runtime-install classes.

- [ ] **Step 4: Implement catalog validation and recommendation metadata**

Add base dependency `huggingface-hub>=0.34,<2` and optional group:

```toml
embeddings-local = [
  "sentence-transformers>=5.0,<6",
  "safetensors>=0.5,<1"
]
```

Use `HfApi.list_models(search=query, pipeline_tag="feature-extraction", sort="downloads", direction=-1, limit=20, full=True)`. Fetch detail for enablement and require:

```python
SUPPORTED_WEIGHT_SUFFIXES = {".safetensors"}
SUPPORTED_LIBRARIES = {"sentence-transformers", "transformers"}

compatible = (
    info.pipeline_tag in {"feature-extraction", "sentence-similarity"}
    and info.library_name in SUPPORTED_LIBRARIES
    and bool(license_name)
    and any(path.endswith(".safetensors") for path in sibling_names)
    and not any(path.endswith(".py") and "modeling_" in path for path in sibling_names)
)
```

Return model ID, revision SHA, license, library, pipeline tag, downloads, likes, total sibling size, compatibility, blockers, and recommended flag.

- [ ] **Step 5: Implement explicit confirmed downloads and commit**

```python
def create(self, model_id: str, revision: str, model_root: Path,
           *, confirmed: bool) -> EmbeddingDownloadJob:
    if not confirmed:
        raise ValueError("EMBEDDING_DOWNLOAD_CONFIRMATION_REQUIRED")
    detail = self.catalog.detail(model_id, revision=revision)
    if not detail.compatible:
        raise ValueError("EMBEDDING_MODEL_INCOMPATIBLE")
    required = detail.size_bytes + max(detail.size_bytes // 10, 256 * 1024 * 1024)
    if shutil.disk_usage(model_root.parent).free < required:
        raise ValueError("EMBEDDING_DISK_SPACE_INSUFFICIENT")
    return self.repository.create_job(
        model_id=model_id, revision=detail.revision,
        target_dir=str(model_root / safe_model_dir(model_id) / detail.revision),
        files_total=len(detail.download_files),
    )
```

`run` downloads only the validated file list with `repo_type="model"`, `revision=detail.revision`, and `local_dir=Path(job.target_dir)`, and resumes through Hugging Face cache semantics. Check `cancel_requested` between files and sanitize errors.

`EmbeddingRuntimeInstallService` creates a `kind='runtime'` job only when `confirmed=True`. It runs the fixed package list shown in the test through `subprocess.run(..., check=False, capture_output=True, text=True, timeout=1800)`. No package name, index URL, extra pip argument, or shell fragment comes from the request. Failure records a sanitized stderr excerpt and leaves RAG off.

Run: `py -m pytest tests/test_embedding_catalog.py tests/test_embedding_downloads.py -v`

Expected: PASS.

```powershell
git add backend/langdrill_agent/embeddings/catalog.py backend/langdrill_agent/embeddings/downloads.py backend/langdrill_agent/embeddings/runtime_install.py backend/langdrill_agent/embeddings/models.py pyproject.toml tests/test_embedding_catalog.py tests/test_embedding_downloads.py
git commit -m "feat: add safe hugging face model discovery and downloads"
```

---

### Task 3: Build Lazy Providers and Identity-Bound Hybrid Retrieval

**Files:**
- Create: `backend/langdrill_agent/embeddings/providers.py`
- Create: `backend/langdrill_agent/embeddings/runtime.py`
- Create: `backend/langdrill_agent/embeddings/indexing.py`
- Modify: `backend/langdrill_agent/knowledge/embeddings.py`
- Modify: `backend/langdrill_agent/knowledge/retrieval.py`
- Modify: `backend/langdrill_agent/knowledge/context.py`
- Modify: `backend/langdrill_agent/past_papers/embeddings.py`
- Modify: `backend/langdrill_agent/past_papers/retrieval.py`
- Modify: `backend/langdrill_agent/memory/retrieval.py`
- Modify: `backend/langdrill_agent/memory/context.py`
- Modify: `backend/langdrill_agent/routers/knowledge.py`
- Modify: `backend/langdrill_agent/routers/past_papers.py`
- Modify: `backend/langdrill_agent/routers/memory.py`
- Modify: `tests/test_hybrid_retrieval.py`
- Modify: `tests/test_knowledge_retrieval.py`
- Modify: `tests/test_past_paper_retrieval.py`
- Modify: `tests/test_memory_retrieval.py`

**Interfaces:**
- Produces: `EmbeddingRuntime.current() -> tuple[EmbeddingSettings, EmbeddingProvider | None]`.
- Produces: `EmbeddingRuntime.health_probe(settings) -> EmbeddingIdentity`.
- Produces: `EmbeddingIndexCoordinator.reindex(targets, confirmed)`.

- [ ] **Step 1: Write provider and identity isolation tests**

```python
def test_local_provider_never_enables_remote_code(fake_sentence_transformer):
    provider = LocalSentenceTransformerProvider(
        model_path=Path("model"),
        identity=EmbeddingIdentity(
            provider="local", model_id="org/model", revision="abc", dimensions=384,
        ),
        factory=fake_sentence_transformer,
    )
    provider.embed(["hello"])
    fake_sentence_transformer.assert_called_once_with(
        str(Path("model")), trust_remote_code=False, local_files_only=True,
    )

def test_retrieval_ignores_vectors_from_previous_revision(conn, chunk):
    old = EmbeddingIdentity(provider="local", model_id="org/model",
                            revision="old", dimensions=3)
    current = old.model_copy(update={"revision": "new"})
    insert_embedding(conn, chunk, identity=old, vector=[1.0, 0.0, 0.0])
    result = KnowledgeRetrievalService(
        conn, embedding_provider=FakeProvider(current, [1.0, 0.0, 0.0]),
        embedding_config=EmbeddingConfig.from_identity(current),
    ).search_result(RetrievalQuery(text="semantic only"))
    assert result.mode == "fts"
```

- [ ] **Step 2: Write fallback and confirmed reindex tests**

```python
def test_provider_error_returns_fts_results(conn, indexed_chunk):
    result = KnowledgeRetrievalService(
        conn, embedding_provider=FailingProvider(),
        embedding_config=EmbeddingConfig(enabled=True),
    ).search_result(RetrievalQuery(text="consecutive"))
    assert result.mode == "fts"
    assert result.items

def test_reindex_requires_confirmation(conn):
    coordinator = EmbeddingIndexCoordinator(conn, runtime=FakeRuntime())
    with pytest.raises(ValueError, match="EMBEDDING_REINDEX_CONFIRMATION_REQUIRED"):
        coordinator.reindex(["knowledge"], confirmed=False)
```

- [ ] **Step 3: Run retrieval tests and verify failures**

Run: `py -m pytest tests/test_hybrid_retrieval.py tests/test_knowledge_retrieval.py tests/test_past_paper_retrieval.py tests/test_memory_retrieval.py -v`

Expected: FAIL because current providers do not include revision/dimensions in identity and local provider is absent.

- [ ] **Step 4: Implement providers and lazy runtime**

```python
class LocalSentenceTransformerProvider:
    def __init__(self, *, model_path: Path, identity: EmbeddingIdentity,
                 factory: Callable[..., Any] | None = None) -> None:
        self.model_path = model_path
        self.identity = identity
        self._factory = factory
        self._model = None

    def _load(self):
        if self._model is None:
            factory = self._factory
            if factory is None:
                from sentence_transformers import SentenceTransformer
                factory = SentenceTransformer
            self._model = factory(
                str(self.model_path), trust_remote_code=False, local_files_only=True,
            )
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        rows = self._load().encode(texts, normalize_embeddings=True)
        return [[float(value) for value in row] for row in rows]
```

Add this constructor to the existing `EmbeddingConfig` so domain indexers consume the identity without duplicating fields:

```python
@classmethod
def from_identity(cls, identity: EmbeddingIdentity, *, enabled: bool = True) -> "EmbeddingConfig":
    return cls(
        provider=identity.key,
        model=identity.model_id,
        dimensions=identity.dimensions,
        enabled=enabled,
    )
```

Implement:

- `HuggingFaceInferenceEmbeddingProvider` using the pinned model ID and HF token.
- `OpenAICompatibleEmbeddingProvider` using `/embeddings`.
- `EmbeddingRuntime` with a lock and one cached local model identity; switching identity unloads the prior model and calls `gc.collect()`.
- `health_probe` embeds `["Lang Drill embedding health probe"]`, requires one nonempty finite vector, and returns the measured dimensions.

- [ ] **Step 5: Bind every vector query to the full identity and commit**

Change `EmbeddingProvider.identity` from `str` to `EmbeddingIdentity`; write `identity.key` into vector-table `provider`, keep `model_id` in `model`, and validate dimensions. Every semantic query filters `e.provider = current_identity.key`, `e.model = current_identity.model_id`, and matching content hash.

`EmbeddingIndexCoordinator.reindex`:

- requires `confirmed=True`;
- marks each target `rebuilding`;
- rebuilds knowledge chunks, true-paper questions, or active memory items;
- records identity key and indexed count only after the target succeeds;
- records `failed` without deleting FTS rows;
- returns per-target results so partial failures remain visible.

Run:

`py -m pytest tests/test_hybrid_retrieval.py tests/test_knowledge_retrieval.py tests/test_past_paper_retrieval.py tests/test_memory_retrieval.py tests/test_knowledge_api.py tests/test_past_papers_api.py tests/test_memory_api.py -v`

Expected: PASS; failure providers return `mode="fts"`.

```powershell
git add backend/langdrill_agent/embeddings/providers.py backend/langdrill_agent/embeddings/runtime.py backend/langdrill_agent/embeddings/indexing.py backend/langdrill_agent/knowledge backend/langdrill_agent/past_papers backend/langdrill_agent/memory backend/langdrill_agent/routers tests/test_hybrid_retrieval.py tests/test_knowledge_retrieval.py tests/test_past_paper_retrieval.py tests/test_memory_retrieval.py
git commit -m "feat: add identity bound embedding runtime and rag"
```

---

### Task 4: Expose Model Management APIs and UI

**Files:**
- Create: `backend/langdrill_agent/routers/embeddings.py`
- Modify: `backend/langdrill_agent/api.py`
- Create: `tests/test_embedding_api.py`
- Create: `frontend/src/features/embeddings/types.ts`
- Create: `frontend/src/features/embeddings/api.ts`
- Create: `frontend/src/features/embeddings/EmbeddingSettings.tsx`
- Create: `frontend/src/features/embeddings/EmbeddingSettings.test.tsx`
- Modify: `frontend/src/features/knowledge/KnowledgeSettings.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Produces: `/api/embeddings/status`, `/settings`, `/test`, `/models`, `/downloads`, `/downloads/{id}`, `/runtime/install`, `/reindex`.
- Produces: `EmbeddingSettings` panel inside the existing knowledge page.

- [ ] **Step 1: Add API tests for default-off and explicit actions**

```python
def test_status_defaults_to_fts_only(client):
    payload = client.get("/api/embeddings/status").json()
    assert payload["settings"]["mode"] == "off"
    assert payload["effective_mode"] == "fts"
    assert payload["runtime"]["loaded"] is False

def test_download_requires_confirmation(client):
    response = client.post("/api/embeddings/downloads", json={
        "model_id": "Qwen/Qwen3-Embedding-0.6B",
        "revision": "abc", "confirmed": False,
    })
    assert response.status_code == 400

def test_runtime_install_requires_confirmation(client):
    response = client.post(
        "/api/embeddings/runtime/install", json={"confirmed": False},
    )
    assert response.status_code == 400

def test_switch_marks_indexes_stale_without_reindex(client):
    response = client.post("/api/embeddings/settings", json={
        "mode": "local", "model_id": "Qwen/Qwen3-Embedding-0.6B",
        "revision": "abc", "dimensions": 1024,
    })
    assert response.status_code == 200
    assert all(item["status"] == "stale" for item in response.json()["indexes"])
```

- [ ] **Step 2: Add frontend tests for three modes and confirmations**

```tsx
it("shows FTS5 and performs no download while off", async () => {
  const api = createApi({ mode: "off" });
  render(<EmbeddingSettings api={api} />);
  expect(await screen.findByText("FTS5 全文检索")).toBeTruthy();
  expect(api.download).not.toHaveBeenCalled();
});

it("requires confirmation before downloading a recommended model", async () => {
  const api = createApi({ mode: "local" });
  vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<EmbeddingSettings api={api} />);
  fireEvent.click(await screen.findByRole("button", { name: /下载 Qwen/ }));
  expect(api.download).not.toHaveBeenCalled();
});

it("requires confirmation before rebuilding stale indexes", async () => {
  const api = createApi({ indexes: [{ target: "knowledge", status: "stale" }] });
  vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<EmbeddingSettings api={api} />);
  fireEvent.click(await screen.findByRole("button", { name: "重新建立向量索引" }));
  expect(api.reindex).not.toHaveBeenCalled();
});
```

- [ ] **Step 3: Run tests and verify missing router/component failures**

Run:

```powershell
py -m pytest tests/test_embedding_api.py -v
Set-Location frontend
npm test -- --run src/features/embeddings/EmbeddingSettings.test.tsx
```

Expected: backend 404 and frontend missing-component failures.

- [ ] **Step 4: Implement API endpoints with sanitized responses**

```python
class DownloadRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=240)
    revision: str = Field(min_length=1, max_length=120)
    target_dir: str = ""
    confirmed: bool = False

class RuntimeInstallRequest(BaseModel):
    confirmed: bool = False

class ReindexRequest(BaseModel):
    targets: list[Literal["knowledge", "past_papers", "memory"]]
    confirmed: bool = False

def default_model_dir() -> Path:
    return load_settings().user_data_dir / "models" / "embeddings"

def run_download_job(job_id: str) -> None:
    init_db()
    with transaction() as conn:
        EmbeddingDownloadService(conn).run(job_id)

def run_runtime_install_job(job_id: str) -> None:
    init_db()
    with transaction() as conn:
        EmbeddingRuntimeInstallService(conn).run(job_id)

@router.get("/status")
def status() -> dict:
    with transaction() as conn:
        settings = EmbeddingSettingsService(conn).get()
        indexes = EmbeddingIndexCoordinator(conn).status()
        runtime = EmbeddingRuntime(conn).status()
        return {
            "settings": settings.model_dump(mode="json"),
            "effective_mode": (
                "hybrid"
                if settings.enabled_identity is not None and runtime["healthy"]
                else "fts"
            ),
            "runtime": runtime,
            "indexes": indexes,
        }

@router.post("/downloads", status_code=202)
def start_download(request: DownloadRequest, background: BackgroundTasks) -> dict:
    with transaction() as conn:
        job = EmbeddingDownloadService(conn).create(
            request.model_id, request.revision,
            Path(request.target_dir) if request.target_dir else default_model_dir(),
            confirmed=request.confirmed,
        )
    background.add_task(run_download_job, job.id)
    return {"job": job.model_dump(mode="json")}

@router.post("/runtime/install", status_code=202)
def install_runtime(request: RuntimeInstallRequest, background: BackgroundTasks) -> dict:
    with transaction() as conn:
        job = EmbeddingRuntimeInstallService(conn).create(
            confirmed=request.confirmed,
        )
    background.add_task(run_runtime_install_job, job.id)
    return {"job": job.model_dump(mode="json")}

@router.post("/reindex", status_code=202)
def reindex(request: ReindexRequest) -> dict:
    with transaction() as conn:
        return EmbeddingIndexCoordinator(conn).reindex(
            request.targets, confirmed=request.confirmed,
        )
```

Search returns at most 20 items. Test/enable performs a health probe; settings cannot store an enabled identity before the probe succeeds. Cancellation updates `cancel_requested`. All exception details are sanitized and API keys are omitted.

- [ ] **Step 5: Implement the existing-style settings panel, test, build and commit**

The panel shows:

- three modes: 关闭、本地模型、云端模型;
- FTS5 fallback status;
- local runtime availability and an explicit confirmed install button when unavailable;
- verified recommendations headed by Qwen;
- Hugging Face search and result metadata;
- model directory and free-space preview;
- explicit download progress/cancel;
- explicit activation after health probe;
- stale indexes and confirmed rebuild;
- cloud base URL/token fields with masked configured state and a connection-test button;
- developer details collapsed in `<details>`.

Mount the panel within `KnowledgeSettings`; do not add a navigation item.

Run:

```powershell
py -m pytest tests/test_embedding_api.py tests/test_embedding_catalog.py tests/test_embedding_downloads.py -v
Set-Location frontend
npm test -- --run src/features/embeddings/EmbeddingSettings.test.tsx src/features/knowledge/KnowledgeSettings.test.tsx
npm run build
```

Expected: PASS and build exit 0.

```powershell
git add backend/langdrill_agent/api.py backend/langdrill_agent/routers/embeddings.py tests/test_embedding_api.py frontend/src/features/embeddings frontend/src/features/knowledge/KnowledgeSettings.tsx frontend/src/styles.css
git commit -m "feat: add user controlled embedding model settings"
```
