# MultAI

> **One skill. Seven AI platforms. Instant synthesis.**

`/multai` is a Claude Cowork/Code plugin skill that submits your research prompt to Claude.ai, ChatGPT, Microsoft Copilot, Perplexity, Grok, DeepSeek, and Google Gemini simultaneously — then synthesizes the results into structured deliverables. Market landscape reports, capability comparison matrices, product deep-dives, or a direct answer from all seven platforms at once.

---

## How It Works

```
You → /multai → 7 AI Platforms in parallel → Synthesized report
```

You type one prompt. `/multai` figures out what you need, runs it across all platforms, and hands back a consolidated result. No flags, no routing decisions, no platform management.

| Capability | Detail |
|---|---|
| **Parallel submission** | All 7 platforms run concurrently |
| **Intelligent routing** | Analyzes your intent and selects the right workflow automatically |
| **Market landscape reports** | 9-section structured reports — top 20 commercial + OSS, positioning matrices, trends |
| **Product deep-dives** | Capabilities, integrations, pricing, competitive context, XLSX scoring |
| **XLSX comparison matrix** | Capability matrix auto-scored and reordered across platforms |
| **DEEP mode** | Activates Deep Research on each platform where available |
| **Rate limiting** | Per-platform budget tracking across sessions; never silently skips a platform |
| **Agent fallback** | Vision-based fallback via `browser-use` when a UI selector fails |
| **Tab reuse** | Existing browser tabs reused across runs; `--followup` continues open conversations |
| **Report viewer** | Browser-rendered Markdown reports with positioning charts |

---

## Supported Platforms

| Platform | Notes |
|---|---|
| Claude.ai | Pro plan recommended for DEEP mode |
| ChatGPT | Plus plan for Deep Research |
| Microsoft Copilot | Free tier works |
| Perplexity | Pro for Deep Research |
| Grok | X/Twitter account required |
| DeepSeek | Free tier works |
| Google Gemini | Google account required |

---

## Quick Start

### 1 — Prerequisites

- Claude Code **v1.0.33 or later** — check with `claude --version`, update with `brew upgrade claude-code` or `npm update -g @anthropic-ai/claude-code`
- Python 3.11+, Google Chrome

### 2 — Install

```shell
# Register the marketplace (one-time):
/plugin marketplace add alo-exp/multai

# Install:
/plugin install multai@multai
```

> Run `/reload-plugins` if `/multai` doesn't appear immediately.

Python dependencies (`playwright`, `openpyxl`, Chromium) are **installed automatically** on first session start via a `SessionStart` hook. No manual setup required.

> **Agent fallback (optional):** For the vision-based `browser-use` fallback:
> ```bash
> bash "$(find ~/.claude/plugins/cache -name setup.sh | head -1)" --with-fallback
> ```

### Alternative — Local / Dev Install

```bash
git clone https://github.com/alo-exp/multai.git
cd multai
bash setup.sh            # creates .venv, installs deps + Playwright Chromium
# optional agent fallback:
bash setup.sh --with-fallback

claude --plugin-dir ./multai
```

### 3 — Log in to platforms

Open Chrome and sign in to each platform. The engine reuses your existing Chrome profile — no credentials are stored.

### 4 — Set optional API keys

```bash
# ~/.zshrc or ~/.bashrc
export GOOGLE_API_KEY="..."      # free from aistudio.google.com — enables Gemini agent fallback
export ANTHROPIC_API_KEY="..."   # from console.anthropic.com — enables Claude agent fallback
```

### 5 — Use the skills

**`/multai`** — research, landscape analysis, direct multi-AI queries, and matrix operations:
```
/multai Run a market landscape analysis on DevOps platforms for SMBs
/multai Research humanitec.com
/multai Add Harness to the comparison matrix
/multai What are the main trade-offs between Rust and Go for backend services?
```

**`/comparator`** — standalone head-to-head comparisons without a prior research run:
```
/comparator Compare Humanitec vs Port.io
/comparator Which is better for a startup — Backstage or Cortex?
/comparator Compare these two products and give me a weighted score
```

**`/consolidator`** — merge any set of content sources into a unified, structured report:
```
/consolidator Consolidate these three research papers into a summary report
/consolidator Summarize these five customer interview transcripts into themes
/consolidator Combine these meeting notes from four teams into a single overview
```

All skills announce their plan before acting — you can always override or adjust.

---

## What `/multai` Can Do

### Market landscape reports

> "Run a landscape analysis on API gateway platforms"
> "Give me a market map for observability tools for startups"

Produces a 9-section structured Market Landscape Report: market definition, size & CAGR, competitive positioning (2×2, Wave-style, Value Curve), key trends, top 20 commercial + OSS solutions, buying guidance, and future outlook.

**Output:** `reports/{task-name}/{Category} - Market Landscape Report.md` + auto-launched browser preview

### Product deep-dives

> "Research humanitec.com"
> "Evaluate Backstage"
> "Analyze Port.io — how does it compare to Cortex?"

Deep research on a specific product — capabilities, integrations, pricing, competitive context — optionally scored in the comparison matrix.

**Output:** `reports/{task-name}/{Product} - Consolidated Intelligence Report.md`

