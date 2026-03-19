# MultAI — Contributor Guide

**Version:** 0.2.260319A Alpha | **Date:** 2026-03-18

> **Looking for the end-user guide?** See [USER-GUIDE.md](USER-GUIDE.md).

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Installation & Setup](#3-installation--setup)
4. [Project Structure](#4-project-structure)
5. [Quick Start](#5-quick-start)
6. [Skills Reference](#6-skills-reference)
   - 6.1 [Multi-AI Orchestrator](#61-multi-ai-orchestrator-skill)
   - 6.2 [Solution Researcher](#62-solution-researcher-skill)
   - 6.3 [Landscape Researcher](#63-landscape-researcher-skill)
   - 6.4 [Comparator](#64-comparator-skill)
   - 6.5 [Consolidator](#65-consolidator-skill)
7. [Engine CLI Reference](#7-engine-cli-reference)
8. [Platform Reference](#8-platform-reference)
9. [Rate Limiting](#9-rate-limiting)
10. [Agent Fallback (browser-use)](#10-agent-fallback-browser-use)
11. [Viewing Reports](#11-viewing-reports)
12. [Domain Knowledge](#12-domain-knowledge)
13. [Running Tests](#13-running-tests)
14. [CI/CD & Make Targets](#14-cicd--make-targets)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Overview

**MultAI** is a local desktop automation platform that submits research prompts to multiple AI services simultaneously — Claude.ai, ChatGPT, Microsoft Copilot, Perplexity, Grok, DeepSeek, and Google Gemini — extracts their responses via Playwright CDP automation, and synthesizes the results into structured deliverables.

It is invoked entirely through **Claude Code** using a set of five skills, each targeting a different research workflow.

```
You (Claude Code)
      │
      ▼
┌─────────────────────────────────────────────┐
│  Multi-AI Orchestrator (routing layer)       │
│  ┌────────────┐  ┌───────────────────────┐  │
│  │ landscape- │  │ solution-researcher   │  │
│  │ researcher │  │ (product deep-dive)   │  │
│  └────────────┘  └───────────────────────┘  │
│  ┌────────────┐  ┌───────────────────────┐  │
│  │ comparator │  │ Direct multi-AI       │  │
│  │ (XLSX ops) │  │ + consolidator        │  │
│  └────────────┘  └───────────────────────┘  │
└─────────────────────────────────────────────┘
      │
      ▼
Playwright Engine  ──►  7 AI Platforms  ──►  reports/
```

### Key Capabilities

| Capability | Detail |
|-----------|--------|
| **Parallel submission** | All 7 platforms run concurrently via `asyncio.gather()` |
| **Rate limiting** | Per-platform budget + cooldown + daily cap, persisted across sessions |
| **Agent fallback** | If a UI selector fails, a vision-based `browser-use` agent takes over |
| **DEEP mode** | Activates Deep Research / Research mode on each platform |
| **REGULAR mode** | Standard chat mode (faster, counts against smaller budget) |
| **Prompt echo filtering** | Automatically detects and strips echoed prompts from extractions |
| **Condensed prompt** | Supplies a shorter prompt to constrained platforms (Grok ≤900 chars) |
| **XLSX comparator** | Maintains a capability matrix across platforms, auto-scores and reorders |
| **Report viewer** | `preview.html?report=<path>` renders any Markdown report with charts |

---

## 2. Prerequisites

### Required

| Requirement | Notes |
|-------------|-------|
| **macOS** (primary) or Linux | Windows is untested |
| **Python 3.11+** | Python 3.13 recommended (required for agent fallback via `browser-use`) |
| **Google Chrome** | Must be installed at `/Applications/Google Chrome.app` |
| **Active logins** | You must be logged in to each AI platform you want to use |
| **Claude Code** | Skills are invoked by Claude Code as the host AI |

### Optional (for Agent Fallback)

| Requirement | Notes |
|-------------|-------|
| `ANTHROPIC_API_KEY` | Enables Claude Sonnet as the fallback agent LLM |
| `GOOGLE_API_KEY` | Enables Gemini 2.0 Flash as the fallback agent LLM (free tier available) |

If neither key is set, the fallback is silently disabled and original Playwright exceptions propagate normally.

### AI Platform Accounts

Log in to these platforms in your regular Chrome profile before running:

| Platform | URL | Notes |
|----------|-----|-------|
| Claude.ai | https://claude.ai | Pro plan recommended for DEEP mode |
| ChatGPT | https://chat.openai.com | Plus plan for Deep Research |
| Microsoft Copilot | https://copilot.microsoft.com | Free tier works |
| Perplexity | https://www.perplexity.ai | Pro for Deep Research |
| Grok | https://grok.com | Requires X/Twitter account |
| DeepSeek | https://chat.deepseek.com | Free tier works |
| Google Gemini | https://gemini.google.com | Google account required |

---

## 3. Installation & Setup

### 3.1 Clone the Repository

```bash
git clone https://github.com/alo-exp/multai.git
cd multai
```

### 3.2 Install Core Dependencies

Run the canonical bootstrap script from the repo root:

```bash
bash setup.sh
```

This creates a virtual environment at `skills/orchestrator/engine/.venv`, installs `playwright>=1.40.0` and `openpyxl>=3.1.0`, runs `playwright install chromium`, and creates a `.env` template.

> **Plugin install users:** If you installed via `claude plugin install`, dependencies are installed automatically on the first session start via the `SessionStart` hook (hook → `install.sh` → `setup.sh`). No manual step is needed.

> **skills.sh install users:** If you installed via `npx skills add alo-exp/multai`, run `bash setup.sh` manually after install. The orchestrator Phase 1 will detect a missing `.venv` and prompt you with instructions if you forget.

### 3.3 Install Agent Fallback Dependencies (Optional)

To also install the vision-based `browser-use` agent fallback (requires Python 3.13):

```bash
bash setup.sh --with-fallback
```

This installs `browser-use==0.12.2`, `anthropic>=0.76.0`, and `fastmcp>=2.0.0` into the same `.venv` at `skills/orchestrator/engine/.venv`.

The orchestrator auto-detects this venv and enables fallback if present alongside a valid API key.

### 3.4 Set API Keys (Optional)

```bash
# In your shell profile (~/.zshrc or ~/.bashrc):
export GOOGLE_API_KEY="your-gemini-api-key"     # Free from aistudio.google.com
export ANTHROPIC_API_KEY="your-anthropic-key"   # From console.anthropic.com
```

### 3.5 Register Skills with Claude Code

Add the skills to Claude Code's configuration (`.claude/launch.json` is already present in the repo):

```bash
# Verify skills are loadable:
cat .claude/launch.json
```

The skills are invoked by name inside Claude Code conversations — no additional registration step is required beyond having the project open.

---

## 4. Project Structure

```
multai/
│
├── skills/
│   ├── orchestrator/           # Entry-point skill + Playwright engine
│   │   ├── SKILL.md            # Routing logic + all phases
│   │   ├── platform-setup.md   # Per-platform injection/extraction notes
│   │   └── engine/
│   │       ├── orchestrator.py     # Main CLI — runs all platforms
│   │       ├── config.py           # Platform URLs, timeouts, rate limits
│   │       ├── rate_limiter.py     # Budget/cooldown/backoff engine
│   │       ├── agent_fallback.py   # browser-use vision fallback
│   │       ├── prompt_echo.py      # Echo detection utilities
│   │       ├── collate_responses.py# Auto-archive raw responses
│   │       ├── utils.py            # Shared helpers
│   │       ├── platforms/          # One file per AI platform
│   │       │   ├── base.py         # BasePlatform — shared lifecycle
│   │       │   ├── claude_ai.py
│   │       │   ├── chatgpt.py
│   │       │   ├── copilot.py
│   │       │   ├── perplexity.py
│   │       │   ├── grok.py
│   │       │   ├── deepseek.py
│   │       │   └── gemini.py
│   │       └── .venv/          # Optional Python 3.13 venv for browser-use
│   │
│   ├── solution-researcher/    # Product deep-dive research skill
│   │   ├── SKILL.md
│   │   ├── prompt-template.md  # Parametrized research prompt
│   │   └── consolidation-guide.md
│   │
│   ├── landscape-researcher/   # Market landscape / ecosystem survey skill
│   │   ├── SKILL.md
│   │   ├── prompt-template.md
│   │   ├── consolidation-guide.md
│   │   └── launch_report.py    # HTTP server + browser opener for preview
│   │
│   ├── comparator/             # XLSX capability matrix skill
│   │   ├── SKILL.md
│   │   ├── matrix_ops.py       # All matrix operations (add, score, reorder…)
│   │   └── matrix_builder.py   # Build a matrix from scratch (JSON → XLSX)
│   │
│   └── consolidator/           # AI response synthesis skill
│       └── SKILL.md
│
├── domains/
│   └── devops-platforms.md     # Shared domain knowledge (enriched over time)
│
├── docs/
│   ├── SRS.md                  # Software Requirements Specification
│   ├── Architecture-and-Design.md
│   ├── Test-Strategy-and-Plan.md
│   └── CICD-Strategy-and-Plan.md
│
├── reports/                    # All run outputs land here
│   ├── preview.html            # Report viewer (query-param driven)
│   └── <task-name>/
│       ├── <Platform>-raw-response.md  (one per platform)
│       ├── status.json
│       ├── <task-name> - Raw AI Responses.md  (auto-collated archive)
│       └── agent-fallback-log.json  (if fallback was triggered)
│
├── tests/                      # pytest unit test suite (96 tests)
│   ├── fixtures/               # Sample prompts, responses, status files
│   ├── test_prompt_echo.py
│   ├── test_rate_limiter.py
│   ├── test_collate_responses.py
│   ├── test_config.py
│   ├── test_orchestrator_args.py
│   ├── test_matrix_ops.py
│   └── test_launch_report.py
│
├── setup.sh                    # Canonical bootstrap — creates .venv, installs deps
├── install.sh                  # Plugin hook delegate → setup.sh
├── CHANGELOG.md
├── USER-GUIDE.md               # End-user guide (non-technical)
├── CONTRIBUTOR-GUIDE.md        # This file — technical contributor reference
└── .gitignore
```

---

## 5. Quick Start

### 5.1 Ask a Question Across All 7 AIs

Inside a Claude Code conversation with this project open:

```
What are the main trade-offs between microservices and monoliths?
```

The orchestrator skill routes this to a **direct multi-AI run** (no specialist skill needed), submits to all 7 platforms, and consolidates the answers.

### 5.2 Research a Product

```
Research Humanitec.com — I want a Competitive Intelligence Report covering their IDP capabilities.
```

Routes to **solution-researcher** → builds the full prompt → submits to 7 AIs in DEEP mode → consolidates into a CIR.

### 5.3 Map a Market Landscape

```
I need a market landscape analysis of the Internal Developer Platform space.
```

Routes to **landscape-researcher** → submits landscape prompt → produces a 9-section Market Landscape Report.

### 5.4 Update the Comparison Matrix

```
Add Spinnaker to the comparison matrix based on the latest CIR.
```

Routes to **comparator** → reads the CIR → extracts feature ticks → updates the XLSX → reorders by score.

### 5.5 Run the Engine Directly (CLI)

```bash
python3 skills/orchestrator/engine/orchestrator.py \
  --prompt "What is 2+2?" \
  --mode REGULAR \
  --task-name "my-test" \
  --platforms claude_ai,chatgpt
```

---

## 6. Skills Reference

Skills are invoked automatically by Claude Code based on your intent. You never call them by name — just describe what you want to do and the orchestrator routes correctly.

---

### 6.1 Multi-AI Orchestrator Skill

**File:** `skills/orchestrator/SKILL.md`

The primary entry point. Routes all requests and owns the Playwright engine.

#### Routing Logic

| Your intent | Routed to |
|-------------|-----------|
| "landscape" / "market map" / "ecosystem survey" / "Gartner-style" | `landscape-researcher` |
| Product URL + research / "competitive intelligence" / "CIR" | `solution-researcher` |
| "comparison matrix" / "add platform" / "update matrix" / "combo column" | `comparator` |
| Anything else (general question, arbitrary multi-AI task) | Direct multi-AI → `consolidator` |

#### Phases (Direct Multi-AI Path)

| Phase | What happens |
|-------|-------------|
| **0** | Route decision announced — accept or override |
| **1** | Prompt confirmed / built |
| **2** | Pre-flight: rate limit check, budget display |
| **3** | Engine invoked: `orchestrator.py --task-name …` |
| **4** | Results reviewed: per-platform status table |
| **5** | Consolidator synthesizes responses into final answer |
| **6** | Self-improve: SKILL.md Run Log updated |

#### Override Routing

If the auto-routing is wrong, tell Claude Code explicitly:

```
Research Humanitec.com — but run it as a direct multi-AI question, not as solution-researcher.
```

---

### 6.2 Solution Researcher Skill

**File:** `skills/solution-researcher/SKILL.md`

Produces a **Competitive Intelligence Report (CIR)** for a specific product or vendor.

#### Usage

```
Research <ProductName> / <URL>.
[Optional: focus on <specific angle>]
[Optional: include comparison against <competitor>]
```

#### What it produces

- **CIR (Variant A or B):** Full structured report covering capabilities, architecture, pricing, integrations, strengths/weaknesses, and competitive positioning
- **Raw AI Responses archive:** All 7 responses collated as a single Markdown file
- **Optional: XLSX update** — routes to comparator to tick the matrix

#### Phases

| Phase | What happens |
|-------|-------------|
| **1** | Confirm product + scope |
| **2** | Build the full research prompt from `prompt-template.md` |
| **3** | Pre-flight rate limit check |
| **4** | Engine run (DEEP mode, all platforms) |
| **5a** | Consolidate into CIR |
| **5b** | Optional: update comparison matrix |
| **6** | Domain knowledge enrichment (proposed, requires approval) |
| **7** | Self-improve |

#### Prompt Template Parameters

Defined in `skills/solution-researcher/prompt-template.md`:

| Placeholder | Example value |
|-------------|---------------|
| `[PRODUCT_NAME]` | `Humanitec` |
| `[PRODUCT_URL]` | `https://humanitec.com` |
| `[FOCUS_AREAS]` | `IDP capabilities, Kubernetes integration, pricing` |

---

### 6.3 Landscape Researcher Skill

**File:** `skills/landscape-researcher/SKILL.md`

Produces a **9-section Market Landscape Report** for a solution category.

#### Usage

```
Research the [category] landscape.
[Optional: focus on [audience] — e.g. "platform engineering teams"]
[Optional: scope to [modifiers] — e.g. "open-source only", "enterprise focus"]
```

#### What it produces

- **Market Landscape Report** with: Executive Summary, Market Definition, Vendor Landscape Map, Capability Taxonomy, Buyer Guidance, Emerging Trends, Risks, Vendor Profiles, and Strategic Recommendations
- **Domain knowledge additions** (proposed, requires approval)

#### Viewing the Report

After the skill completes:

```bash
python3 skills/landscape-researcher/launch_report.py \
  --report-dir reports/my-landscape-run \
  --report-file "Platform Engineering Solutions - Market Landscape Report.md"
```

This starts a local HTTP server and opens `preview.html?report=<path>` in your browser with rendered Markdown and charts.

#### Prompt Template Parameters

| Placeholder | Example value |
|-------------|---------------|
| `[SOLUTION_CATEGORY]` | `Internal Developer Platforms` |
| `[TARGET_AUDIENCE]` | `platform engineering teams` |
| `[SCOPE_MODIFIERS]` | `include open-source and commercial tools` |

---

### 6.4 Comparator Skill

**File:** `skills/comparator/SKILL.md`

Maintains a capability comparison matrix as an XLSX file.

#### Usage

```
Add [PlatformName] to the comparison matrix.
[Provide CIR or feature list]
```

```
Reorder the matrix columns by score.
```

```
Create a combo column for [PlatformA] + [PlatformB].
```

#### Matrix Operations

All operations go through `skills/comparator/matrix_ops.py`:

| Command | Purpose | Example |
|---------|---------|---------|
| `info` | Show matrix structure | `matrix_ops.py info --src matrix.xlsx` |
| `extract-features` | List all features as JSON | `matrix_ops.py extract-features --src matrix.xlsx` |
| `add-platform` | Add a new column with ticks | `matrix_ops.py add-platform --src … --platform "Name" --features f.json` |
| `scores` | Show ranked scores | `matrix_ops.py scores --src matrix.xlsx` |
| `reorder-columns` | Sort columns by score | `matrix_ops.py reorder-columns --src … --out …` |
| `combo` | Create A+B merged column | `matrix_ops.py combo --src … --name "A+B" --platform-a A --platform-b B` |
| `verify` | Check tick consistency | `matrix_ops.py verify --src matrix.xlsx` |

#### Building a Matrix from Scratch

Use `matrix_builder.py` with a JSON config:

```json
{
  "title": "DevOps Platforms Comparison Matrix",
  "categories": [
    {
      "name": "1. Deployment",
      "features": [
        {"name": "GitOps-based deployment", "priority": "High"},
        {"name": "Canary deployments", "priority": "High"}
      ]
    }
  ],
  "platforms": [
    {"name": "ArgoCD", "features": ["GitOps-based deployment", "Canary deployments"]},
    {"name": "Flux",   "features": ["GitOps-based deployment"]}
  ]
}
```

```bash
python3 skills/comparator/matrix_builder.py --config build.json --out matrix.xlsx
```

#### The 6 Golden Rules (enforced in code)

1. Never hardcode styles — clone from existing cells
2. Unmerge before writing, re-merge after
3. Never use `ws.insert_rows()` — corrupts row metadata
4. Row type detection via col A value + col B presence
5. Cache styles before any column reorder
6. Validate features against matrix before saving (orphan check)

---

### 6.5 Consolidator Skill

**File:** `skills/consolidator/SKILL.md`

Synthesizes raw AI responses from the archive into a structured final deliverable.

The consolidator is invoked automatically by other skills — you rarely need to invoke it directly. When invoked directly, provide:

- The path to a raw archive (`*-Raw AI Responses.md`)
- The name of the consolidation guide to use (or "generic")

#### Consolidation Guides

| Guide | Used by | Output |
|-------|---------|--------|
| `skills/solution-researcher/consolidation-guide.md` | solution-researcher | CIR (Variant A or B) |
| `skills/landscape-researcher/consolidation-guide.md` | landscape-researcher | 9-section Market Landscape Report |
| *(generic)* | orchestrator direct path | Free-form synthesis |

---

## 7. Engine CLI Reference

```
python3 skills/orchestrator/engine/orchestrator.py [OPTIONS]
```

### Required (mutually exclusive)

| Flag | Description |
|------|-------------|
| `--prompt TEXT` | Literal prompt text passed inline |
| `--prompt-file PATH` | Path to a pre-built `.md` or `.txt` prompt file |

### Prompt Options

| Flag | Description |
|------|-------------|
| `--condensed-prompt TEXT` | Short version of the prompt for constrained platforms (Grok) |
| `--condensed-prompt-file PATH` | Path to condensed prompt file (≤900 chars for Grok) |
| `--prompt-sigs TEXT` | Comma-separated echo-detection signatures (auto-detected if omitted) |

### Run Options

| Flag | Default | Description |
|------|---------|-------------|
| `--mode {REGULAR,DEEP}` | `REGULAR` | Chat mode vs Deep Research mode |
| `--task-name TEXT` | *(none)* | Names the run; output goes to `reports/{task-name}/` |
| `--output-dir PATH` | `reports/` | Custom output directory (overridden by `--task-name`) |
| `--platforms TEXT` | `all` | Comma-separated platform names, or `all` |
| `--tier {free,paid}` | `free` | Rate limit tier (affects budget thresholds) |
| `--stagger-delay N` | `5` | Seconds between staggered platform launches |

### Platform & Chrome Options

| Flag | Default | Description |
|------|---------|-------------|
| `--chrome-profile TEXT` | `Default` | Chrome profile directory name |
| `--headless` | *(off)* | Run headlessly (not recommended — some platforms block it) |
| `--fresh` | *(off)* | Kill and relaunch Chrome (default: reuse running instance) |

### Rate Limit Options

| Flag | Description |
|------|-------------|
| `--budget` | Print rate limit budget summary and exit (no run) |
| `--skip-rate-check` | Bypass all pre-flight rate limit checks (use with caution) |

### Platform Names

Use these names with `--platforms`:

| Name | Platform |
|------|---------|
| `claude_ai` | Claude.ai |
| `chatgpt` | ChatGPT |
| `copilot` | Microsoft Copilot |
| `perplexity` | Perplexity |
| `grok` | Grok |
| `deepseek` | DeepSeek |
| `gemini` | Google Gemini |

### Examples

```bash
# Run a quick question on Claude.ai only
python3 skills/orchestrator/engine/orchestrator.py \
  --prompt "What is Kubernetes?" \
  --platforms claude_ai \
  --task-name "k8s-explainer"

# Run a full research prompt in DEEP mode across all platforms
python3 skills/orchestrator/engine/orchestrator.py \
  --prompt-file skills/solution-researcher/prompt-template.md \
  --mode DEEP \
  --task-name "humanitec-research" \
  --tier paid

# Run with condensed prompt for Grok
python3 skills/orchestrator/engine/orchestrator.py \
  --prompt-file prompts/full-research.md \
  --condensed-prompt-file prompts/condensed-grok.txt \
  --task-name "research-run"

# Check current budget before running
python3 skills/orchestrator/engine/orchestrator.py \
  --prompt "x" --budget --tier free

# Run specific platforms, skip rate checks
python3 skills/orchestrator/engine/orchestrator.py \
  --prompt "Explain GitOps" \
  --platforms claude_ai,chatgpt,gemini \
  --skip-rate-check \
  --task-name "gitops-comparison"
```

---

## 8. Platform Reference

### Injection Methods

Each platform requires a different method to insert text into its input field:

| Platform | Input type | Method | Notes |
|----------|-----------|--------|-------|
| Claude.ai | `contenteditable` div | `execCommand('insertText')` | Standard |
| ChatGPT | `contenteditable` div | `execCommand('insertText')` | Standard |
| Copilot | `contenteditable` div | `execCommand('insertText')` | Avoid microphone button |
| Perplexity | `contenteditable` div | `execCommand('insertText')` | Standard |
| **Grok** | **React `<textarea>`** | **`page.type()` (physical)** | JS injection fails silently; use condensed prompt ≤900 chars |
| **DeepSeek** | **React `<textarea>`** | **`page.fill()` + event dispatch** | `execCommand` fails; requires React state events |
| Gemini | `contenteditable` div | `execCommand('insertText')` | Silently truncates long prompts — verify injected length |

### Response Wait Times

#### REGULAR Mode

| Platform | Typical | Maximum |
|----------|---------|---------|
| All platforms | 1–5 min | 15 min |

#### DEEP Mode

| Platform | Typical | Maximum |
|----------|---------|---------|
| Perplexity, Grok, DeepSeek | 1–5 min | 10 min |
| Google Gemini Deep Research | 5–15 min | 25 min |
| Claude.ai Research mode | 5–40 min | 50 min |
| Microsoft Copilot Deep Research | 15–40 min | 50 min |
| ChatGPT Deep Research | 20–40 min | 50 min |

### Platform-Specific Hazards

| Platform | Hazard | How it's handled |
|----------|--------|-----------------|
| **Claude.ai** | Quota shared with Claude Code. NEVER use Opus. | Engine always selects Sonnet; quota monitored |
| **ChatGPT** | REGULAR mode DOM shows response twice | Extractor slices at first "End of Report." marker |
| **Copilot** | Microphone button near input area — if clicked, destroys session | Engine uses `aria-label` filtering to avoid it |
| **Grok** | Physical typing only; long prompts time out | Condensed prompt ≤900 chars always provided |
| **DeepSeek** | May produce "URL Access Failure" for target URLs | Engine detects this; marks as failed |
| **Gemini** | "At full capacity" error in DEEP mode | Engine retries 3× with 30s waits |
| **Gemini** | Silently truncates long prompts | Engine verifies injected length after paste |

---

## 9. Rate Limiting

The engine enforces per-platform rate limits to avoid hitting service caps. Limits are tracked in `~/.chrome-playwright/rate-limit-state.json` and persist across sessions.

### Viewing the Budget

```bash
python3 skills/orchestrator/engine/orchestrator.py --prompt "x" --budget
```

**Free tier (default):**

```
  Rate Limit Budget Summary (tier: free, mode: REGULAR)
========================================================================
  Platform               Used   Budget   Next Available   Cooldown
------------------------------------------------------------------------
  Claude.ai              0/12  12 left              now         5m
  ChatGPT                 0/8   8 left              now         5m
  Microsoft Copilot       0/5   5 left              now        10m
  Perplexity             0/50  50 left              now        30s
  Grok                    0/8   8 left              now         5m
  DeepSeek                0/8   8 left              now         1m
  Google Gemini           0/4   4 left              now        15m
========================================================================
```

**Paid tier (`--tier paid`):**

```
  Rate Limit Budget Summary (tier: paid, mode: REGULAR)
========================================================================
  Platform               Used   Budget   Next Available   Cooldown
------------------------------------------------------------------------
  Claude.ai              0/40  40 left              now         2m
  ChatGPT                0/80  80 left              now         1m
  Microsoft Copilot      0/15  15 left              now         5m
  Perplexity            0/200 200 left              now        10s
  Grok                  0/100 100 left              now        30s
  DeepSeek               0/8   8 left              now         1m
  Google Gemini          0/80  80 left              now         1m
========================================================================
```

### How Rate Limiting Works

1. **Pre-flight check** — before each platform runs, the limiter checks: budget remaining, cooldown window, daily cap, exponential backoff (after rate-limited events)
2. **Cooldown** — after each successful request, the platform is locked for its cooldown period (e.g. 5 min for Claude.ai free tier)
3. **Budget window** — requests older than the rolling window (18000s / 5h) are pruned and no longer count against the budget
4. **Rate-limited backoff** — if a platform returns a rate-limit banner, it is penalized with exponential backoff (2×, 4×, 8×… up to 16× the normal cooldown)
5. **Staggered launch** — platforms with more remaining budget launch first; over-budget platforms are deferred

### Bypassing Rate Limits

```bash
# Skip all pre-flight checks (use only for testing)
python3 skills/orchestrator/engine/orchestrator.py \
  --prompt "…" --skip-rate-check
```

### State File Location

```
~/.chrome-playwright/rate-limit-state.json
```

Do not commit this file — it contains machine-local usage history and is in `.gitignore`.

---

## 10. Agent Fallback (browser-use)

When all Playwright selectors fail (e.g. a platform redesigns its UI), the engine automatically falls back to a **vision-based AI agent** powered by [browser-use](https://github.com/browser-use/browser-use).

### How It Works

1. A Playwright extraction returns too few characters (< 200) or raises an exception
2. The `AgentFallbackManager` is invoked with the failing step and a task description
3. A `browser-use` Agent (using Gemini 2.0 Flash or Claude Sonnet) takes screenshots of the live browser, navigates as needed, and extracts the content
4. The result replaces the failed extraction; the fallback event is logged to `agent-fallback-log.json`

### Provider Selection

The fallback LLM is chosen by priority:

```
ANTHROPIC_API_KEY set?  →  Claude Sonnet (claude-sonnet-4-6)
GOOGLE_API_KEY set?     →  Gemini 2.0 Flash (gemini-2.0-flash)
Neither set?            →  Fallback disabled
```

### Fallback Log

After any run where fallback was triggered, inspect:

```bash
cat reports/<task-name>/agent-fallback-log.json
```

```json
[
  {
    "timestamp": "2026-03-16T10:13:47.123456",
    "platform": "copilot",
    "step": "extract_response",
    "original_error": "Extraction returned only 190 chars",
    "agent_task": "On Microsoft Copilot: extract the complete AI response text...",
    "agent_result": "Paris is the capital of France.",
    "agent_success": true,
    "duration_s": 33.5
  }
]
```

### Getting a Free Gemini API Key

1. Go to https://aistudio.google.com/app/apikey
2. Click **Create API key**
3. Export: `export GOOGLE_API_KEY="your-key"`

No credit card required.

---

## 11. Viewing Reports

All run outputs land in `reports/<task-name>/`:

```
reports/my-research-run/
├── Claude.ai-raw-response.md
├── ChatGPT-raw-response.md
├── DeepSeek-raw-response.md
├── Google-Gemini-raw-response.md
├── Perplexity-raw-response.md
├── my-research-run - Raw AI Responses.md   ← auto-collated archive
├── status.json
└── agent-fallback-log.json                 ← only if fallback triggered
```

### Using the Preview Viewer

```bash
python3 skills/landscape-researcher/launch_report.py \
  --report-dir reports/my-research-run \
  --report-file "My Research - Market Landscape Report.md"
```

This starts an HTTP server on port 7788 (auto-selects next available) and opens:

```
http://localhost:7788/reports/preview.html?report=reports/my-research-run/My%20Research%20...
```

### Preview Viewer Options

| Flag | Description |
|------|-------------|
| `--report-dir PATH` | Directory containing the report |
| `--report-file NAME` | Filename of the report to load |
| `--no-browser` | Print the URL but don't open a browser (useful for remote/headless) |
| `--port N` | Override default port 7788 |

### Manual URL

You can also open any report directly by URL:

```
http://localhost:7788/reports/preview.html?report=reports/<task-name>/<filename>.md
```

---

## 12. Domain Knowledge

The file `domains/devops-platforms.md` is a shared knowledge base enriched by both research skills after successful runs.

### What Gets Added

| Source skill | What it contributes |
|-------------|-------------------|
| `solution-researcher` | Product terminology, feature equivalences, inference patterns, competitive signals |
| `landscape-researcher` | Market archetypes, vendor movement signals, category definitions, trend language |

### How Enrichment Works

1. After a successful run, the skill proposes domain additions
2. You review and **approve** before any write happens
3. All additions are **append-only** and **timestamped**
4. The file grows over time, making future research runs more accurate

### Format

```markdown
## [YYYY-MM-DD] Session: <Task Name>

### Category: <Archetype | Terminology | Trend Signal | …>
- **<Term>**: <Definition or inference pattern>
- **<Term>**: …
```

---

## 13. Running Tests

The project has a full pytest unit test suite covering all core engine modules.

### Run All Tests

Use the project venv (created by `bash setup.sh`):

```bash
# From the repo root:
skills/orchestrator/engine/.venv/bin/python -m pytest tests/ -v --tb=short

# Or activate the venv first, then run normally:
source skills/orchestrator/engine/.venv/bin/activate
cd skills/orchestrator/engine && python -m pytest ../../../tests/ -v --tb=short
```

**Expected output:** `96 passed` in ~4s

### Test Coverage

| Test file | IDs | What it covers |
|-----------|-----|---------------|
| `test_prompt_echo.py` | UT-PE-01–08 | Echo detection, signature extraction |
| `test_rate_limiter.py` | UT-RL-01–14 | Budget, cooldown, backoff, persistence |
| `test_collate_responses.py` | UT-CR-01–07 | Response collation and archive creation |
| `test_config.py` | UT-CF-01–07 | RATE_LIMITS structure, 7 platforms verified |
| `test_orchestrator_args.py` | UT-OR-01–11 | CLI flag parsing, defaults, mutual exclusions |
| `test_matrix_ops.py` | UT-MX-01–09 | XLSX matrix operations |
| `test_launch_report.py` | TC-LAUNCH-1–2 | URL encoding, port-in-use handling |

### Compile Check

```bash
python3 -m py_compile skills/orchestrator/engine/orchestrator.py
python3 -m py_compile skills/orchestrator/engine/config.py
python3 -m py_compile skills/orchestrator/engine/rate_limiter.py
# … (or use: for f in skills/orchestrator/engine/**/*.py; do python3 -m py_compile "$f"; done)
```

---

## 14. CI/CD & Make Targets

A `Makefile` is provided for local development. Run `make check` before every commit.

### Available Targets

| Target | What it runs | Time |
|--------|-------------|------|
| `make compile` | `py_compile` on all engine, comparator, landscape, and platform files | ~5s |
| `make test` | Full pytest suite | ~10s |
| `make regression` | Domain-string checks + RATE_LIMITS validation + CLI flag checks | ~10s |
| `make check` | `compile` + `test` + `regression` combined | ~25s |
| `make budget-check` | Prints budget table for free and paid tiers | ~2s |
| `make landscape-smoke` | `launch_report.py --no-browser` smoke test | ~2s |
| `make e2e-smoke` | Live run on Claude.ai with a simple prompt (requires Chrome) | ~2 min |
| `make e2e` | Full live run on all 7 platforms | ~10 min |

### GitHub Actions

The CI workflow (`.github/workflows/ci.yml`) runs on every push and PR:

1. **Install** — `pip install -r skills/orchestrator/engine/requirements.txt && pip install pytest`
2. **Compile** — all engine + comparator + landscape + platform files
3. **Unit tests** — full pytest suite
4. **Regression** — grep checks + RATE_LIMITS config validation + CLI flag checks + landscape smoke

Chrome-based E2E tests do not run in CI — they require active platform logins.

---

## 15. Troubleshooting

### Chrome won't connect

**Symptom:** `Error connecting to Chrome CDP on port 9222`

**Causes & fixes:**
- Chrome is not running → the orchestrator will launch it automatically on first run
- Port 9222 is blocked → check `lsof -i :9222` and kill any conflicting process
- Use `--fresh` to force a clean Chrome launch: `--fresh`

---

### "Rate limited" at pre-flight — nothing runs

**Symptom:** All platforms show `rate_limited` without launching

**Check budget:**
```bash
python3 skills/orchestrator/engine/orchestrator.py --prompt "x" --budget
```

**Options:**
- Wait for cooldowns to expire (shown in "Next Available" column)
- Switch to `--tier paid` if you have paid subscriptions
- Use `--skip-rate-check` for a one-off override (use sparingly)
- Reset a specific platform's state (edit `~/.chrome-playwright/rate-limit-state.json`)

---

### Platform extracted 0 or very few characters

**Symptom:** `Extracted 190 chars via body.innerText` — then `status: failed`

**Causes:**
- Page hasn't finished rendering — increase timeout in `config.py`
- Platform UI changed — a selector needs updating in `platforms/<name>.py`
- Agent fallback will attempt recovery automatically if `GOOGLE_API_KEY` or `ANTHROPIC_API_KEY` is set

---

### Agent fallback fails with `"ChatAnthropic" object has no field ...`

This is a browser-use / langchain-anthropic version mismatch. The fix is already applied in `agent_fallback.py`. If you see this:

```bash
cd skills/orchestrator/engine/.venv
pip install --upgrade browser-use langchain-anthropic
```

---

### Grok extracts 0 characters

**Symptom:** Grok run completes but extracts nothing

**Causes:**
- Prompt was too long and physical typing timed out
- Provide a condensed prompt ≤900 chars via `--condensed-prompt-file`

---

### DeepSeek shows "URL Access Failure"

This is a DeepSeek limitation — it cannot always fetch external URLs. The engine detects this and marks the platform as failed. The other 6 platforms are unaffected.

---

### `preview.html` shows a blank page

**Cause:** Browser opened before the HTTP server was ready, or the report file path is wrong.

**Fix:**
1. Wait 2s and reload
2. Check the URL — the `?report=` parameter must be URL-encoded
3. Verify the report file exists at the stated path
4. Use `--no-browser` to print the URL first, then open manually

---

### Tests fail with `ModuleNotFoundError: No module named 'openpyxl'`

```bash
pip install openpyxl
```

---

### Claude.ai quota depleted mid-run

The Claude.ai quota is **shared with Claude Code itself**. Heavy Claude Code usage before a research run can exhaust the Claude.ai platform budget.

**Mitigations:**
- Run research sessions first, before heavy Claude Code sessions
- Switch to `--tier paid` if you have a paid Claude.ai subscription
- Use `--platforms chatgpt,gemini,perplexity,grok,deepseek` to skip Claude.ai

---

## Appendix A: Output File Reference

| File | Written by | Contents |
|------|-----------|---------|
| `<Platform>-raw-response.md` | Engine | Raw extracted text from platform |
| `status.json` | Engine | Per-platform status, chars, duration, mode |
| `<task-name> - Raw AI Responses.md` | `collate_responses.py` | All responses in canonical order with metadata headers |
| `agent-fallback-log.json` | `agent_fallback.py` | Log of each fallback invocation |

### `status.json` Schema

```json
{
  "claude_ai": {
    "status": "complete",
    "chars": 1796,
    "duration_s": 18.2,
    "mode_used": "Sonnet",
    "file": "Claude.ai-raw-response.md"
  },
  "chatgpt": {
    "status": "rate_limited",
    "chars": 0,
    "duration_s": 0,
    "mode_used": "",
    "error": "Pre-flight blocked: Cooldown active"
  }
}
```

### Platform Status Values

| Status | Meaning |
|--------|---------|
| `complete` | Response extracted successfully |
| `rate_limited` | Blocked by pre-flight or live rate limit detection |
| `failed` | Extraction or navigation error |
| `timeout` | Global timeout reached before platform completed |

---

## Appendix B: Adding a New Platform

To add an 8th platform:

1. **Create `skills/orchestrator/engine/platforms/<name>.py`** — subclass `BasePlatform`, implement `configure_mode()`, `inject_prompt()`, `wait_for_completion()`, `extract_response()`, `check_rate_limit()`
2. **Add to `config.py`** — add entry to `PLATFORM_URLS`, `TIMEOUTS`, `RATE_LIMITS`, `PLATFORM_DISPLAY_NAMES`, and `PLATFORM_CLASSES`
3. **Update `domains/`** — add platform to the domain knowledge file if relevant
4. **Add to `tests/test_config.py`** — update expected platform count from 7 to 8
5. **Run `make check`** — all checks should pass with the new count

---

## Appendix C: Version History

| Version | Date | Summary |
|---------|------|---------|
| 4.1 | 2026-03-18 | setup.sh bootstrap; install.sh delegates to setup.sh; SessionStart hook auto-installs deps for plugin users; venv check in orchestrator Phase 1 |
| 4.0 | 2026-03-16 | Landscape researcher, intelligent routing, self-improving skills, domain knowledge sharing, query-param preview |
| 3.2 | 2026-03-14 | Collation, `--task-name` routing, `collate_responses.py` |
| 3.1 | 2026-03-14 | Rate limiter, budget/cooldown/backoff, `--tier`, `--budget` |
| 3.0 | 2026-03-13 | Comparator skill, XLSX matrix operations |
| 2.0 | 2026-03-13 | Generic restructuring — engine moved to `skills/orchestrator/engine/` |

Full details: [CHANGELOG.md](CHANGELOG.md)
