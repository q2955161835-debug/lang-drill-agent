import { useCallback, useEffect, useRef, useState } from "react";
import {
  Archive,
  ArrowClockwise,
  Check,
  DownloadSimple,
  FloppyDisk,
  MagnifyingGlass,
  PencilSimple,
  PushPin,
  Trash,
  UploadSimple,
  X,
} from "@phosphor-icons/react";

import { memoryApi, type MemoryApi } from "./api";
import type {
  MemoryCandidate,
  MemoryCategory,
  MemoryGroup,
  MemoryItem,
  MemoryItemDetail,
  MemorySettingsState,
  MemoryStatusResponse,
  ProviderSwitchResult,
} from "./types";

const CATEGORY_LABELS: Record<MemoryCategory, string> = {
  core: "核心",
  semantic: "语义事实",
  episodic: "事件",
  procedural: "过程",
  temporal: "时效",
  preference: "偏好",
  profile: "画像",
  learning_weakness: "学习弱项",
};

const STATUS_LABELS: Record<MemoryItem["status"], string> = {
  active: "生效中",
  archived: "已归档",
  superseded: "已被替代",
  deleted: "已删除",
};

const CANDIDATE_REASON_LABELS: Record<string, string> = {
  approval_required: "等待用户审核",
  insufficient_learning_evidence: "学习证据不足",
  confidence_below_threshold: "置信度未达阈值",
};

// Plan 3 Task 1: 三档记忆模式。token 上限与后端 MODE_LIMITS 保持一致。
const MODE_OPTIONS: Array<{ id: MemorySettingsState["mode"]; label: string; hint: string }> = [
  { id: "economy", label: "节省", hint: "5,000 tokens · 适合快速对话" },
  { id: "standard", label: "标准", hint: "10,000 tokens · 默认推荐" },
  { id: "deep", label: "深入", hint: "动态（最多 70% 可用上下文）· 长程学习" },
];

// Plan 3 Task 1: 三个用户可见组，覆盖内部 8 类 category。
const GROUP_OPTIONS: Array<{ id: MemoryGroup; label: string; description: string }> = [
  { id: "about_me", label: "关于我", description: "核心信息、画像、语义记忆" },
  { id: "learning_history", label: "学习记录", description: "情景、时序、薄弱点" },
  { id: "usage_habits", label: "使用习惯", description: "流程、偏好" },
];

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function providerDetailLabel(detail: string): string {
  const normalized = detail.toLowerCase();
  if (normalized.includes("already primary")) return "当前已是主写供应商。";
  if (normalized.includes("not registered")) return "供应商未注册，主写保持不变。";
  if (normalized.includes("unhealthy")) return "供应商健康检查未通过，主写保持不变。";
  if (normalized.includes("explicit commit required")) return "迁移预检通过，等待显式确认切换。";
  if (normalized.includes("switch committed")) return "主写供应商切换已提交。";
  return detail;
}

