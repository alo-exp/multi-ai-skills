# Roadmap: MultAI

## Milestones

- ✅ **v0.2 Alpha** — Core engine, 7 platforms, Help Center, CI (shipped 2026-04-08)
- 🚧 **v0.3 Quality** — Phases 1+ (in progress)

## Phases

<details>
<summary>✅ v0.2 Alpha — SHIPPED 2026-04-08</summary>

Core engine: parallel 7-platform orchestration, rate limiting, agent fallback, XLSX matrix, Help Center, SENTINEL security audit, CI pipeline.

</details>

### 🚧 v0.3 Quality (In Progress)

**Milestone Goal:** Production-grade test coverage and reliability.

## Phase Details

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1     | v0.3      | 0/7            | Planning | - |


### Phase 1: Achieve 100% unit test coverage

**Goal:** Achieve 100% unit test coverage enforced in CI (--cov-fail-under=100), with all existing 99 tests continuing to pass and all new tests passing in CI on Python 3.11/3.12/3.13.
**Requirements**: [COV-INFRA, COV-PRAGMA, COV-CI, COV-MATRIX, COV-RATE-LIMITER, COV-ENGINE-SETUP, COV-CLI, COV-PROMPT-LOADER, COV-STATUS-WRITER, COV-LAUNCH-REPORT, COV-TAB-MANAGER, COV-BASE-PLATFORM, COV-BROWSER-UTILS, COV-INJECT-UTILS, COV-AGENT-FALLBACK, COV-RETRY-HANDLER, COV-CHATGPT, COV-CLAUDE-AI, COV-COPILOT, COV-DEEPSEEK, COV-GEMINI, COV-GROK, COV-PERPLEXITY, COV-CHATGPT-EXTRACTOR, COV-ORCHESTRATOR, COV-CONFIG, COV-COLLATE, COV-CI-GATE, COV-INTEGRATION-SKIP]
**Depends on:** Phase 0
**Plans:** 7 plans

Plans:
- [ ] 01-01-PLAN.md — Test infrastructure: conftest.py MockPage, pytest/coverage config, pragma annotations
- [ ] 01-02-PLAN.md — matrix_ops.py 100% coverage (493 statements, pure Python)
- [ ] 01-03-PLAN.md — Non-Playwright modules: rate_limiter, engine_setup, cli, prompt_loader, status_writer, launch_report, tab_manager
- [ ] 01-04-PLAN.md — Playwright core: base.py, browser_utils, inject_utils, agent_fallback, retry_handler
- [ ] 01-05-PLAN.md — Platform drivers group 1: chatgpt, claude_ai, copilot, deepseek
- [ ] 01-06-PLAN.md — Platform drivers group 2: gemini, grok, perplexity, chatgpt_extractor
- [ ] 01-07-PLAN.md — Orchestrator async tests, config/collate gaps, CI --cov-fail-under=100 gate
