import { useCallback, useEffect, useState } from "react";

import type { CreativeApi } from "./api";
import type { CreativeAuditEvent } from "./types";

interface Props {
  api: CreativeApi;
  runId?: string;
}

const EVENT_LABELS: Record<string, string> = {
  message_delta: "模型输出",
  pi_runtime_started: "Pi 运行时启动",
  pi_runtime_restarted: "Pi 运行时重启",
  pi_dispatch_failed: "Pi 调度失败",
  step_claimed: "步骤开始",
  step_completed: "步骤完成",
  step_failed: "步骤失败",
  step_retry_scheduled: "步骤重试",
  tool_call_recorded: "工具请求",
  tool_policy_decision: "策略决策",
  tool_call_completed: "工具执行完成",
  tool_call_failed: "工具执行失败",
  tool_call_cancelled: "工具执行取消",
  tool_execution_completed: "执行结果",
  approval_requested: "审批请求",
  approval_approved: "审批通过",
  approval_denied: "审批拒绝",
  approval_expired: "审批过期",
  approval_resolved: "审批已处理",
  settings_saved: "设置保存",
  plan_replaced: "计划更新",
  paused: "运行暂停",
  resumed: "运行恢复",
  cancelled: "运行取消",
  run_completed: "运行完成",
  run_failed: "运行失败",
  replan_required: "需要重新规划",
  pi_execution_plan_bound: "执行计划绑定",
};

function classifyEvent(eventType: string): string {
  if (eventType === "message_delta") return "model-text";
  if (eventType.startsWith("step_") || eventType === "plan_replaced") return "plan-step";
  if (eventType === "tool_call_recorded") return "tool-request";
  if (eventType === "tool_policy_decision") return "decision";
  if (eventType.startsWith("tool_call_") || eventType === "tool_execution_completed") return "execution";
  if (eventType.startsWith("approval_")) return "decision";
  if (eventType === "run_completed" || eventType === "replan_required" || eventType === "pi_execution_plan_bound") return "verification";
  return "other";
}

function summarizePayload(payload: Record<string, unknown>): string {
  const keys = Object.keys(payload);
  if (keys.length === 0) return "";
  const parts: string[] = [];
  for (const key of ["tool_name", "action", "decision", "step_id", "error_code", "reason"]) {
    if (key in payload && payload[key] !== null && payload[key] !== "") {
      parts.push(`${key}: ${String(payload[key])}`);
    }
  }
  return parts.join(" · ");
}

export function CreativeRunTimeline({ api, runId }: Props) {
  const [events, setEvents] = useState<CreativeAuditEvent[]>([]);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const list = await api.listAuditEvents(runId);
      setEvents(list);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载审计事件失败");
    }
  }, [api, runId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (error) {
    return <p className="hint" role="alert">{error}</p>;
  }

  if (events.length === 0) {
    return <p className="hint">暂无审计事件。</p>;
  }

  return (
    <div className="creative-timeline" aria-label="创造模式审计时间线">
      {events.map((event) => {
        const label = EVENT_LABELS[event.event_type] || event.event_type;
        const category = classifyEvent(event.event_type);
        const summary = summarizePayload(event.payload);
        return (
          <div
            key={event.id}
            className={`creative-timeline-item type-${event.event_type}`}
            data-category={category}
          >
            <span className="creative-timeline-dot" />
            <div className="creative-timeline-body">
              <div className="creative-timeline-meta">
                <span>{label}</span>
                {event.run_id && <span> · run: {event.run_id.slice(-8)}</span>}
                {event.created_at && <span> · {event.created_at}</span>}
              </div>
              {event.reason_code && (
                <div className="creative-timeline-reason">{event.reason_code}</div>
              )}
              {summary && (
                <div className="creative-timeline-payload">{summary}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
