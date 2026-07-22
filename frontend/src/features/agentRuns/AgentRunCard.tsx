import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CaretDown,
  CaretRight,
  CheckCircle,
  Pause,
  Play,
  StopCircle,
  WarningCircle,
} from "@phosphor-icons/react";

import { agentRunApi } from "./client";
import type { AgentRun, AgentRunApi, AgentRunDetail } from "./types";

const STATUS_LABELS: Record<AgentRun["status"], string> = {
  queued: "等待执行",
  running: "执行中",
  paused: "已暂停",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const EVENT_LABELS: Record<string, string> = {
  plan_replaced: "计划已保存",
  planning_completed: "规划已完成",
  planning_fallback: "规划已使用安全兜底",
  step_claimed: "步骤已领取",
  step_completed: "步骤已完成",
  step_failed: "步骤失败",
  step_retry_scheduled: "步骤等待重试",
  tool_call_recorded: "工具调用已记录",
  tool_call_completed: "工具调用已完成",
  tool_call_failed: "工具调用失败",
  tool_call_reused: "已复用持久化工具结果",
  approval_requested: "等待审批",
  paused: "任务已暂停",
  resumed: "任务已恢复",
  cancelled: "任务已取消",
  replan_required: "需要重新规划",
  run_completed: "任务已完成",
};

const RISK_LABELS: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  critical: "严重风险",
};

const APPROVAL_STATUS_LABELS: Record<string, string> = {
  pending: "等待审批",
  approved: "已批准",
  rejected: "已拒绝",
  expired: "已过期",
};

function evidenceText(evidence: Record<string, unknown>): string {
  if (!Object.keys(evidence).length) return "";
  return JSON.stringify(evidence);
}

export function AgentRunCard({
  run,
  api = agentRunApi,
}: {
  run: AgentRun;
  api?: AgentRunApi;
}) {
  const [detail, setDetail] = useState<AgentRunDetail | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    const next = await api.getDetail(run.id);
    setDetail(next);
  }, [api, run.id]);

  useEffect(() => {
    let active = true;
    void api.getDetail(run.id)
      .then((next) => {
        if (active) setDetail(next);
      })
      .catch((error: unknown) => {
        if (active) setMessage(error instanceof Error ? error.message : "任务计划加载失败");
      });
    return () => {
      active = false;
    };
  }, [api, run.id]);

  const runStatus = detail?.run.status ?? run.status;

  useEffect(() => {
    if (!detail || !["queued", "running"].includes(runStatus)) {
      return undefined;
    }
    return api.subscribe(run.id, () => {
      void refresh();
    });
  }, [api, detail === null, refresh, run.id, runStatus]);

  const currentRun = detail?.run ?? run;
  const steps = detail?.steps ?? [];
  const currentStep = useMemo(
    () => steps.find((step) => !["completed", "cancelled"].includes(step.status)) ?? steps.at(-1),
    [steps],
  );
  const completedCount = steps.filter((step) => step.status === "completed").length;
  const displaySequence = currentStep?.sequence ?? Math.min(completedCount + 1, Math.max(steps.length, 1));
  const evidence = steps
    .map((step) => ({ step, text: evidenceText(step.evidence) }))
    .filter((item) => item.text);
  const approvals = detail?.approvals ?? [];
  const recentEvents = (detail?.events ?? []).slice(-5).reverse();

  const act = (action: "pause" | "resume" | "cancel") => {
    setBusy(true);
    setMessage("");
    void api[action](run.id)
      .then((nextRun) => {
        setDetail((current) => current ? { ...current, run: nextRun } : current);
        return refresh();
      })
      .catch((error: unknown) => {
        setMessage(error instanceof Error ? error.message : "任务状态更新失败");
      })
      .finally(() => setBusy(false));
  };

  return (
    <section className="agent-run-card" aria-label="复杂任务计划">
      <div className="agent-run-head">
        <button
          type="button"
          className="agent-run-toggle"
          aria-label={expanded ? "收起任务计划" : "展开任务计划"}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? <CaretDown size={16} /> : <CaretRight size={16} />}
        </button>
        <div className="agent-run-title">
          <strong>{currentRun.goal}</strong>
          <span>{STATUS_LABELS[currentRun.status]}</span>
          <span>步骤 {displaySequence} / {steps.length || 1}</span>
        </div>
        <div className="agent-run-actions">
          {currentRun.status === "running" || currentRun.status === "queued" ? (
            <button type="button" className="inline-action" disabled={busy} onClick={() => act("pause")}>
              <Pause size={15} />暂停
            </button>
          ) : null}
          {currentRun.status === "paused" ? (
            <button type="button" className="inline-action primary-inline" disabled={busy} onClick={() => act("resume")}>
              <Play size={15} />继续
            </button>
          ) : null}
          {!(["completed", "failed", "cancelled"] as string[]).includes(currentRun.status) ? (
            <button type="button" className="icon-button danger-action" aria-label="取消任务" title="取消" disabled={busy} onClick={() => act("cancel")}>
              <StopCircle size={17} />
            </button>
          ) : null}
        </div>
      </div>

      {expanded && (
        <div className="agent-run-body">
          <div className="agent-run-criteria">
            <strong>完成条件</strong>
            {currentRun.completion_criteria.map((criterion) => <span key={criterion}>{criterion}</span>)}
          </div>
          <div className="agent-run-steps">
            {steps.map((step) => (
              <div key={step.id} className={`agent-run-step ${step.status}`}>
                <span className="agent-run-step-icon">
                  {step.status === "completed" ? <CheckCircle size={16} /> : step.status === "failed" ? <WarningCircle size={16} /> : step.sequence}
                </span>
                <div>
                  <strong>{step.title}</strong>
                  <span>{step.description}</span>
                  <small>{step.tool_names.join(" · ")}</small>
                </div>
                <span>{step.attempts}/{step.max_attempts}</span>
              </div>
            ))}
          </div>
          {evidence.length > 0 && (
            <div className="agent-run-evidence">
              <strong>验证证据</strong>
              {evidence.map(({ step, text }) => <code key={step.id}>{step.sequence}. {text}</code>)}
            </div>
          )}
          {approvals.length > 0 && (
            <div className="agent-run-audit">
              <strong>审批与风险</strong>
              {approvals.map((approval) => (
                <span key={approval.id}>
                  {approval.capability} · {RISK_LABELS[approval.risk_level] ?? approval.risk_level} · {APPROVAL_STATUS_LABELS[approval.status] ?? approval.status}
                </span>
              ))}
            </div>
          )}
          {recentEvents.length > 0 && (
            <div className="agent-run-audit">
              <strong>最近事件</strong>
              {recentEvents.map((event) => (
                <span key={event.id}>{EVENT_LABELS[event.event_type] ?? event.event_type}</span>
              ))}
            </div>
          )}
          {currentRun.error_code && <p className="agent-run-error">{currentRun.error_code}</p>}
          {message && <p className="agent-run-error" role="status">{message}</p>}
        </div>
      )}
    </section>
  );
}
