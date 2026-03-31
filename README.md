# MultAI

> **Submit a research prompt to 7 AI platforms simultaneously — all from Claude Code.**

`MultAI` is a Claude Cowork/Code plugin that automates multi-AI research workflows. It uses Playwright CDP automation to submit prompts to Claude.ai, ChatGPT, Microsoft Copilot, Perplexity, Grok, DeepSeek, and Google Gemini in parallel, extracts their responses, and synthesizes the results into structured deliverables — market landscape reports, solution capability matrices, comparison spreadsheets, and more.

---

## What It Does

```
You (Claude Code)
      │
      ▼
┌──────────────────────────────────────────────────────┐
│  Orchestrator  (intelligent router — Phase 0)         │
│                                                        │
│  ┌──────────────────┐   ┌────────────────────────┐   │
│  │ landscape-       │   │ solution-researcher    │   │
│  │ researcher       │   │ product deep-dive      │   │
│  └──────────────────┘   └────────────────────────┘   │
│  ┌──────────────────┐   ┌────────────────────────┐   │
│  │ comparator       │   │ direct multi-AI        │   │
│  │ XLSX matrix ops  │   │ + generic consolidator │   │
│  └──────────────────┘   └────────────────────────┘   │
└──────────────────────────────────────────────────────┘
      │
      ▼
Playwright Engine ──► 7 AI Platforms ──► reports/
```

| Capability | Detail |
|---|---|
| **Parallel submission** | All 7 platforms run concurrently via `asyncio.gather()` |
| **Intelligent routing** | Orchestrator analyzes intent and dispatches to the right skill automatically |
| **Market landscape reports** | 9-section structured reports (Top 20 commercial + OSS, positioning matrices, trends) |
| **Solution research** | Deep-dive on a product URL — capability inventory, competitive context, XLSX scoring |
| **XLSX comparison matrix** | Capability matrix auto-scored and reordered across platforms |
| **Rate limiting** | Per-platform budget tracking; warns on low budget but never skips a platform — only sign-in failures, unreachable hosts, or on-page quota exhaustion exclude a platform |
| **Agent fallback** | Vision-based `browser-use` agent kicks in automatically when a UI selector fails, including navigation errors and sign-in pages |
| **Sign-in detection** | Detects login/sign-in pages and returns a clear `needs_login` status rather than silently failing |
| **Tab reuse** | Existing browser tabs are reused across runs; `--followup` injects into the open conversation, new topics navigate within the same tab |
| **DEEP mode** | Activates Deep Research / Research mode on each platform (where available) |
| **Prompt echo filtering** | Automatically strips platform echoes from extracted responses |
| **Report viewer** | `preview.html?report=<path>` renders any Markdown report with charts |
| **Self-improving skills** | Each skill appends a run log and can update its own templates after every run |
| **Shared domain knowledge** | `domains/{domain}.md` is enriched by both research skills after every run |

---

## Supported Platforms

| Platform | URL | Notes |
|---|---|---|
| Claude.ai | https://claude.ai | Pro plan recommended for DEEP mode |
| ChatGPT | https://chat.openai.com | Plus plan for Deep Research |
| Microsoft Copilot | https://copilot.microsoft.com | Free tier works |
| Perplexity | https://www.perplexity.ai | Pro for Deep Research |
| Grok | https://grok.com | X/Twitter account required |
| DeepSeek | https://chat.deepseek.com | Free tier works |
| Google Gemini | https://gemini.google.com | Google account required |

---

## Quick Start

### 1 — Prerequisites

- Claude Code **v1.0.33 or later** — run `claude --version` to check; update with `brew upgrade claude-code` or `npm update -g @anthropic-ai/claude-code`
- Python 3.11+, Google Chrome installed

### 2 — Install via Claude Code Plugin Manager

```shell
# Step 1 — register the repo as a marketplace (one-time):
/plugin marketplace add alo-exp/multai

# Step 2 — install the plugin from that marketplace:
/plugin install multai@multai
```

