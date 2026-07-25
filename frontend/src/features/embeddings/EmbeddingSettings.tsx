import { useCallback, useEffect, useState } from "react";
import {
  ArrowClockwise,
  CaretDown,
  CheckCircle,
  DownloadSimple,
  Lightning,
  Plug,
  X,
} from "@phosphor-icons/react";

import { embeddingApi, type EmbeddingApi, type EmbeddingSettingsPatch } from "./api";
import type {
  EmbeddingJob,
  EmbeddingModelSummary,
  EmbeddingReindexTarget,
  EmbeddingStatusResponse,
} from "./types";

const MODE_LABELS: Record<EmbeddingStatusResponse["settings"]["mode"], string> = {
  off: "关闭（FTS5 全文检索）",
  local: "本地模型（HuggingFace 下载，本地推理）",
  huggingface_cloud: "云端模型（Hugging Face Inference）",
  openai_compatible: "OpenAI 兼容供应商",
};

const INDEX_LABELS: Record<EmbeddingReindexTarget, string> = {
  knowledge: "知识库",
  past_papers: "历年真题",
  memory: "记忆",
};

const INDEX_STATUS_LABELS: Record<string, string> = {
  fts_only: "仅 FTS5",
  stale: "已过期，等待重建",
  rebuilding: "重建中",
  indexed: "已索引",
  failed: "失败",
};

