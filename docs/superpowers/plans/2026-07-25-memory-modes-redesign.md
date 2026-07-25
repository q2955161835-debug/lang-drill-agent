# Memory Modes Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace opaque low-budget memory controls with economy, standard, and deep modes plus three user-facing memory groups while preserving the existing evidence-backed memory engine.

**Architecture:** A memory policy adapter maps three user groups to the existing eight internal categories and resolves a safe recall budget from mode plus available context. Internal policy controls remain stored and available under a collapsed developer section; existing memory items, evidence, revisions, provider migration, export, and import remain compatible.

**Tech Stack:** Python 3.11, Pydantic, SQLite/FTS5, existing shared embedding runtime, React 19, TypeScript, Vitest.

## Global Constraints

- Economy mode is at most `5,000` memory tokens.
- Standard mode is at most `10,000` memory tokens and is the default.
- Deep mode has no fixed cap and uses at most `70%` of currently available context, reserving at least `30%`.
- When fewer than 5,000 tokens are safely available, context safety wins and the UI/API reports the effective lower budget.
- User groups are `about_me`, `learning_history`, and `usage_habits`.
- Existing internal categories remain in the database and exported records.
- Memory content remains derived reference data and cannot override authoritative profile, attempts, questions, or mastery data.
- Permanent purge and group clear require explicit confirmation.
- RAG remains governed by the shared embedding settings; memory does not get a second independent embedding provider.

## File Structure

- Create `backend/langdrill_agent/memory/presets.py`: modes, group mapping and budget policy.
- Modify `backend/langdrill_agent/memory/hooks.py`: new settings defaults and effective budget use.
- Modify `backend/langdrill_agent/memory/context.py`: shared embedding runtime and budget enforcement.
- Modify `backend/langdrill_agent/memory/retrieval.py`: ranking order remains relevant/quality/recency and observes resolved budget.
- Modify `backend/langdrill_agent/routers/memory.py`: simplified settings payload and confirmed group clear.
- Modify `backend/langdrill_agent/context.py`, `backend/langdrill_agent/api.py`, and `backend/langdrill_agent/agents.py`: pass available context instead of hard-coded 800/1200 budgets.
- Modify `frontend/src/features/memory/types.ts`, `api.ts`, `MemorySettings.tsx`, and test.
- Modify `frontend/src/styles.css`.
- Modify `tests/test_memory_hooks.py`, `tests/test_memory_api.py`, `tests/test_memory_retrieval.py`.
- Create `tests/test_memory_presets.py`.

---

### Task 1: Define Modes, Groups, and Safe Budget Resolution

**Files:**
- Create: `backend/langdrill_agent/memory/presets.py`
- Create: `tests/test_memory_presets.py`

**Interfaces:**
- Produces: `MemoryMode`, `MemoryGroup`, `MODE_LIMITS`, `GROUP_CATEGORIES`.
- Produces: `resolve_memory_budget(mode, available_context_tokens) -> MemoryBudget`.
- Produces: `categories_for_groups(group_enabled)`.
- Produces: `read_context_limit(conn)` and `intersect_categories(...)`.

- [ ] **Step 1: Write exact preset and reserve tests**

```python
@pytest.mark.parametrize(
    ("mode", "available", "expected"),
    [
        ("economy", 100_000, 5_000),
        ("standard", 100_000, 10_000),
        ("deep", 100_000, 70_000),
        ("deep", 8_000, 5_600),
        ("standard", 6_000, 4_200),
    ],
)
def test_resolve_memory_budget(mode, available, expected):
    budget = resolve_memory_budget(mode, available)
    assert budget.effective_tokens == expected
    assert budget.reserved_tokens >= math.ceil(available * 0.30)

def test_group_mapping_covers_internal_categories_once():
    flattened = [category for values in GROUP_CATEGORIES.values() for category in values]
    assert sorted(flattened) == sorted({
        "core", "semantic", "episodic", "procedural", "temporal",
        "preference", "profile", "learning_weakness",
    })
    assert len(flattened) == len(set(flattened))
```