export function MemorySettings({ api = memoryApi }: { api?: MemoryApi }) {
  const [status, setStatus] = useState<MemoryStatusResponse | null>(null);
  const [settings, setSettings] = useState<MemorySettingsState | null>(null);
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [candidates, setCandidates] = useState<MemoryCandidate[]>([]);
  const [details, setDetails] = useState<Record<string, MemoryItemDetail>>({});
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [providerId, setProviderId] = useState("builtin");
  const [providerSwitch, setProviderSwitch] = useState<ProviderSwitchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [devOpen, setDevOpen] = useState(false);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  const refresh = useCallback(async (search = "") => {
    const [nextStatus, nextItems, nextCandidates] = await Promise.all([
      api.status(),
      api.listItems(search),
      api.listCandidates(),
    ]);
    setStatus(nextStatus);
    setSettings(nextStatus.settings);
    setItems(nextItems);
    setCandidates(nextCandidates);
    setProviderId(nextStatus.provider.current_primary_id);
  }, [api]);

  useEffect(() => {
    let active = true;
    void Promise.all([api.status(), api.listItems(""), api.listCandidates()])
      .then(([nextStatus, nextItems, nextCandidates]) => {
        if (!active) return;
        setStatus(nextStatus);
        setSettings(nextStatus.settings);
        setItems(nextItems);
        setCandidates(nextCandidates);
        setProviderId(nextStatus.provider.current_primary_id);
      })
      .catch((error: unknown) => {
        if (active) setMessage(errorMessage(error, "记忆设置加载失败"));
      });
    return () => {
      active = false;
    };
  }, [api]);

  const withBusy = async (action: () => Promise<void>, fallback: string) => {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      setMessage(errorMessage(error, fallback));
    } finally {
      setBusy(false);
    }
  };

  const saveSettings = () => withBusy(async () => {
    if (!settings) return;
    const saved = await api.saveSettings(settings);
    setSettings(saved);
    setMessage("记忆设置已保存。");
    await refresh(query);
  }, "记忆设置保存失败");

  const reviewCandidate = (candidateId: string, action: "approve" | "reject") => withBusy(async () => {
    await api.reviewCandidate(candidateId, action);
    setMessage(action === "approve" ? "候选记忆已批准。" : "候选记忆已拒绝。");
    await refresh(query);
  }, "候选记忆审核失败");

  const saveItem = (item: MemoryItem) => withBusy(async () => {
    const content = (editing[item.id] ?? item.content).trim();
    if (!content) return;
    await api.updateItem(item.id, { content });
    setEditing((current) => {
      const next = { ...current };
      delete next[item.id];
      return next;
    });
    setMessage("记忆内容已保存。");
    await refresh(query);
  }, "记忆内容保存失败");

  const actOnItem = (item: MemoryItem, action: string) => withBusy(async () => {
    if (action === "purge" && !window.confirm("永久删除这条记忆、证据引用和版本历史？此操作不可恢复。")) return;
    await api.actOnItem(item.id, action, action === "purge");
    setMessage(action === "purge" ? "记忆已永久删除。" : "记忆状态已更新。");
    await refresh(query);
  }, "记忆状态更新失败");

  const toggleDetail = (itemId: string) => withBusy(async () => {
    if (details[itemId]) {
      setDetails((current) => {
        const next = { ...current };
        delete next[itemId];
        return next;
      });
      return;
    }
    const detail = await api.itemDetail(itemId);
    setDetails((current) => ({ ...current, [itemId]: detail }));
  }, "记忆详情加载失败");

  const clearGroup = (group: MemoryGroup) => withBusy(async () => {
    const label = GROUP_OPTIONS.find((option) => option.id === group)?.label || group;
    if (!window.confirm(`清理“${label}”的全部记忆？此操作会归档相关记忆，可在开发者选项中恢复。`)) return;
    const result = await api.clearGroup(group);
    setMessage(`已归档 ${result.archived_count} 条记忆。`);
    await refresh(query);
  }, "记忆清理失败");

  const exportMemory = () => withBusy(async () => {
    const payload = await api.exportMemory();
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "lang-drill-memory.json";
    anchor.click();
    URL.revokeObjectURL(url);
    setMessage(`已导出 ${payload.records.length} 条记忆。`);
  }, "记忆导出失败");

  const importMemory = (file: File | null) => withBusy(async () => {
    if (!file) return;
    const parsed: unknown = JSON.parse(await file.text());
    const records = Array.isArray(parsed)
      ? parsed
      : typeof parsed === "object" && parsed && "records" in parsed && Array.isArray(parsed.records)
        ? parsed.records
        : [];
    if (!records.length) throw new Error("导入文件不包含记忆记录。");
    const result = await api.importMemory(records);
    setMessage(`已导入 ${result.imported_count} 条，跳过 ${result.skipped_count} 条。`);
    await refresh(query);
  }, "记忆导入失败");

  const reindex = () => withBusy(async () => {
    const result = await api.reindex();
    setMessage(`已重建 ${result.indexed_count} 条记忆索引。`);
  }, "记忆索引重建失败");

  const prepareProvider = () => withBusy(async () => {
    const result = await api.prepareProvider(providerId.trim());
    setProviderSwitch(result);
    setMessage(providerDetailLabel(result.detail));
    await refresh(query);
  }, "记忆供应商预检失败");

  const commitProvider = () => withBusy(async () => {
    if (!providerSwitch?.verification_token) return;
    const result = await api.commitProvider(providerSwitch.requested_provider_id, providerSwitch.verification_token);
    setProviderSwitch(result);
    setMessage(providerDetailLabel(result.detail));
    await refresh(query);
  }, "记忆供应商切换失败");

  if (!status || !settings) {
    return <p className="hint" role="status">{message || "正在加载记忆设置..."}</p>;
  }

  const budget = status.effective_budget;
  const groupCounts = status.group_counts;

  return (
    <div className="memory-settings">
      <div className="memory-summary" aria-label="记忆状态">
        <strong>{status.counts.active || 0} 条生效</strong>
        <span>{status.counts.candidates || 0} 条等待审核</span>
        <span>主写供应商：{status.provider.current_primary_id === "builtin" ? "内置" : status.provider.current_primary_id}</span>
      </div>

      <fieldset className="memory-mode-grid" aria-label="记忆模式">
        <legend>记忆模式</legend>
        {MODE_OPTIONS.map((option) => (
          <label key={option.id} className={`memory-mode-card${settings.mode === option.id ? " is-selected" : ""}`}>
            <input
              type="radio"
              name="memory-mode"
              value={option.id}
              checked={settings.mode === option.id}
              onChange={() => setSettings({ ...settings, mode: option.id })}
            />
            <span>
              <strong>{option.label}</strong>
              <small>{option.hint}</small>
            </span>
          </label>
        ))}
      </fieldset>

      {budget && (
        <div className="memory-budget-summary" aria-label="记忆预算">
          <span>当前有效预算：<strong>{budget.effective_tokens.toLocaleString()}</strong> tokens</span>
          <span>已预留：{budget.reserved_tokens.toLocaleString()} tokens</span>
          {budget.constrained_by_context && (
            <span className="memory-budget-warning">可用上下文不足，已自动降低预算</span>
          )}
        </div>
      )}

      <div className="memory-group-grid" aria-label="记忆分组">
        {GROUP_OPTIONS.map((group) => (
          <article key={group.id} className="memory-group-card">
            <div className="memory-group-head">
              <strong>{group.label}</strong>
              <span>{groupCounts?.[group.id] ?? 0} 条</span>
            </div>
            <small>{group.description}</small>
            <div className="memory-group-actions">
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={settings.group_enabled[group.id]}
                  onChange={(event) => setSettings({
                    ...settings,
                    group_enabled: { ...settings.group_enabled, [group.id]: event.target.checked },
                  })}
                />
                <span>启用</span>
              </label>
              <button
                type="button"
                className="inline-action"
                disabled={busy}
                onClick={() => void clearGroup(group.id)}
              >清理{group.label}</button>
            </div>
          </article>
        ))}
      </div>

      <div className="memory-toggle-grid">
        <label className="check-row">
          <input type="checkbox" checked={settings.enabled} onChange={(event) => setSettings({ ...settings, enabled: event.target.checked })} />
          <span><strong>分层记忆</strong><small>总开关</small></span>
        </label>
        <label className="check-row">
          <input type="checkbox" checked={settings.capture_enabled} onChange={(event) => setSettings({ ...settings, capture_enabled: event.target.checked })} />
          <span><strong>捕获</strong><small>生成候选记忆</small></span>
        </label>
        <label className="check-row">
          <input type="checkbox" checked={settings.recall_enabled} onChange={(event) => setSettings({ ...settings, recall_enabled: event.target.checked })} />
          <span><strong>召回</strong><small>注入受控上下文</small></span>
        </label>
        <label className="check-row">
          <input type="checkbox" checked={settings.compaction_flush_enabled} onChange={(event) => setSettings({ ...settings, compaction_flush_enabled: event.target.checked })} />
          <span><strong>压缩前刷新</strong><small>保留显式长期事实</small></span>
        </label>
        <label className="check-row">
          <input type="checkbox" checked={settings.embeddings_enabled} onChange={(event) => setSettings({ ...settings, embeddings_enabled: event.target.checked })} />
          <span><strong>向量召回</strong><small>不可用时回退全文检索</small></span>
        </label>
      </div>

      <button type="button" className="inline-action primary-inline" disabled={busy} onClick={() => void saveSettings()}><FloppyDisk size={16} />保存记忆设置</button>

      <section className="memory-review-section">
        <div className="memory-section-head"><strong>等待审核</strong><span>{candidates.length}</span></div>
        <div className="memory-list">
          {candidates.map((candidate) => (
            <article key={candidate.id} className="memory-row">
              <div className="memory-row-main">
                <div>
                  <strong>{CATEGORY_LABELS[candidate.category]}</strong>
                  <span>{candidate.evidence_count} {candidate.category === "learning_weakness" ? "次独立错题" : "条证据"}</span>
                </div>
                <p>{candidate.content}</p>
                <small>{CANDIDATE_REASON_LABELS[candidate.reason] || candidate.reason}</small>
              </div>
              <div className="memory-row-actions">
                <button type="button" className="icon-button" aria-label="批准候选记忆" title="批准" disabled={busy} onClick={() => void reviewCandidate(candidate.id, "approve")}><Check size={16} /></button>
                <button type="button" className="icon-button" aria-label="拒绝候选记忆" title="拒绝" disabled={busy} onClick={() => void reviewCandidate(candidate.id, "reject")}><X size={16} /></button>
              </div>
            </article>
          ))}
          {!candidates.length && <p className="hint">没有等待审核的记忆。</p>}
        </div>
      </section>

      <section className="memory-items-section">
        <div className="memory-section-head">
          <strong>记忆条目</strong>
          <div className="memory-search-row">
            <input aria-label="搜索记忆" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void refresh(query); }} />
            <button type="button" className="icon-button" aria-label="搜索记忆" title="搜索" disabled={busy} onClick={() => void refresh(query)}><MagnifyingGlass size={17} /></button>
          </div>
        </div>
        <div className="memory-list">
          {items.map((item) => (
            <article key={item.id} className="memory-row memory-item-row">
              <div className="memory-row-main">
                <div><strong>{CATEGORY_LABELS[item.category]}</strong><span>{STATUS_LABELS[item.status]}{item.pinned ? " · 已置顶" : ""}</span></div>
                {item.id in editing ? (
                  <textarea aria-label={`编辑 ${item.content}`} value={editing[item.id]} onChange={(event) => setEditing((current) => ({ ...current, [item.id]: event.target.value }))} />
                ) : <p>{item.content}</p>}
                <button type="button" className="memory-detail-toggle" onClick={() => void toggleDetail(item.id)}>{details[item.id] ? "收起证据与历史" : "查看证据与历史"}</button>
                {details[item.id] && (
                  <div className="memory-detail">
                    <span>证据 {details[item.id].evidence.length} 条</span>
                    <span>版本 {details[item.id].revisions.length} 条</span>
                    {details[item.id].revisions.map((revision) => <small key={revision.id}>{revision.operation} · {revision.created_at}</small>)}
                  </div>
                )}
              </div>
              <div className="memory-row-actions">
                {item.id in editing ? (
                  <button type="button" className="icon-button" aria-label="保存记忆内容" title="保存" disabled={busy} onClick={() => void saveItem(item)}><FloppyDisk size={16} /></button>
                ) : (
                  <button type="button" className="icon-button" aria-label="编辑记忆内容" title="编辑" disabled={busy} onClick={() => setEditing((current) => ({ ...current, [item.id]: item.content }))}><PencilSimple size={16} /></button>
                )}
                <button type="button" className="icon-button" aria-label={item.pinned ? "取消置顶记忆" : "置顶记忆"} title={item.pinned ? "取消置顶" : "置顶"} disabled={busy} onClick={() => void actOnItem(item, item.pinned ? "unpin" : "pin")}><PushPin size={16} /></button>
                <button type="button" className="icon-button" aria-label={item.status === "archived" ? "恢复记忆" : "归档记忆"} title={item.status === "archived" ? "恢复" : "归档"} disabled={busy} onClick={() => void actOnItem(item, item.status === "archived" ? "restore" : "archive")}><Archive size={16} /></button>
                <button type="button" className="icon-button" aria-label={item.status === "deleted" ? "恢复已删除记忆" : "软删除记忆"} title={item.status === "deleted" ? "恢复" : "删除"} disabled={busy} onClick={() => void actOnItem(item, item.status === "deleted" ? "restore" : "delete")}><Trash size={16} /></button>
                <button type="button" className="icon-button danger-action" aria-label="永久删除记忆" title="永久删除" disabled={busy} onClick={() => void actOnItem(item, "purge")}><Trash size={16} /></button>
              </div>
            </article>
          ))}
          {!items.length && <p className="hint">没有匹配的记忆。</p>}
        </div>
      </section>

      <details className="memory-developer-options" open={devOpen}>
        <summary
          onClick={(event) => {
            event.preventDefault();
            setDevOpen((current) => !current);
          }}
        >开发者选项</summary>
        {devOpen && (
          <div className="memory-developer-body">
            <div className="memory-category-list" aria-label="记忆类别">
              {(Object.keys(CATEGORY_LABELS) as MemoryCategory[]).map((category) => (
                <label key={category} className="inline-check">
                  <input
                    type="checkbox"
                    checked={settings.category_enabled[category]}
                    onChange={(event) => setSettings({
                      ...settings,
                      category_enabled: { ...settings.category_enabled, [category]: event.target.checked },
                    })}
                  />
                  {CATEGORY_LABELS[category]}
                </label>
              ))}
            </div>

            <div className="memory-policy-grid">
              <label><span>写入模式</span><select value={settings.write_mode} onChange={(event) => setSettings({ ...settings, write_mode: event.target.value as MemorySettingsState["write_mode"] })}><option value="explicit">仅显式</option><option value="approval">全部审核</option><option value="balanced">平衡</option><option value="proactive">主动</option></select></label>
              <label><span>弱项证据数</span><input type="number" min="2" max="20" value={settings.learning_evidence_min} onChange={(event) => setSettings({ ...settings, learning_evidence_min: Number(event.target.value) })} /></label>
              <label><span>最低置信度</span><input type="number" min="0" max="1" step="0.05" value={settings.confidence_min} onChange={(event) => setSettings({ ...settings, confidence_min: Number(event.target.value) })} /></label>
              <label><span>默认有效天数</span><input type="number" min="1" max="3650" value={settings.default_ttl_days} onChange={(event) => setSettings({ ...settings, default_ttl_days: Number(event.target.value) })} /></label>
              <label><span>核心记忆预算</span><input type="number" min="50" max="20000" value={settings.core_token_budget} onChange={(event) => setSettings({ ...settings, core_token_budget: Number(event.target.value) })} /></label>
              <label><span>召回数量</span><input type="number" min="1" max="50" value={settings.recall_top_k} onChange={(event) => setSettings({ ...settings, recall_top_k: Number(event.target.value) })} /></label>
              <label><span>召回令牌预算</span><input type="number" min="100" max="20000" value={settings.recall_token_budget} onChange={(event) => setSettings({ ...settings, recall_token_budget: Number(event.target.value) })} /></label>
            </div>

            <div className="memory-tool-row">
              <button type="button" className="inline-action" disabled={busy} onClick={() => void exportMemory()}><DownloadSimple size={16} />导出</button>
              <button type="button" className="inline-action" disabled={busy} onClick={() => importInputRef.current?.click()}><UploadSimple size={16} />导入</button>
              <input ref={importInputRef} type="file" accept="application/json,.json" hidden onChange={(event) => void importMemory(event.target.files?.[0] || null)} />
              <button type="button" className="inline-action" disabled={busy} onClick={() => void reindex()}><ArrowClockwise size={16} />重建索引</button>
            </div>

            <div className="memory-provider-row">
              <input aria-label="记忆供应商" value={providerId} onChange={(event) => setProviderId(event.target.value)} />
              <button type="button" className="inline-action" disabled={busy || !providerId.trim()} onClick={() => void prepareProvider()}>预检供应商</button>
              {providerSwitch?.migration_verified && providerSwitch.verification_token && (
                <button type="button" className="inline-action primary-inline" disabled={busy} onClick={() => void commitProvider()}>确认切换主写</button>
              )}
            </div>
          </div>
        )}
      </details>

      {message && <p className="hint strong-hint" role="status">{message}</p>}
    </div>
  );
}