> Skills are namespaced: `/multai:orchestrator`, `/multai:solution-researcher`, etc.
> Run `/reload-plugins` if skills don't appear immediately.

Python dependencies (`playwright`, `openpyxl`, Chromium browser) are **installed automatically** on the first session start via a `SessionStart` hook (hook → `install.sh` → `setup.sh`). No manual setup required.

> **Agent fallback (optional):** To enable the vision-based browser-use fallback, run manually:
> ```bash
> bash "$(find ~/.claude/plugins/cache -name setup.sh | head -1)" --with-fallback
> ```

### Alternative — Local / Dev Install

```bash
git clone https://github.com/alo-exp/multai.git
cd multai
bash setup.sh            # creates .venv, installs pip deps + Playwright Chromium + .env template
# optional agent fallback:
bash setup.sh --with-fallback

# Load directly without marketplace registration:
claude --plugin-dir ./multai
```

### 3 — Log in to platforms

Open Chrome and log in to each of the 7 AI platforms above. The engine re-uses your existing Chrome profile — no credentials are stored by this tool.

### 4 — Set optional API keys

```bash
# ~/.zshrc or ~/.bashrc
export GOOGLE_API_KEY="..."      # free from aistudio.google.com — enables Gemini agent fallback
export ANTHROPIC_API_KEY="..."   # from console.anthropic.com — enables Claude agent fallback
```

### 4 — Open your project in Claude Code and use a skill

```
# Route a landscape research request:
"Run a market landscape analysis on DevOps platforms for SMBs"

# Route a product deep-dive:
"Research humanitec.com"

# Route a matrix operation:
"Add Harness to the comparison matrix"

# Direct multi-AI (no specific route):
"What are the main trade-offs between Rust and Go for backend services?"
```

The orchestrator announces its routing decision before proceeding — you can override it.

---

## Skills

### `orchestrator` — Intelligent Router + Engine Owner

The entry point for all workflows. Phase 0 analyzes your intent and routes to the correct specialist skill. For direct multi-AI queries it owns the full pipeline itself.

**Triggers:** any research or comparison prompt; explicitly routing to another skill

**Routing rules:**
```
"landscape" / "market map" / "ecosystem" / "vendor landscape"
  → landscape-researcher

Product URL or named product + research intent
  → solution-researcher

"comparison matrix" / "add platform" / "update matrix"
  → comparator

Everything else
  → direct multi-AI (orchestrator handles end-to-end)
```

---

### `landscape-researcher` — Market Landscape Reports

Produces a 9-section structured Market Landscape Report across commercial and OSS solutions for any product category.

**Triggers:** "landscape analysis on X", "market map for X", "competitive landscape", "ecosystem overview"

**Output:** `reports/{task-name}/{Category} - Market Landscape Report.md` + auto-launched browser preview

**Report sections:**
1. Market Definition & Scope
2. Market Overview (size, CAGR, drivers)
3. Competitive Positioning (2×2, Wave-style, Value Curve)
4. Key Industry Trends (5–10)
5. Top 20 Commercial Solutions for SMBs
6. Top 20 OSS Solutions
7. Buying Guidance & Shortlist Profiles
8. Future Outlook & Emerging Disruptors
9. Source Reliability Assessment

---

### `solution-researcher` — Product Deep-Dives

Researches a specific product or URL in depth — capabilities, integrations, pricing, competitive context — and optionally scores it in the comparison matrix.

**Triggers:** "research humanitec.com", "evaluate Backstage", "analyze Port.io"

**Output:** `reports/{task-name}/{Product} - Consolidated Intelligence Report.md` + optional XLSX matrix scoring

---

### `comparator` — XLSX Capability Matrix

Maintains and operates the capability comparison matrix spreadsheet.

**Triggers:** "add X to the matrix", "update comparison matrix", "score Harness", "combo column", "verify ticks"

**Scripts:**
- `skills/comparator/matrix_ops.py` — add platforms, update scores, apply combos
- `skills/comparator/matrix_builder.py` — rebuild matrix from raw response archives