- [ ] **Step 2: Run tests and verify missing module failure**

Run: `py -m pytest tests/test_memory_presets.py -v`

Expected: FAIL with missing `memory.presets`.

- [ ] **Step 3: Implement exact mappings**

```python
MemoryMode = Literal["economy", "standard", "deep"]
MemoryGroup = Literal["about_me", "learning_history", "usage_habits"]

MODE_LIMITS: dict[MemoryMode, int | None] = {
    "economy": 5_000,
    "standard": 10_000,
    "deep": None,
}

GROUP_CATEGORIES: dict[MemoryGroup, tuple[str, ...]] = {
    "about_me": ("core", "profile", "semantic"),
    "learning_history": ("episodic", "temporal", "learning_weakness"),
    "usage_habits": ("procedural", "preference"),
}

class MemoryBudget(BaseModel):
    mode: MemoryMode
    configured_limit: int | None
    available_context_tokens: int
    reserved_tokens: int
    effective_tokens: int
    constrained_by_context: bool
```

- [ ] **Step 4: Implement 30% reserve behavior**

```python
def resolve_memory_budget(mode: MemoryMode, available_context_tokens: int) -> MemoryBudget:
    available = max(0, int(available_context_tokens))
    reserved = math.ceil(available * 0.30)
    safe_memory = max(0, available - reserved)
    configured = MODE_LIMITS[mode]
    effective = safe_memory if configured is None else min(configured, safe_memory)
    return MemoryBudget(
        mode=mode,
        configured_limit=configured,
        available_context_tokens=available,
        reserved_tokens=reserved,
        effective_tokens=effective,
        constrained_by_context=configured is not None and effective < configured,
    )
```

`categories_for_groups` expands only enabled groups and returns categories in the mapping order.

```python
def read_context_limit(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value_json FROM app_settings WHERE key='context.settings'"
    ).fetchone()
    payload = loads(row["value_json"], {}) if row else {}
    return max(1_000, int(payload.get("max_tokens") or 1_000_000))

def intersect_categories(requested: list[str] | None, grouped: list[str],
                         internal_enabled: dict[str, bool]) -> list[str]:
    requested_set = set(requested or grouped)
    return [
        category for category in grouped
        if category in requested_set and internal_enabled.get(category, True)
    ]
```

- [ ] **Step 5: Run tests and commit**

Run: `py -m pytest tests/test_memory_presets.py -v`

Expected: PASS.

```powershell
git add backend/langdrill_agent/memory/presets.py tests/test_memory_presets.py
git commit -m "feat: define memory modes groups and budgets"
```

---

### Task 2: Apply Presets Across Memory Hooks and Context Callers

**Files:**
- Modify: `backend/langdrill_agent/memory/hooks.py`
- Modify: `backend/langdrill_agent/memory/context.py`
- Modify: `backend/langdrill_agent/memory/retrieval.py`
- Modify: `backend/langdrill_agent/context.py`
- Modify: `backend/langdrill_agent/api.py`
- Modify: `backend/langdrill_agent/agents.py`
- Modify: `tests/test_memory_hooks.py`
- Modify: `tests/test_memory_retrieval.py`
- Modify: `tests/test_runtime_learning_regression.py`

**Interfaces:**
- Changes: `MemoryHooks.recall(..., available_context_tokens: int | None = None)`.
- Produces: `MemoryContext.budget` with configured/effective/reserved values.
- Consumes: `EmbeddingRuntime.current()` from the RAG plan.

- [ ] **Step 1: Add settings migration and effective-budget tests**

