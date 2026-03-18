# Software Requirements Specification (SRS)

**Project:** Multi-AI Orchestrator Platform
**Version:** 4.1
**Date:** 2026-03-18
**Base Version:** multi-ai-skills/ (formerly solution-research-skill-260308A)

| Version | Date | Summary |
|---------|------|---------|
| 2.0 | 2026-03-13 | Generic restructuring: engine, orchestrator, consolidator, solution-researcher, domain knowledge |
| 3.0 | 2026-03-13 | Generic Comparator Skill + Python Matrix Engine (matrix_ops.py, matrix_builder.py) |
| 3.1 | 2026-03-14 | Rate Limiting Guardrails (rate_limiter.py, per-platform detection, staggered dispatch) |
| 3.2 | 2026-03-14 | Task-Name Output Organization + Auto-Collation (collate_responses.py, --task-name flag) |
| 4.0 | 2026-03-16 | 5-skill architecture: landscape-researcher, engine owned by orchestrator, comparator owns matrix scripts, self-improving skills, domain enrichment from both researchers |
| 4.1 | 2026-03-18 | Dependency bootstrap: setup.sh canonical installer; install.sh plugin hook delegate; SessionStart auto-install; orchestrator Phase 1 venv check |

---

## 1. Introduction

### 1.1 Purpose

This document specifies the software requirements for the Multi-AI Orchestrator Platform — a local automation system that submits prompts to 7 AI platforms in parallel, collects responses, and supports downstream synthesis, comparison, and domain knowledge enrichment workflows.

The system has evolved through six generations:
- **v2.0:** Decoupled engine + skills architecture; generic prompt handling
- **v3.0:** Added comparison matrix capabilities (Python XLSX engine + Comparator skill)
- **v3.1:** Added rate limiting guardrails to prevent platform throttling
- **v3.2:** Added task-name output organization and automatic raw response collation
- **v4.0:** 5-skill architecture with landscape-researcher; engine owned by orchestrator skill; self-improving skills with run logs; dual domain enrichment
- **v4.1:** Dependency bootstrap: `setup.sh` canonical installer; `install.sh` delegates to `setup.sh`; `SessionStart` hook auto-installs deps for plugin users; orchestrator Phase 1 venv check

### 1.2 Scope

The system submits user-provided prompts to 7 AI platforms in parallel (Claude.ai, ChatGPT, Copilot, Perplexity, Grok, DeepSeek, Gemini), extracts responses, collates them into an archive, and supports: generic consolidation, structured solution research (CIR), and comparison matrix maintenance. All orchestration is automated via Playwright/Python; synthesis, CIR production, and matrix judgment are performed by the host AI (Claude Code/Desktop).

### 1.3 Definitions

| Term | Definition |
|------|-----------|
| **Engine** | The Python/Playwright orchestration runtime managing Chrome, platforms, and extraction |
| **Skill** | A SKILL.md file containing workflow instructions for the host AI (Claude Code) |
| **Task type** | A specific use case (solution research, security audit, etc.) that provides a prompt template and consolidation guide |
| **Domain knowledge** | A .md file containing category-specific evaluation criteria, terminology, archetypes, and inference patterns |
| **Platform** | One of the 7 AI services (Claude.ai, ChatGPT, Copilot, Perplexity, Grok, DeepSeek, Gemini) |
| **CIR** | Consolidated Intelligence Report — structured output of the solution research task type |
| **Matrix** | XLSX comparison spreadsheet with platforms as columns and features/capabilities as rows |
| **Prompt-echo** | When a platform renders the submitted prompt on the page alongside the AI response |
| **Rate limiter** | The `rate_limiter.py` module tracking per-platform usage, enforcing budgets and cooldowns |
| **Task name** | A short label for an orchestration run; determines the output subdirectory (`reports/{task-name}/`) |
| **Archive** | The auto-generated `{task-name} - Raw AI Responses.md` file collating all platform responses |
| **Pre-flight check** | A budget/cooldown validation performed before launching a platform, to skip over-budget platforms early |
| **Landscape Report** | A 9-section Market Landscape Report produced by the landscape-researcher skill (v4.0) |
| **launch_report.py** | Python script that starts an HTTP server and opens `preview.html?report=<path>` to display a landscape report (v4.0) |
| **Self-Improve** | A phase in each skill where the skill appends a timestamped run log entry to its own SKILL.md after a successful run (v4.0) |
| **Run Log** | A section in each SKILL.md that accumulates timestamped entries from Self-Improve phases (v4.0) |
| **setup.sh** | The canonical one-time bootstrap script at the repo root; creates `skills/orchestrator/engine/.venv`, installs Python dependencies, runs `playwright install chromium`, and creates a `.env` template (v4.1) |
| **SessionStart hook** | A Claude Code plugin lifecycle hook defined in `hooks/hooks.json` that fires `install.sh` (which delegates to `setup.sh`) on the first session start (v4.1) |
| **.installed sentinel** | A file created by the `SessionStart` hook after successful setup; prevents `setup.sh` from being re-invoked on subsequent sessions (v4.1) |