---

### `consolidator` — Response Synthesis

Synthesizes raw multi-AI responses into a single structured report. Called automatically by other skills; rarely invoked directly.

**With a consolidation guide:** the guide is the sole structural authority — used by landscape-researcher (9-section guide) and solution-researcher (CIR guide).

**Without a guide:** produces a well-structured synthesis using its own judgement.

---

## Project Structure

```
multai/
├── .claude-plugin/
│   ├── plugin.json           ← Claude Code Plugin manifest
│   └── hooks.json            ← SessionStart hook (runs install.sh → setup.sh once)
├── skills/
│   ├── orchestrator/
│   │   ├── SKILL.md          ← Router + phases
│   │   ├── platform-setup.md ← Per-platform login/injection notes
│   │   └── engine/           ← Playwright automation engine
│   │       ├── orchestrator.py
│   │       ├── config.py
│   │       ├── rate_limiter.py
│   │       ├── agent_fallback.py
│   │       ├── prompt_echo.py
│   │       ├── collate_responses.py
│   │       ├── utils.py
│   │       └── platforms/    ← claude_ai.py chatgpt.py copilot.py …
│   ├── consolidator/
│   │   └── SKILL.md
│   ├── landscape-researcher/
│   │   ├── SKILL.md
│   │   ├── prompt-template.md
│   │   ├── consolidation-guide.md
│   │   └── launch_report.py  ← stdlib-only HTTP server + browser open
│   ├── solution-researcher/
│   │   ├── SKILL.md
│   │   ├── prompt-template.md
│   │   └── consolidation-guide.md
│   └── comparator/
│       ├── SKILL.md
│       ├── matrix_ops.py
│       └── matrix_builder.py
├── domains/
│   └── devops-platforms.md   ← Shared domain knowledge (enriched per run)
├── reports/
│   └── preview.html          ← Query-param driven report viewer
├── docs/
│   ├── Architecture-and-Design.md
│   ├── SRS.md
│   ├── Test-Strategy-and-Plan.md
│   └── CICD-Strategy-and-Plan.md
├── tests/                    ← pytest suite
├── setup.sh                  ← Canonical bootstrap — creates .venv, installs deps
├── install.sh                ← Plugin hook delegate → setup.sh
├── pyproject.toml            ← Python packaging spec
├── settings.json             ← Default Claude Cowork/Code plugin permissions
├── USER-GUIDE.md             ← End-user guide (non-technical)
└── CONTRIBUTOR-GUIDE.md      ← Technical contributor reference
```

---

## Engine CLI Reference

The orchestration engine can also be driven directly from the terminal:

```bash
# Check platform budgets (no browser opened):
python3 skills/orchestrator/engine/orchestrator.py --budget --tier free

# Submit a prompt in REGULAR mode:
python3 skills/orchestrator/engine/orchestrator.py \
  --prompt "What is the CAP theorem?" \
  --mode REGULAR \
  --task-name my-research

# Submit from a file in DEEP mode:
python3 skills/orchestrator/engine/orchestrator.py \
  --prompt-file /tmp/my-prompt.md \
  --mode DEEP \
  --task-name deep-research-20260316

# Follow-up on the same topic (reuses open conversations, no new tabs):
python3 skills/orchestrator/engine/orchestrator.py \
  --prompt "Now focus specifically on pricing models" \
  --mode REGULAR \
  --task-name my-research \
  --followup

# Collate archived responses into a single file:
python3 skills/orchestrator/engine/collate_responses.py \
  --archive-dir reports/my-research/
```

Output is written to `reports/{task-name}/` — one `.md` file per platform, plus a `status.json` summary.

---

## Rate Limiting

The engine tracks per-platform usage across runs and warns when a budget is low, but **never skips a platform based on budget alone**. A platform is only excluded from a round if:

- A sign-in / login page is detected (`needs_login` status — 🔑)
- The platform is unreachable (network error)
- Actual quota exhaustion is detected on-page