```python
def test_legacy_settings_load_as_standard(conn):
    conn.execute(
        "INSERT INTO app_settings(key,value_json) VALUES ('memory.settings', ?)",
        (dumps({"core_token_budget": 400, "recall_token_budget": 1200}),),
    )
    settings = MemorySettingsService(conn).get()
    assert settings.mode == "standard"
    assert settings.group_enabled == {
        "about_me": True, "learning_history": True, "usage_habits": True,
    }

def test_recall_standard_uses_ten_thousand_when_available(conn, seeded_memories):
    context = MemoryHooks(conn).recall(
        "study preferences", scope="global", available_context_tokens=100_000,
    )
    assert context.budget.effective_tokens == 10_000
    assert context.budget.reserved_tokens == 30_000

def test_disabled_group_filters_internal_categories(conn, seeded_memories):
    MemorySettingsService(conn).save(
        MemorySettings(group_enabled={
            "about_me": False, "learning_history": True, "usage_habits": True,
        })
    )
    context = MemoryHooks(conn).recall(
        "profile", scope="global", available_context_tokens=100_000,
    )
    assert all(item.category not in {"core", "profile", "semantic"} for item in context.items)
```

- [ ] **Step 2: Run tests and verify old defaults fail**

Run: `py -m pytest tests/test_memory_hooks.py tests/test_memory_retrieval.py -v`

Expected: FAIL because `mode`, `group_enabled`, and `budget` are absent.

- [ ] **Step 3: Extend settings compatibly**

```python
class MemorySettings(BaseModel):
    enabled: bool = True
    capture_enabled: bool = True
    recall_enabled: bool = True
    mode: MemoryMode = "standard"
    group_enabled: dict[MemoryGroup, bool] = Field(default_factory=lambda: {
        "about_me": True,
        "learning_history": True,
        "usage_habits": True,
    })
    category_enabled: dict[str, bool] = Field(default_factory=default_internal_categories)
    write_mode: str = "balanced"
    learning_evidence_min: int = 3
    confidence_min: float = 0.70
    default_ttl_days: int = 365
    recall_top_k: int = 50
    embeddings_enabled: bool = True
    compaction_flush_enabled: bool = True
```

On load, default missing `mode` to standard and missing groups to enabled. Legacy `core_token_budget` and `recall_token_budget` values are accepted during loading but no longer control preset budgeting.

- [ ] **Step 4: Resolve available context and remove hard-coded low budgets**

```python
class MemoryContext(BaseModel):
    trust: str = "derived_memory"
    rules: list[str] = Field(default_factory=default_memory_rules)
    mode: str = "fts"
    items: list[RetrievedMemoryItem] = Field(default_factory=list)
    token_count: int = 0
    budget: MemoryBudget = Field(default_factory=lambda: MemoryBudget(
        mode="standard", configured_limit=10_000,
        available_context_tokens=0, reserved_tokens=0,
        effective_tokens=0, constrained_by_context=True,
    ))

def recall(self, text: str, *, scope: str, categories: list[str] | None = None,
           available_context_tokens: int | None = None) -> MemoryContext:
    settings = self.settings_service.get()
    available = (
        available_context_tokens
        if available_context_tokens is not None
        else read_context_limit(self.conn)
    )
    budget = resolve_memory_budget(settings.mode, available)
    enabled_categories = intersect_categories(
        categories,
        categories_for_groups(settings.group_enabled),
        settings.category_enabled,
    )
    query = MemoryRetrievalQuery(
        text=text.strip(), categories=enabled_categories, scope=scope,
        top_k=settings.recall_top_k,
        token_budget=max(1, budget.effective_tokens),
    )
    return MemoryContextAssembler(self.conn).build(
        query, budget=budget, embeddings_enabled=settings.embeddings_enabled,
    )
```

Increase `MemoryRetrievalQuery.token_budget` from `le=20_000` to `le=7_000_000`, matching the configured maximum context of 10,000,000 minus the 30% reserve. `MemoryContextAssembler.build` receives the resolved `MemoryBudget` and returns it unchanged in `MemoryContext.budget`.

At each session-aware call site calculate:

```python
usage = ContextService(conn).usage(session_id)
available = max(
    0,
    int(usage["context_limit"]) - int(usage["estimated_current_context"]),
)
```

Pass `available_context_tokens=available` and remove explicit `token_budget=800`/`1200` overrides in `api.py` and `agents.py`. In `ContextService.prompt_context`, reuse its already computed usage to avoid recursion.

- [ ] **Step 5: Use shared embeddings, test and commit**

Replace `embedding_runtime_from_env()` in memory context with `EmbeddingRuntime(conn).current()`. Retrieval ranking remains FTS/vector fusion plus confidence, importance, pinned state and recency; apply the resolved token budget last.

Run:

`py -m pytest tests/test_memory_hooks.py tests/test_memory_retrieval.py tests/test_runtime_learning_regression.py tests/test_agentic_chat_routing.py -v`

Expected: PASS; assertions confirm no caller injects an 800-token cap.

```powershell
git add backend/langdrill_agent/memory backend/langdrill_agent/context.py backend/langdrill_agent/api.py backend/langdrill_agent/agents.py tests/test_memory_hooks.py tests/test_memory_retrieval.py tests/test_runtime_learning_regression.py
git commit -m "feat: apply safe memory budgets across prompt contexts"
```

---

### Task 3: Expose Three Groups and Confirmed Group Clearing

**Files:**
- Modify: `backend/langdrill_agent/routers/memory.py`
- Modify: `backend/langdrill_agent/memory/repository.py`
- Modify: `tests/test_memory_api.py`

**Interfaces:**
- Produces: simplified settings and `effective_budget` in `/api/memory/status`.
- Produces: `POST /api/memory/groups/{group}/clear`.

- [ ] **Step 1: Add status and destructive-action tests**

```python
def test_status_exposes_mode_groups_and_effective_budget(client):
    payload = client.get("/api/memory/status").json()
    assert payload["settings"]["mode"] == "standard"
    assert payload["settings"]["group_enabled"]["about_me"] is True
    assert payload["effective_budget"]["configured_limit"] == 10_000
    assert payload["group_counts"].keys() == {
        "about_me", "learning_history", "usage_habits",
    }

def test_group_clear_requires_confirmation(client):
    response = client.post(
        "/api/memory/groups/learning_history/clear",
        json={"confirmed": False},
    )
    assert response.status_code == 400

def test_group_clear_archives_only_mapped_categories(client, seeded_memories):
    response = client.post(
        "/api/memory/groups/learning_history/clear",
        json={"confirmed": True},
    )
    assert response.status_code == 200
    assert set(response.json()["categories"]) == {
        "episodic", "temporal", "learning_weakness",
    }
```

- [ ] **Step 2: Run tests and verify endpoint/status failures**

Run: `py -m pytest tests/test_memory_api.py -v`

Expected: FAIL for missing group status and 404 clear endpoint.

- [ ] **Step 3: Add repository group archive**

```python
def archive_categories(self, categories: list[str]) -> int:
    placeholders = ",".join("?" for _ in categories)
    cursor = self.conn.execute(
        f"""UPDATE memory_items
            SET status='archived', updated_at=CURRENT_TIMESTAMP
            WHERE status='active' AND category IN ({placeholders})""",
        categories,
    )
    self._event("memory_group_archived", payload={
        "categories": categories, "count": cursor.rowcount,
    })
    return cursor.rowcount
```

- [ ] **Step 4: Add the confirmed endpoint and status payload**

```python
class MemoryGroupClearRequest(BaseModel):
    confirmed: bool = False

@router.post("/groups/{group}/clear")
def clear_memory_group(group: MemoryGroup, request: MemoryGroupClearRequest) -> dict:
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail={"code": "MEMORY_GROUP_CLEAR_CONFIRMATION_REQUIRED"},
        )
    categories = list(GROUP_CATEGORIES[group])
    with transaction() as conn:
        count = MemoryRepository(conn).archive_categories(categories)
    return {"group": group, "categories": categories, "archived_count": count}
```