---

## 2. System Overview

### 2.1 Current State (v4.0)

Three independent layers:

```
Layer 1: Engine (Python)        — Generic orchestration, platform automation, extraction,
                                   rate limiting, response collation (owned by orchestrator skill)
Layer 2: Skills (SKILL.md)      — Orchestrator (router + engine owner), Consolidator,
                                   Comparator (owns matrix scripts), Solution Researcher,
                                   Landscape Researcher
Layer 3: Domain Knowledge (.md) — Per-domain evaluation criteria, archetypes, inference patterns
```

### 2.2 System Context

```
User → Claude Code (host AI)
                │
        ┌───────┼────────────────────────────────┐
        │       │                                │
   Engine     Domain                          reports/
  (Python)  Knowledge (.md)               (output files)
        │
   Chrome (CDP) → 7 AI tabs
```

### 2.3 Operating Modes (v4.0 — Intent-Based Routing)

| Mode | Trigger | Pipeline |
|------|---------|---------|
| **Landscape Research** | User requests market landscape analysis | Orchestrator → Landscape Researcher → Engine → Consolidator → launch_report.py → Domain Enrichment |
| **Solution Research** | User explicitly requests product research | Orchestrator → Solution Researcher → Engine → Consolidator → Comparator → Domain Enrichment |
| **Comparator** | User requests matrix update directly | Orchestrator → Comparator (direct) |
| **Generic** | Any arbitrary prompt | Orchestrator → Engine → Consolidator |

The Orchestrator skill acts as a router (Phase 0 routing decision tree) and dispatches to the appropriate skill based on user intent.

---

## 3. Functional Requirements

### 3.1 Generic Orchestrator Engine

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-OE-01 | Accept a pre-built prompt via `--prompt` (literal text) or `--prompt-file` (file path) | Must |
| FR-OE-02 | Accept an optional condensed prompt via `--condensed-prompt` or `--condensed-prompt-file` for constrained platforms | Should |
| FR-OE-03 | Support `--mode DEEP\|REGULAR` to control platform configuration (timeouts, model selection) | Must |
| FR-OE-04 | Support `--platforms` to select a subset of the 7 platforms | Must |
| FR-OE-05 | Launch Chrome with persistent login context via CDP; reuse running Chrome if available | Must |
| FR-OE-06 | Run all selected platforms in true parallel via `asyncio` | Must |
| FR-OE-07 | For each platform: navigate, check rate limit, configure mode, inject prompt, send, poll completion (with rate limit detection each cycle), extract response, save to file | Must |
| FR-OE-08 | Write `status.json` with per-platform terminal status (complete, partial, failed, timeout, rate_limited) | Must |
| FR-OE-09 | Write each platform's raw response to `{Platform}-raw-response.md` in the output directory | Must |
| FR-OE-10 | Auto-extract prompt-echo detection signatures from the submitted prompt | Must |
| FR-OE-11 | Pass prompt-echo signatures to all platform classes for use during extraction | Must |
| FR-OE-12 | NOT contain any domain-specific or task-type-specific logic | Must |
| FR-OE-13 | Invoke browser-use Agent fallback when Playwright selectors fail (if ANTHROPIC_API_KEY is set) | Should |
| FR-OE-14 | Support `--fresh` flag to force-launch a new Chrome instance | Should |
| FR-OE-15 | Support `--headless` flag for headless execution | Should |
| FR-OE-16 | Support `--task-name` to route output to `reports/{task-name}/` subdirectory | Must |
| FR-OE-17 | Auto-collate all per-platform raw responses into a single `{task-name} - Raw AI Responses.md` archive after every run | Must |
| FR-OE-18 | Support `--tier free\|paid` to select rate limit budget tier | Must |
| FR-OE-19 | Perform pre-flight budget checks; skip over-budget platforms with `rate_limited` status before launch | Must |
| FR-OE-20 | Launch platforms in staggered order (configurable delay via `--stagger-delay`), ordered by remaining budget | Must |
| FR-OE-21 | Enforce per-platform cooldowns with exponential backoff after rate limit events | Must |
| FR-OE-22 | Persist usage state to `~/.chrome-playwright/rate-limit-state.json` across sessions | Must |
| FR-OE-23 | Support `--skip-rate-check` to bypass all rate limit guardrails | Should |
| FR-OE-24 | Support `--budget` to print budget summary and exit without running | Should |
| FR-OE-25 | All 7 platforms must detect rate limit conditions via `check_rate_limit()` on page load and during each poll cycle | Must |