Budgets, cooldowns, and daily caps are configured per-platform and per-tier in `config.py` and are persisted in `~/.chrome-playwright/rate-limit-state.json` across sessions.

---

## Agent Fallback

When a Playwright selector fails (e.g. platform UI changed), a `browser-use` vision agent takes over:

1. **Anthropic key present** → Claude Sonnet is the agent LLM
2. **Google key present** → Gemini 2.0 Flash is the agent LLM (free tier at aistudio.google.com)
3. **Neither key** → fallback silently disabled; Playwright exception propagates

```bash
# Set in your shell profile:
export GOOGLE_API_KEY="AIza..."        # recommended (free)
export ANTHROPIC_API_KEY="sk-ant-..."  # alternative
```

The fallback venv is set up by `setup.sh --with-fallback` and auto-detected by the engine.

---

## Report Viewer

Reports are rendered by a self-contained `preview.html` served locally:

```bash
# From the landscape-researcher skill (auto-launched):
python3 skills/landscape-researcher/launch_report.py \
  --report-dir market-landscape-20260316-1430 \
  --report-file "DevOps Platforms - Market Landscape Report.md" \
  --port 7788
```

Or open manually:
```
http://localhost:7788/preview.html?report=market-landscape-20260316-1430/DevOps%20Platforms%20-%20Market%20Landscape%20Report.md
```

The viewer renders Markdown, highlights code blocks, and injects positioning charts when the report contains a matrix section.

---

## Domain Knowledge

`domains/{domain}.md` is a shared living document enriched after every research run:

- **landscape-researcher** adds: new vendor archetypes, market-wide trend signals, category boundary changes, emerging vendors
- **solution-researcher** adds: new capability categories, terminology introduced by a vendor, feature-name equivalences

Both skills propose additions and ask for approval before writing. Additions are always append-only and timestamped.

---

## Running Tests

```bash
# Full test suite — 98 tests (using the project venv):
skills/orchestrator/engine/.venv/bin/python -m pytest tests/ -v

# Alternatively, from the engine directory:
cd skills/orchestrator/engine && .venv/bin/python -m pytest ../../../tests/ -v

# Specific test file:
skills/orchestrator/engine/.venv/bin/python -m pytest tests/test_rate_limiter.py -v

# Engine budget check (smoke test — no browser):
python3 skills/orchestrator/engine/orchestrator.py --budget --tier free
```

---

## Documentation

| Document | Description |
|---|---|
| [`USER-GUIDE.md`](USER-GUIDE.md) | End-user guide — installation, skills overview, viewing reports |
| [`CONTRIBUTOR-GUIDE.md`](CONTRIBUTOR-GUIDE.md) | Contributor reference — CLI flags, platform internals, tests, CI/CD |
| [`docs/Architecture-and-Design.md`](docs/Architecture-and-Design.md) | System topology, data flows, design decisions |
| [`docs/SRS.md`](docs/SRS.md) | Software Requirements Specification |
| [`docs/Test-Strategy-and-Plan.md`](docs/Test-Strategy-and-Plan.md) | Test cases, coverage strategy |
| [`docs/CICD-Strategy-and-Plan.md`](docs/CICD-Strategy-and-Plan.md) | CI/CD pipeline, make targets, deployment |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history |

---

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | 3.13 required for agent fallback |
| Google Chrome | latest | Must be installed; engine re-uses your profile |
| playwright | ≥ 1.40.0 | Installed by `setup.sh` |
| openpyxl | ≥ 3.1.0 | Installed by `setup.sh` |
| Claude Code | latest | Skills are invoked as Claude Cowork/Code plugin skills |

---

## License

MIT — see [LICENSE](LICENSE) or the `license` field in [`pyproject.toml`](pyproject.toml).

---

## Author

[alo-exp](https://github.com/alo-exp) · [GitHub](https://github.com/alo-exp/multai) · [User Guide](USER-GUIDE.md) · [Contributor Guide](CONTRIBUTOR-GUIDE.md)