Status returns group counts by mapping internal category counts, plus the configured and effective budget based on current context capacity.

- [ ] **Step 5: Run tests and commit**

Run: `py -m pytest tests/test_memory_api.py tests/test_memory_repository.py -v`

Expected: PASS.

```powershell
git add backend/langdrill_agent/routers/memory.py backend/langdrill_agent/memory/repository.py tests/test_memory_api.py
git commit -m "feat: expose user facing memory groups"
```

---

### Task 4: Simplify the Memory UI Without Removing Advanced Controls

**Files:**
- Modify: `frontend/src/features/memory/types.ts`
- Modify: `frontend/src/features/memory/api.ts`
- Modify: `frontend/src/features/memory/MemorySettings.tsx`
- Modify: `frontend/src/features/memory/MemorySettings.test.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 3 status/settings/group clear APIs.
- Produces: mode cards, group controls, provenance display, collapsed developer options.

- [ ] **Step 1: Replace old-control tests with approved interaction tests**

```tsx
it("defaults to standard ten thousand token mode", async () => {
  render(<MemorySettings api={createApi()} />);
  const standard = await screen.findByRole("radio", { name: /标准.*10,000/ });
  expect((standard as HTMLInputElement).checked).toBe(true);
});

it("shows only three user facing groups before developer options open", async () => {
  render(<MemorySettings api={createApi()} />);
  expect(await screen.findByText("关于我")).toBeTruthy();
  expect(screen.getByText("学习记录")).toBeTruthy();
  expect(screen.getByText("使用习惯")).toBeTruthy();
  expect(screen.queryByText("最低置信度")).toBeNull();
  fireEvent.click(screen.getByText("开发者选项"));
  expect(screen.getByText("最低置信度")).toBeTruthy();
});

it("confirms before clearing a group", async () => {
  const api = createApi();
  vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<MemorySettings api={api} />);
  fireEvent.click(await screen.findByRole("button", { name: "清理学习记录" }));
  expect(api.clearGroup).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run the focused UI tests and verify type/render failures**

Run: `npm test -- --run src/features/memory/MemorySettings.test.tsx`

Working directory: `frontend`

Expected: FAIL because old settings expose eight categories and no mode radios.

- [ ] **Step 3: Update exact frontend types and API**

```ts
export type MemoryMode = "economy" | "standard" | "deep";
export type MemoryGroup = "about_me" | "learning_history" | "usage_habits";

export type MemoryBudget = {
  mode: MemoryMode;
  configured_limit: number | null;
  available_context_tokens: number;
  reserved_tokens: number;
  effective_tokens: number;
  constrained_by_context: boolean;
};
```

Add `mode`, `group_enabled`, `effective_budget`, and `group_counts` to status types and:

```ts
clearGroup(group: MemoryGroup): Promise<{ archived_count: number }> {
  return apiPost(`/api/memory/groups/${group}/clear`, { confirmed: true });
}
```

- [ ] **Step 4: Recompose the existing page**

Render:

- a three-card radio group for 节省 5,000 / 标准 10,000 / 深入 动态;
- current effective budget and reserve warning;
- three group cards with description, count, enable switch and clear button;
- existing waiting-review and memory-item lists;
- evidence count, revision count, timestamps and source references in item details;
- export/import/reindex/provider migration and technical policy fields inside a closed `<details><summary>开发者选项</summary>`.

Do not delete advanced state or APIs. Remove the eight-category checkboxes from the default view; show them only inside developer options.

- [ ] **Step 5: Test, build and commit**

Run:

```powershell
Set-Location frontend
npm test -- --run src/features/memory/MemorySettings.test.tsx
npm run build
```

Expected: PASS and build exit 0.

```powershell
git add frontend/src/features/memory frontend/src/styles.css
git commit -m "feat: simplify memory settings into three modes"
```