### 3.2 Generic Orchestrator Skill

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-OS-01 | Accept a prompt (text or file path) from the user or calling skill | Must |
| FR-OS-02 | Accept mode (DEEP/REGULAR), task name, and optional platform subset | Must |
| FR-OS-03 | Verify Python environment and Chrome availability before running | Must |
| FR-OS-04 | Invoke the engine CLI with `--task-name` to organize output in a named subdirectory | Must |
| FR-OS-05 | Read `status.json` and report terminal statuses to the user | Must |
| FR-OS-06 | The engine auto-generates the raw archive; the skill reads and presents it | Must |
| FR-OS-07 | NOT perform any consolidation/synthesis | Must |

### 3.3 Generic Consolidator Skill

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CS-01 | Accept a raw responses archive (the engine's auto-generated archive file) | Must |
| FR-CS-02 | Accept an optional consolidation guide (.md file) defining the output structure | Should |
| FR-CS-03 | If no guide provided, use generic synthesis: consensus, disagreements, unique insights, source reliability | Must |
| FR-CS-04 | If a guide is provided, follow its prescribed output structure | Must |
| FR-CS-05 | Produce a consolidated report as a .md file | Must |
| FR-CS-06 | Include source reliability assessment (per-platform rating) | Must |
| FR-CS-07 | Propose domain knowledge enrichment (source reliability observations, cross-AI disagreements) if domain context provided | Should |
| FR-CS-08 | NOT contain domain-specific logic; the consolidation guide provides all domain context | Must |

### 3.4 Solution Researcher Skill

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-SR-01 | Accept: primary URL, scope context, optional additional URLs, optional GitHub URL, optional domain name | Must |
| FR-SR-02 | Load `prompt-template.md` and fill placeholders with user inputs | Must |
| FR-SR-03 | If domain specified, load `domains/{domain}.md` and append evaluation criteria to the prompt | Should |
| FR-SR-04 | Generate a condensed prompt (≤900 chars) for constrained platforms | Should |
| FR-SR-05 | Invoke the orchestrator skill with the built prompt and a descriptive `--task-name` | Must |
| FR-SR-06 | Invoke the consolidator skill with `consolidation-guide.md` | Must |
| FR-SR-07 | CIR structure: Executive Summary, Capability Groups, Assumptions/Gaps, Marketing Claims vs Demonstrated, Comparison-Ready Checklist, Source Reliability | Must |
| FR-SR-08 | After consolidation, auto-invoke the comparator skill if a matrix exists for the domain (Phase 5b) | Should |
| FR-SR-09 | After consolidation, propose additions to the domain knowledge file if new patterns were found | Should |
| FR-SR-10 | Present deliverables (raw archive + CIR + updated matrix) to the user | Must |
| FR-SR-11 | `prompt-template.md` must be category-agnostic (no DevOps-specific categories) | Must |

### 3.5 Landscape Researcher Skill (v4.0)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-LR-01 | Accept: domain name, scope context, optional constraints | Must |
| FR-LR-02 | Load `prompt-template.md` and fill placeholders with user inputs | Must |
| FR-LR-03 | If domain specified, load `domains/{domain}.md` and append evaluation criteria to the prompt | Should |
| FR-LR-04 | Invoke the orchestrator skill with the built prompt and a descriptive `--task-name` | Must |
| FR-LR-05 | Invoke the consolidator skill with `consolidation-guide.md` (9-section Market Landscape Report) | Must |
| FR-LR-06 | Report includes Top 20 commercial and Top 20 OSS solutions | Must |
| FR-LR-07 | Auto-launch HTML report viewer via `launch_report.py` after consolidation | Must |
| FR-LR-08 | `launch_report.py --no-browser` prints correctly URL-encoded path without opening browser | Must |
| FR-LR-09 | `launch_report.py` skips HTTP server start if port already in use | Must |
| FR-LR-10 | After run, propose domain knowledge enrichment (append-only, timestamped) with general domain knowledge | Should |
| FR-LR-11 | Append timestamped run log entry to own SKILL.md after successful run (Self-Improve phase) | Must |

### 3.6 Comparator Skill (Updated v4.0 — owns matrix scripts)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CM-01 | Accept: CIR path, matrix (.xlsx) path, domain name | Must |
| FR-CM-02 | Load domain knowledge file to understand evaluation categories and inference patterns | Must |
| FR-CM-03 | Read the CIR and identify its variant (A: rich narrative, or B: structured checklist) | Must |
| FR-CM-04 | Map each matrix feature to a tick decision (true/false); produce `features.json` | Must |
| FR-CM-05 | Identify new rows (features not yet in the matrix); produce `new-rows.json` | Should |
| FR-CM-06 | Invoke `matrix_ops.py add-platform` with `features.json` and `new-rows.json` | Must |
| FR-CM-07 | Invoke `matrix_ops.py reorder-columns` after adding a platform | Should |
| FR-CM-08 | Verify updated matrix via `matrix_ops.py scores` | Should |
| FR-CM-09 | Propose additions to domain knowledge (new archetypes, inference patterns, feature equivalences) | Should |
| FR-CM-10 | Present ranked scores and top platforms to the user | Must |

### 3.7 Matrix Engine (Updated v4.0 — moved to skills/comparator/)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-MX-01 | `matrix_ops.py` provides CLI + JSON stdout interface for all deterministic XLSX operations | Must |
| FR-MX-02 | Supported operations: `add-platform`, `reorder-columns`, `reorder-rows`, `reorder-categories`, `combo`, `verify`, `extract-features`, `scores`, `info` | Must |
| FR-MX-03 | Auto-detect XLSX layout (with or without title row) via `_Layout` class | Must |
| FR-MX-04 | Never hardcode styles — clone from existing cells | Must |
| FR-MX-05 | Unmerge before writing, re-merge after | Must |
| FR-MX-06 | Never use `ws.insert_rows()` — append or replace rows only | Must |
| FR-MX-07 | Validate features.json against matrix; report orphan (unmatched) features in output JSON | Must |
| FR-MX-08 | `matrix_builder.py` builds new XLSX matrices from JSON config with correct styling, formulas, and merges | Should |
| FR-MX-09 | All operations idempotent: running twice on the same input produces the same result | Should |

### 3.8 Domain Knowledge

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-DK-01 | Each domain is a single .md file in `domains/` | Must |
| FR-DK-02 | Required sections: Evaluation Categories, Key Terminology, Evaluation Criteria | Must |
| FR-DK-03 | Optional sections (populated over time): Platform Archetypes, Inference Patterns, CIR Evidence Rules, Matrix Categories, CIR-to-Matrix Cross-Reference, Feature Name Equivalences, New Row Guidelines, Priority Weights | Should |
| FR-DK-04 | Referenced by solution-researcher during prompt building | Must |
| FR-DK-05 | Referenced by consolidator during synthesis | Should |
| FR-DK-06 | Referenced by comparator for tick judgment and inference | Must |
| FR-DK-07 | Enrichable over time by all skills (landscape-researcher, solution-researcher, consolidator, comparator); enrichments are append-only and timestamped | Must |
| FR-DK-08 | Initial domain: `devops-platforms.md` | Must |

### 3.9 Platform Automation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-PA-01 | 7 platform classes (claude_ai, chatgpt, copilot, perplexity, grok, deepseek, gemini) | Must |
| FR-PA-02 | Each implements: `configure_mode`, `completion_check`, `extract_response`, `check_rate_limit` | Must |
| FR-PA-03 | Extraction must use generic prompt-echo detection (not hardcoded signatures) | Must |
| FR-PA-04 | Extraction fallback markers must be generic (Markdown headings `# `, `## `) not domain-specific | Must |
| FR-PA-05 | `check_rate_limit()` must scan for platform-specific rate limit UI indicators | Must |
| FR-PA-06 | browser-use Agent fallback on selector failure (when ANTHROPIC_API_KEY set) | Should |

### 3.10 v4.0 Cross-Cutting Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-NEW-1 | Orchestrator skill routes to landscape-researcher on landscape intent (Phase 0 routing decision tree) | Must |
| FR-NEW-2 | landscape-researcher produces 9-section Market Landscape Report (Top 20 commercial + Top 20 OSS) | Must |
| FR-NEW-3 | landscape-researcher auto-launches HTML report viewer via `launch_report.py` | Must |
| FR-NEW-4 | Both landscape-researcher and solution-researcher enrich `domains/{domain}.md` post-run (append-only, timestamped) | Must |
| FR-NEW-5 | Each of the 5 skills appends a timestamped run log entry to its own SKILL.md after every successful run (Self-Improve phase) | Must |
| FR-NEW-6 | `preview.html` is query-param driven: `?report=<path>` loads specified report; no param loads default | Must |
| FR-NEW-7 | All 5 SKILL.md files contain a Self-Improve phase and a Run Log section | Must |

### 3.11 v4.1 Dependency Bootstrap Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-SETUP-1 | `setup.sh` MUST create a virtual environment at `skills/orchestrator/engine/.venv` and install `playwright>=1.40.0` and `openpyxl>=3.1.0` | Must |
| FR-SETUP-2 | `setup.sh --with-fallback` MUST also install `browser-use==0.12.2`, `anthropic>=0.76.0`, and `fastmcp>=2.0.0` | Should |
| FR-SETUP-3 | `setup.sh` MUST be idempotent — re-running when `.venv` already exists MUST not fail | Must |
| FR-HOOK-1 | The `SessionStart` hook MUST auto-invoke `setup.sh` (via `install.sh`) on first plugin session start | Must |
| FR-HOOK-2 | The `SessionStart` hook MUST use an `.installed` sentinel file to prevent re-running setup on subsequent sessions | Must |
| FR-VENV-1 | `orchestrator/SKILL.md` Phase 1 MUST check for `.venv` before invoking the engine and MUST show `bash setup.sh` instructions if missing | Must |

---

## 4. Non-Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-01 | **Performance:** 7 platforms run in parallel after stagger; global timeout ≤50 min (DEEP) or ≤15 min (REGULAR) | Must |
| NFR-02 | **Reliability:** Each platform runs independently; one failure does not block others | Must |
| NFR-03 | **Extensibility:** Adding a new task type requires only new files under `skills/` and optionally `domains/`; no engine changes | Must |
| NFR-04 | **Extensibility:** Adding a new AI platform requires only a new file under `skills/orchestrator/engine/platforms/` and config/rate-limit entries | Must |
| NFR-05 | **Portability:** Runs on macOS, Linux, Windows with Python 3.11+ and Chrome installed | Should |
| NFR-06 | **Graceful degradation:** If ANTHROPIC_API_KEY not set, Agent fallback is disabled silently | Must |
| NFR-07 | **Idempotency:** Orchestrator can be re-run; Chrome reuse via CDP preserves logins | Should |
| NFR-08 | **Observability:** Structured logging; `status.json` for machine-readable results; `agent-fallback-log.json` for fallback events; `rate-limit-state.json` for usage state | Must |
| NFR-09 | **Security:** No credentials stored in code; Chrome profile reuse preserves platform logins without exposing passwords | Must |
| NFR-10 | **Rate limit safety:** System must not submit requests to a platform when its rolling-window budget is exhausted | Must |
| NFR-11 | **Output organization:** All run outputs must be isolated in a named subdirectory under `reports/`; the root `reports/` directory is not written to directly | Must |
| NFR-12 | **XLSX integrity:** All 6 Golden Rules (no hardcoded styles, unmerge/re-merge, no insert_rows, row-type detection, cache styles before reorder, validate features) must be enforced by code, not documentation | Must |

---

## 5. Use Cases

### UC-01: Generic Multi-AI Query

**Actor:** User via Claude Code
**Flow:**
1. User provides a prompt: "Compare React vs Vue vs Svelte for a large enterprise app"
2. Orchestrator skill writes prompt to temp file
3. Engine invoked: `--prompt-file /tmp/prompt.md --mode REGULAR --task-name "React vs Vue vs Svelte"`
4. Engine pre-flight checks all 7 platforms; staggered launch; 7 responses collected
5. Engine auto-generates archive: `reports/React vs Vue vs Svelte/React vs Vue vs Svelte - Raw AI Responses.md`
6. User optionally invokes consolidator skill to synthesize

### UC-02: Solution Research (DevOps Product)

**Actor:** User via Claude Code
**Flow:**
1. User: "Research Facets.cloud — it's a DevOps internal developer platform"
2. Solution-researcher: URL=facets.cloud, scope="DevOps IDP", domain=devops-platforms
3. Skill builds prompt from `prompt-template.md` + domain criteria
4. Engine runs with `--task-name "Facets.cloud"` → archive auto-generated
5. Consolidator produces CIR using `consolidation-guide.md`
6. Comparator auto-invoked: CIR → tick decisions → `matrix_ops.py add-platform` → updated .xlsx
7. Deliverables: archive + CIR + updated matrix + proposed domain enrichments

### UC-03: Solution Research (New Domain)

**Actor:** User via Claude Code
**Flow:**
1. User: "Research Monday.com — it's a project management tool"
2. No `domains/project-management.md` exists — skill proceeds without domain knowledge
3. After consolidation, skill creates `domains/project-management.md` from findings
4. Next research run in this domain uses the enriched file

### UC-04: Budget Check Before Run

**Actor:** User via Claude Code
**Flow:**
1. User or skill calls: `python3 skills/orchestrator/engine/orchestrator.py --prompt "test" --budget --tier free`
2. Engine prints per-platform budget table with remaining requests, next available time, cooldown
3. User decides whether to proceed and with which platforms

### UC-05: Standalone Comparison Matrix Update

**Actor:** User via Claude Code
**Flow:**
1. User provides an existing CIR and the matrix path
2. Comparator skill loads domain knowledge + matrix layout
3. LLM reads CIR → produces `features.json`
4. `matrix_ops.py add-platform` updates XLSX
5. `matrix_ops.py reorder-columns` sorts by score
6. Updated matrix delivered to user

### UC-06: Market Landscape Research (v4.0)

**Actor:** User via Claude Code
**Flow:**
1. User: "Give me a market landscape analysis of DevOps platforms"
2. Orchestrator routes to landscape-researcher (Phase 0 routing)
3. Landscape-researcher builds prompt from `prompt-template.md` + domain criteria
4. Engine runs with `--task-name "DevOps Platforms Landscape"` → archive auto-generated
5. Consolidator produces 9-section Market Landscape Report (Top 20 commercial + Top 20 OSS)
6. `launch_report.py` auto-launches HTML report viewer via `preview.html?report=<path>`
7. landscape-researcher proposes domain knowledge enrichment (append-only)
8. Skill appends timestamped run log entry to own SKILL.md

### UC-07: Adding a New Task Type

**Actor:** Developer
**Flow:**
1. Create `skills/security-auditor/SKILL.md` with audit workflow
2. Create `skills/security-auditor/prompt-template.md`
3. Create `skills/security-auditor/consolidation-guide.md`
4. No engine changes required

---

## 6. Input/Output Specifications

### 6.1 Engine CLI Interface

**Input:**
```
python3 skills/orchestrator/engine/orchestrator.py \
    --prompt-file <path>              # Required (or --prompt <text>)
    --task-name "<name>"              # Recommended — output to reports/<name>/
    --condensed-prompt <text>         # Optional
    --mode DEEP|REGULAR               # Default: REGULAR
    --platforms all                    # Default: all
    --chrome-profile Default          # Default: Default
    --headless                        # Default: false
    --fresh                           # Default: false
    --tier free|paid                  # Default: free
    --skip-rate-check                 # Default: false
    --budget                          # Print budget table and exit
    --stagger-delay <seconds>         # Default: 5
```

**Output directory structure:**
```
reports/{task-name}/
├── status.json                             # Machine-readable results
├── Claude.ai-raw-response.md
├── ChatGPT-raw-response.md
├── Microsoft-Copilot-raw-response.md
├── Perplexity-raw-response.md
├── Grok-raw-response.md
├── DeepSeek-raw-response.md
├── Google-Gemini-raw-response.md
├── {task-name} - Raw AI Responses.md      # Auto-generated archive
└── agent-fallback-log.json                # Only if fallback events occurred
```

**Side effects:**
- `~/.chrome-playwright/rate-limit-state.json` — updated after every run

### 6.2 status.json Format

```json
{
  "timestamp": "2026-03-14T14:30:00",
  "mode": "REGULAR",
  "platforms": [
    {
      "platform": "claude_ai",
      "display_name": "Claude.ai",
      "status": "complete",
      "chars": 15234,
      "file": "reports/My Task/Claude.ai-raw-response.md",
      "mode_used": "Sonnet",
      "error": "",
      "duration_s": 45.3
    }
  ]
}
```

### 6.3 Rate Limit State File Format

```json
{
  "version": 1,
  "tier": "free",
  "updated_at": "2026-03-14T14:30:00",
  "usage": {
    "claude_ai": {
      "recent_requests": [
        {"ts": 1741960200.0, "mode": "REGULAR", "status": "complete", "duration_s": 45.3}
      ],
      "last_rate_limited_at": null,
      "consecutive_rate_limits": 0
    }
  }
}
```

### 6.4 matrix_ops.py CLI Interface

```bash
python3 skills/comparator/matrix_ops.py <operation> [options]
```

| Operation | Key Options | Output |
|-----------|-------------|--------|
| `info` | `--src <path>` | JSON: layout, platform count, row count |
| `extract-features` | `--src <path>` | JSON: list of {feature, category, priority} |
| `add-platform` | `--src <path> --platform <name> --features features.json [--new-rows new-rows.json]` | JSON: ticks_applied, new_rows_added, orphans |
| `reorder-columns` | `--src <path>` | JSON: new column order |
| `scores` | `--src <path>` | JSON: {platform: score} sorted descending |
| `verify` | `--src <path> --features features.json` | JSON: match_count, orphan_count |
| `combo` | `--src <path> --name <name> --platform-a <p1> --platform-b <p2>` | JSON: ticks merged |
| `reorder-rows` | `--src <path> --order <file>` | JSON: rows reordered |
| `reorder-categories` | `--src <path> --order <file>` | JSON: categories reordered |

### 6.5 Domain Knowledge File Format

```markdown
# Domain Knowledge: {Domain Name}

## Evaluation Categories
- Category 1
- Category 2

## Key Terminology
- Term: definition

## Evaluation Criteria
1. Criterion 1 (weight rationale)

## Platform Archetypes          ← optional, added by comparator
## Inference Patterns           ← optional, added by comparator
## CIR Evidence Rules           ← optional, added by comparator
## Matrix Categories            ← optional, added by comparator
## Priority Weights             ← optional, added by comparator
```

---

## 7. Constraints and Assumptions

### 7.1 Constraints

1. Chrome must be installed on the host machine
2. User must be logged into AI platforms via Chrome (persistent profile)
3. Some platforms rate-limit or block headless browsers
4. Cross-origin iframe content (ChatGPT Deep Research) requires CDP-level access
5. Grok may require condensed prompts due to physical typing constraints
6. The host AI (Claude Code) has a context window limit; raw response files are read externally
7. Matrix XLSX files must not be opened in Excel/Numbers while `matrix_ops.py` is running
8. Rate limit budgets are conservative estimates based on observed behavior; actual limits may differ per account and subscription level
9. The `rate-limit-state.json` is shared across all projects on the machine; budget consumption from one project affects others

### 7.2 Assumptions

1. The user has active subscriptions/access to the 7 AI platforms
2. Chrome supports `--remote-debugging-port` for CDP
3. Platform UIs change infrequently (weeks/months between breaking changes)
4. The browser-use Agent fallback can handle minor UI changes
5. The host AI (Claude Code) is capable of reading files and following SKILL.md instructions
6. `openpyxl` correctly handles the XLSX files produced by Excel/Numbers/Google Sheets
7. The LLM performing CIR → tick decisions has sufficient reasoning capability (Claude Sonnet or equivalent)
