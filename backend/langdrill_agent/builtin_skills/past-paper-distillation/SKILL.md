---
name: past-paper-distillation（真题蒸馏）
description: Distill evidence-backed patterns from locally installed real past papers（从本地已安装真实真题中蒸馏有证据支持的模式）.
---

# Past Paper Distillation（真题蒸馏）

## Workflow（工作流）

1. Call `past_papers.status`（调用真题状态）and confirm that remote catalog entries are not counted as installed papers（确认远程目录项不计为已安装试卷）.
2. Call `past_papers.validate`（调用真题校验）and exclude failed documents, unverified answers, unsupported types, and listening items（排除失败文档、未验证答案、不支持题型和听力项）.
3. Call `past_papers.distill`（调用真题蒸馏）with only validated local document IDs（只传入已验证本地文档标识符）.
4. Call `past_papers.inspect_findings`（调用发现检查）and present evidence counts, paper counts, years, confidence, and evidence question IDs（展示证据数、试卷数、年份、置信度和证据题目标识符）.

## Boundaries（边界）

- Never invent a paper, year, set, answer, source, or evidence ID（不得虚构试卷、年份、套卷、答案、来源或证据标识符）.
- Never promote `insufficient_evidence`（证据不足）to a ready finding（就绪发现）.
- Model wording may label deterministic aggregates only（模型措辞只能标注程序确定性聚合结果）.
- A finding must remain traceable to every stored evidence question ID（每条发现必须可追溯到全部已存储证据题目标识符）.
