# Resource Import, RAG, Memory, and Demo Rollout

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement these plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved true-paper upload, knowledge drag/drop, user-controlled embeddings/RAG, simplified memory modes, and stable/experimental demo downloads as four independently testable increments.

**Architecture:** The work is split at stable subsystem boundaries. Each plan produces working software and a reviewable commit series; shared embedding services land before memory vector integration.

**Tech Stack:** Python 3.11, FastAPI, SQLite/FTS5, Pydantic 2, React 19, TypeScript 5.8, Vitest, Hugging Face Hub, sentence-transformers.

## Global Constraints

- Preserve the current navigation, dark/light theme, card layout, and component styling language.
- RAG defaults to `off`; no model download, runtime install, cloud call, model activation, or reindex occurs without an explicit user action.
- Local embedding defaults to `Qwen/Qwen3-Embedding-0.6B`; `trust_remote_code` is always `False`.
- Memory modes are economy `5,000`, standard `10,000` (default), and deep with no fixed cap while reserving at least `30%` of available context.
- File selection and parsing do not write formal knowledge or past-paper records; only explicit confirmation writes formal data.
- Stable download is `v0.1.2`; experimental download and online experience are `v1.0.0-alpha.2`.
- Do not change GitHub Release prerelease flags.
- Real tokens and API keys stay in `.env`; `.env.example` contains placeholders only.

## Execution Order

1. [Staged true-paper and knowledge imports](2026-07-25-staged-resource-imports.md)
2. [Embedding runtime, Hugging Face model management, and RAG](2026-07-25-embedding-runtime-rag.md)
3. [Three-mode memory redesign](2026-07-25-memory-modes-redesign.md)
4. [Demo download channels and integrated L3 acceptance](2026-07-25-demo-download-channels-and-acceptance.md)

## Required Execution Discipline

- Run each plan using `superpowers:subagent-driven-development` or `superpowers:executing-plans`.
- Use `superpowers:test-driven-development` for every behavior change.
- Commit after each task; stage only files listed by that task.
- Run the task-local tests before each commit and the complete L3 suite in the final plan.
- Use `superpowers:verification-before-completion` before claiming completion.
- Use `superpowers:requesting-code-review` before final acceptance.
- Use `superpowers:finishing-a-development-branch` only after the task acceptance record concludes `通过`.