function formatBytes(value: number): string {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let scaled = value;
  let unitIndex = 0;
  while (scaled >= 1024 && unitIndex < units.length - 1) {
    scaled /= 1024;
    unitIndex += 1;
  }
  return `${scaled.toFixed(scaled >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function jobProgressPercent(job: EmbeddingJob): number {
  if (!job.files_total) return 0;
  return Math.min(100, Math.round((job.files_completed / job.files_total) * 100));
}

export function EmbeddingSettings({ api = embeddingApi }: { api?: EmbeddingApi }) {
  const [status, setStatus] = useState<EmbeddingStatusResponse | null>(null);
  const [recommendations, setRecommendations] = useState<EmbeddingModelSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<EmbeddingModelSummary[]>([]);
  const [activeJob, setActiveJob] = useState<EmbeddingJob | null>(null);
  const [runtimeJob, setRuntimeJob] = useState<EmbeddingJob | null>(null);
  const [draftMode, setDraftMode] = useState<EmbeddingStatusResponse["settings"]["mode"]>("off");
  const [draftModelId, setDraftModelId] = useState("");
  const [draftRevision, setDraftRevision] = useState("");
  const [draftBaseUrl, setDraftBaseUrl] = useState("");
  const [draftApiKey, setDraftApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [testResult, setTestResult] = useState<{ healthy: boolean; error?: string } | null>(null);

  const refresh = useCallback(async () => {
    const next = await api.status();
    setStatus(next);
    setDraftMode(next.settings.mode);
    setDraftModelId(next.settings.model_id);
    setDraftRevision(next.settings.revision);
    setDraftBaseUrl(next.settings.base_url);
    const models = await api.listModels("");
    setRecommendations(models.recommendations);
    if (next.runtime.identity) {
      setRuntimeJob(null);
    }
  }, [api]);

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setMessage(errorMessage(error, "嵌入模型状态加载失败"));
    });
  }, [refresh]);

  const runSearch = async () => {
    const query = searchQuery.trim();
    if (!query) return;
    setBusy(true);
    try {
      const response = await api.listModels(query);
      setSearchResults(response.search_results);
    } catch (error) {
      setMessage(errorMessage(error, "Hugging Face 搜索失败"));
    } finally {
      setBusy(false);
    }
  };

  const saveMode = async (activate: boolean) => {
    setBusy(true);
    setMessage(activate ? "正在保存设置并执行健康检查..." : "正在保存嵌入模型设置...");
    try {
      const patch: EmbeddingSettingsPatch = {
        mode: draftMode,
        model_id: draftModelId,
        revision: draftRevision,
        base_url: draftBaseUrl,
      };
      if (draftApiKey) {
        patch.api_key = draftApiKey;
      }
      if (activate) {
        patch.activate = true;
      }
      const next = await api.saveSettings(patch);
      setStatus(next);
      setMessage(
        activate
          ? "嵌入模型已激活，可前往重建向量索引。"
          : "嵌入模型设置已保存；切换模式后现有索引标记为过期，需要显式重建才会启用混合检索。",
      );
      setDraftApiKey("");
    } catch (error) {
      setMessage(errorMessage(error, "嵌入模型设置保存失败"));
    } finally {
      setBusy(false);
    }
  };

  const downloadModel = async (model: EmbeddingModelSummary) => {
    if (!window.confirm(`下载 ${model.model_id} 模型权重？需要确认才会写入本地磁盘。`)) {
      return;
    }
    setBusy(true);
    setMessage(`正在创建下载任务：${model.model_id} ...`);
    try {
      const response = await api.startDownload({
        model_id: model.model_id,
        revision: model.revision || "main",
        confirmed: true,
      });
      setActiveJob(response.job);
      setMessage(`下载任务已创建：${response.job.id}`);
    } catch (error) {
      setMessage(errorMessage(error, "下载任务创建失败"));
    } finally {
      setBusy(false);
    }
  };

  const cancelDownload = async () => {
    if (!activeJob) return;
    setBusy(true);
    try {
      const response = await api.cancelDownload(activeJob.id);
      setActiveJob(response.job);
      setMessage("已请求取消下载任务；正在运行的文件完成后会停止。");
    } catch (error) {
      setMessage(errorMessage(error, "取消下载失败"));
    } finally {
      setBusy(false);
    }
  };

  const refreshJob = async () => {
    if (!activeJob) return;
    try {
      const response = await api.downloadStatus(activeJob.id);
      setActiveJob(response.job);
    } catch (error) {
      setMessage(errorMessage(error, "下载状态查询失败"));
    }
  };

  const installRuntime = async () => {
    if (
      !window.confirm(
        "安装本地嵌入运行时（sentence-transformers 等依赖）？需要确认才会执行 pip 安装。",
      )
    ) {
      return;
    }
    setBusy(true);
    setMessage("正在创建运行时安装任务...");
    try {
      const response = await api.installRuntime(true);
      setRuntimeJob(response.job);
      setMessage(`运行时安装任务已创建：${response.job.id}`);
    } catch (error) {
      setMessage(errorMessage(error, "运行时安装任务创建失败"));
    } finally {
      setBusy(false);
    }
  };

  const rebuildIndexes = async () => {
    if (!status) return;
    if (
      !window.confirm(
        "重建所有标记为过期的向量索引？需要确认才会执行嵌入计算，原 FTS5 数据不会删除。",
      )
    ) {
      return;
    }
    setBusy(true);
    setMessage("正在重建向量索引...");
    try {
      const targets: EmbeddingReindexTarget[] = ["knowledge", "past_papers", "memory"];
      const response = await api.reindex(targets, true);
      const next = await api.status();
      setStatus(next);
      const failed = Object.entries(response.results).filter(
        ([, value]) => value.status !== "indexed",
      );
      if (failed.length) {
        setMessage(`部分索引重建失败：${failed.map(([key]) => INDEX_LABELS[key as EmbeddingReindexTarget]).join("、")}`);
      } else {
        setMessage("向量索引已重建，混合检索已启用。");
      }
    } catch (error) {
      setMessage(errorMessage(error, "向量索引重建失败"));
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    setBusy(true);
    setMessage("正在测试当前嵌入模型连接...");
    try {
      const result = await api.testConnection();
      setTestResult({ healthy: result.healthy, error: result.error });
      setMessage(result.healthy ? "健康检查通过。" : `健康检查失败：${result.error ?? "未知错误"}`);
    } catch (error) {
      setTestResult({ healthy: false, error: errorMessage(error, "请求失败") });
      setMessage(errorMessage(error, "健康检查请求失败"));
    } finally {
      setBusy(false);
    }
  };

  const runtimeLoaded = status?.runtime.loaded ?? false;
  const staleIndexes = status?.indexes.filter((item) => item.status === "stale") ?? [];
  const hasStaleIndexes = staleIndexes.length > 0;

  return (
    <section className="embedding-settings" aria-label="嵌入模型设置">
      <header className="embedding-summary">
        <strong>嵌入模型</strong>
        <span>
          当前模式：{status ? MODE_LABELS[status.settings.mode] : "加载中..."}
        </span>
        <span>
          检索方式：{status?.effective_mode === "hybrid" ? "混合（FTS5 + 向量）" : "FTS5 全文检索"}
        </span>
        {status?.settings.api_key_configured ? (
          <span className="hint strong-hint">云端密钥已配置</span>
        ) : (
          <span className="hint">未配置云端密钥</span>
        )}
      </header>

      <div className="embedding-mode-grid">
        {(["off", "local", "huggingface_cloud", "openai_compatible"] as const).map((mode) => (
          <label key={mode} className="embedding-mode-option">
            <input
              type="radio"
              name="embedding-mode"
              value={mode}
              checked={draftMode === mode}
              onChange={() => setDraftMode(mode)}
            />
            <span>{MODE_LABELS[mode]}</span>
          </label>
        ))}
      </div>

      {draftMode !== "off" && (
        <div className="embedding-config-row">
          <label>
            <span>模型 ID</span>
            <input
              value={draftModelId}
              onChange={(event) => setDraftModelId(event.target.value)}
              placeholder="Qwen/Qwen3-Embedding-0.6B"
            />
          </label>
          <label>
            <span>修订版本</span>
            <input
              value={draftRevision}
              onChange={(event) => setDraftRevision(event.target.value)}
              placeholder="main"
            />
          </label>
          {draftMode === "openai_compatible" && (
            <>
              <label>
                <span>Base URL</span>
                <input
                  value={draftBaseUrl}
                  onChange={(event) => setDraftBaseUrl(event.target.value)}
                  placeholder="https://api.example.com/v1"
                />
              </label>
              <label>
                <span>API Key（仅保存到本地 .env）</span>
                <input
                  type="password"
                  value={draftApiKey}
                  onChange={(event) => setDraftApiKey(event.target.value)}
                  placeholder={status?.settings.api_key_configured ? "已配置，留空保持不变" : "粘贴密钥后保存"}
                />
              </label>
            </>
          )}
          {draftMode === "huggingface_cloud" && (
            <label>
              <span>Hugging Face Token（仅保存到本地 .env）</span>
              <input
                type="password"
                value={draftApiKey}
                onChange={(event) => setDraftApiKey(event.target.value)}
                placeholder={status?.settings.api_key_configured ? "已配置，留空保持不变" : "粘贴 token 后保存"}
              />
            </label>
          )}
        </div>
      )}

      <div className="embedding-actions">
        <button
          type="button"
          className="inline-action primary-inline"
          disabled={busy}
          onClick={() => void saveMode(false)}
        >
          保存设置
        </button>
        <button
          type="button"
          className="inline-action"
          disabled={busy || draftMode === "off"}
          onClick={() => void saveMode(true)}
          title="保存设置并执行健康检查；只有通过才会启用嵌入运行时"
        >
          <Plug size={16} /> 保存并激活
        </button>
        <button
          type="button"
          className="inline-action"
          disabled={busy || draftMode === "off"}
          onClick={() => void runTest()}
        >
          <Lightning size={16} /> 测试连接
        </button>
        {testResult && (
          <small className={testResult.healthy ? "hint strong-hint" : "error-text"}>
            {testResult.healthy ? "健康检查通过" : testResult.error ?? "未通过"}
          </small>
        )}
      </div>

      {draftMode === "local" && !runtimeLoaded && (
        <div className="embedding-runtime-install">
          <p className="hint">
            本地嵌入运行时未就绪；需要先安装 sentence-transformers 等依赖才能加载本地模型。
          </p>
          <button
            type="button"
            className="inline-action primary-inline"
            disabled={busy}
            onClick={() => void installRuntime()}
          >
            <DownloadSimple size={16} /> 安装本地运行时
          </button>
        </div>
      )}

      {runtimeJob && (
        <article className="embedding-job-progress" aria-label="运行时安装任务">
          <strong>运行时安装任务</strong>
          <span>状态：{runtimeJob.status}</span>
          {runtimeJob.error_code && <small className="error-text">{runtimeJob.error_code}</small>}
          {runtimeJob.error_detail && <small className="hint">{runtimeJob.error_detail}</small>}
        </article>
      )}

      <div className="embedding-model-list" aria-label="推荐嵌入模型">
        <p className="hint">推荐模型（已审核，不启用 trust_remote_code）：</p>
        {recommendations.map((model) => (
          <article key={model.model_id} className="embedding-model-card">
            <div>
              <strong>{model.model_id}</strong>
              <span>{model.library} · {model.pipeline_tag}</span>
              {model.recommended && <em>推荐</em>}
            </div>
            <button
              type="button"
              className="inline-action"
              disabled={busy}
              onClick={() => void downloadModel(model)}
            >
              <DownloadSimple size={16} /> 下载 {model.model_id.split("/").pop()}
            </button>
          </article>
        ))}
      </div>

      <div className="embedding-search-row">
        <input
          aria-label="Hugging Face 模型搜索"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void runSearch();
          }}
          placeholder="搜索 Hugging Face 嵌入模型"
        />
        <button
          type="button"
          className="inline-action square-action"
          aria-label="搜索模型"
          title="搜索模型"
          disabled={!searchQuery.trim() || busy}
          onClick={() => void runSearch()}
        >
          <ArrowClockwise size={18} />
        </button>
      </div>

      {searchResults.length > 0 && (
        <div className="embedding-model-list" aria-label="搜索结果">
          {searchResults.map((model) => (
            <article key={model.model_id} className="embedding-model-card">
              <div>
                <strong>{model.model_id}</strong>
                <span>
                  {model.library} · {model.pipeline_tag} · 下载 {model.downloads} · {formatBytes(model.size_bytes)}
                </span>
                {model.blockers.length > 0 && (
                  <small className="error-text">阻断项：{model.blockers.join("、")}</small>
                )}
                {!model.compatible && <small className="hint">该模型不可直接下载</small>}
              </div>
              <button
                type="button"
                className="inline-action"
                disabled={busy || !model.compatible}
                onClick={() => void downloadModel(model)}
              >
                <DownloadSimple size={16} /> 下载
              </button>
            </article>
          ))}
        </div>
      )}

      {activeJob && (
        <article className="embedding-job-progress" aria-label="嵌入模型下载任务">
          <header>
            <strong>{activeJob.model_id}</strong>
            <button
              type="button"
              className="icon-button"
              aria-label="刷新下载状态"
              title="刷新下载状态"
              disabled={busy}
              onClick={() => void refreshJob()}
            >
              <ArrowClockwise size={16} />
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label="取消下载"
              title="取消下载"
              disabled={busy || activeJob.cancel_requested}
              onClick={() => void cancelDownload()}
            >
              <X size={16} />
            </button>
          </header>
          <span>状态：{activeJob.status}</span>
          <span>
            进度：{activeJob.files_completed}/{activeJob.files_total} 文件 · {formatBytes(activeJob.bytes_downloaded)} · {jobProgressPercent(activeJob)}%
          </span>
          {activeJob.error_code && <small className="error-text">{activeJob.error_code}</small>}
          {activeJob.error_detail && <small className="hint">{activeJob.error_detail}</small>}
        </article>
      )}

      <div className="embedding-index-status" aria-label="向量索引状态">
        <p className="hint">向量索引状态（切换模式后会标记为过期，FTS5 始终可用作兜底）：</p>
        <ul>
          {status?.indexes.map((item) => (
            <li key={item.target}>
              <strong>{INDEX_LABELS[item.target]}</strong>
              <span>{INDEX_STATUS_LABELS[item.status] ?? item.status}</span>
              {item.indexed_count > 0 && <small>已索引 {item.indexed_count} 条</small>}
              {item.error_code && <small className="error-text">{item.error_code}</small>}
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="inline-action"
          disabled={busy || !hasStaleIndexes || status?.effective_mode !== "hybrid"}
          onClick={() => void rebuildIndexes()}
        >
          <CheckCircle size={16} /> 重新建立向量索引
        </button>
      </div>

      {message && <p className="hint strong-hint" role="status">{message}</p>}

      <details className="embedding-developer-details">
        <summary>
          <CaretDown size={14} /> 开发者详情（运行时身份、目录与原始状态）
        </summary>
        <dl>
          <dt>当前模式</dt>
          <dd>{status?.settings.mode ?? "—"}</dd>
          <dt>模型目录</dt>
          <dd>{status?.settings.model_dir || "—"}</dd>
          <dt>Base URL</dt>
          <dd>{status?.settings.base_url || "—"}</dd>
          <dt>启用身份</dt>
          <dd>{status?.settings.enabled_identity ? JSON.stringify(status.settings.enabled_identity) : "未激活"}</dd>
          <dt>Runtime loaded</dt>
          <dd>{String(status?.runtime.loaded ?? false)}</dd>
          <dt>Runtime healthy</dt>
          <dd>{String(status?.runtime.healthy ?? false)}</dd>
          <dt>云端密钥已配置</dt>
          <dd>{String(status?.settings.api_key_configured ?? false)}</dd>
        </dl>
      </details>
    </section>
  );
}