### Head-to-head comparisons — `/comparator`

> "Compare Humanitec vs Port.io"
> "Which is better for SMBs — Backstage or Cortex?"
> "Compare these two products and score them"

Standalone skill for comparing any two (or more) solutions. Derives a capability framework from available evidence (CIRs, documents, or LLM knowledge), optionally lets you set feature priorities, scores each solution with priority-weighted ticks, and produces both an XLSX matrix and a readable Markdown summary with per-category winners and key differentiators. No prior research run required — works from LLM knowledge alone if needed.

**Output:** `reports/{domain}/{domain}-matrix.xlsx` + `reports/{domain}/{task-name}-comparison-summary.md`

Can also be triggered via `/multai` — it routes automatically when comparison intent is detected.

### Multi-source consolidation — `/consolidator`

> "Consolidate these three research papers into a summary"
> "Summarize these five customer interviews into themes and recommendations"
> "Combine these meeting notes from four teams into one overview"

Standalone skill for synthesizing content from any set of sources — documents, transcripts, notes, URLs, pasted text, or AI platform responses — into a unified, well-structured report. Detects the content type and auto-derives an appropriate report structure (research synthesis, theme extraction, decision log, etc.), or follows a consolidation guide you provide.

When invoked from within a `/multai` workflow, operates in AI-Responses mode and produces a CIR (Consolidated Intelligence Report) from raw platform outputs.

**Output:** `[Topic] - Consolidated Report.md` (generic) or `[Topic] - Consolidated Intelligence Report.md` (AI-Responses mode)

### Comparison matrix operations

> "Add Harness to the comparison matrix"
> "Update the score for Cortex on the developer portal capability"
> "Reorder the matrix by score"

Maintains an existing XLSX capability matrix — adding platforms, updating scores, applying combo columns, reordering, and verifying coverage.

### Direct multi-AI queries

> "What are the emerging consensus patterns for LLM memory management?"
> "Summarize the current state of WebAssembly for server-side workloads"

For anything that isn't a landscape, deep-dive, or matrix operation, `/multai` submits directly to all 7 platforms and synthesizes a consolidated answer.

---

## Project Structure

```
multai/
├── .claude-plugin/
│   ├── plugin.json           ← Plugin manifest
│   └── hooks.json            ← SessionStart hook (auto-installs deps)
├── skills/
│   ├── orchestrator/         ← /multai skill — router + engine owner
│   │   ├── SKILL.md
│   │   ├── platform-setup.md
│   │   └── engine/           ← Playwright automation engine
│   │       ├── orchestrator.py
│   │       ├── config.py
│   │       ├── rate_limiter.py
│   │       ├── agent_fallback.py
│   │       ├── collate_responses.py
│   │       └── platforms/    ← claude_ai.py chatgpt.py copilot.py …
│   ├── consolidator/         ← /consolidator skill — multi-source synthesis + CIR
│   ├── landscape-researcher/ ← Market landscape workflow (internal)
│   ├── solution-researcher/  ← Product deep-dive workflow (internal)
│   └── comparator/           ← /comparator skill — head-to-head comparisons + XLSX matrix
├── domains/                  ← Shared domain knowledge (enriched per run)
├── reports/
│   └── preview.html          ← Report viewer
├── docs/                     ← Architecture, SRS, test & CI/CD plans
├── tests/                    ← pytest suite
├── setup.sh                  ← Bootstrap — venv, deps, Playwright Chromium
├── pyproject.toml
├── requirements.txt
├── USER-GUIDE.md
└── CONTRIBUTOR-GUIDE.md
```

---

## Rate Limiting

The engine tracks per-platform usage across sessions and warns when a budget is low, but **never skips a platform based on budget alone**. A platform is excluded from a round only if:

- A sign-in page is detected (`needs_login` — 🔑)
- The platform is unreachable (network error)
- Actual quota exhaustion is detected on-page

---

## Agent Fallback

When a Playwright selector fails, a `browser-use` vision agent takes over automatically:

1. `ANTHROPIC_API_KEY` set → Claude Sonnet is the agent LLM
2. `GOOGLE_API_KEY` set → Gemini 2.0 Flash (free tier at aistudio.google.com)
3. Neither key → fallback disabled; Playwright exception propagates

---

## Documentation

| Document | Description |
|---|---|
| [`USER-GUIDE.md`](USER-GUIDE.md) | Installation, usage, viewing reports |
| [`CONTRIBUTOR-GUIDE.md`](CONTRIBUTOR-GUIDE.md) | CLI flags, platform internals, tests, CI/CD |
| [`docs/Architecture-and-Design.md`](docs/Architecture-and-Design.md) | System topology and design decisions |
| [`docs/SRS.md`](docs/SRS.md) | Software Requirements Specification |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history |

---

## Requirements

| Requirement | Version |
|---|---|
| Python | ≥ 3.11 |
| Google Chrome | latest |
| Claude Code | ≥ v1.0.33 |

---

## License

MIT — see [LICENSE](LICENSE).

---

[alo-exp](https://github.com/alo-exp) · [User Guide](USER-GUIDE.md) · [Contributor Guide](CONTRIBUTOR-GUIDE.md)
