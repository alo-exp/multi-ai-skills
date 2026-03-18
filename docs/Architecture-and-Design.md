# Architecture and Design Document

**Project:** Multi-AI Orchestrator Platform
**Version:** 4.1
**Date:** 2026-03-18

| Version | Date | Summary |
|---------|------|---------|
| 2.0 | 2026-03-13 | Initial architecture for generic restructuring |
| 3.0 | 2026-03-13 | Added comparator flow, matrix engine, full pipeline diagram |
| 3.1 | 2026-03-14 | Added rate_limiter.py, check_rate_limit() lifecycle, rate limit flow |
| 3.2 | 2026-03-14 | Added collate_responses.py, --task-name routing, collation step in flow |
| 4.0 | 2026-03-16 | 5-skill architecture: landscape-researcher, engine owned by orchestrator, comparator owns matrix scripts, self-improving skills, domain knowledge sharing model, intent-based routing |
| 4.1 | 2026-03-18 | Dependency bootstrap architecture: setup.sh, plugin hook chain, skills.sh install path, venv check |

---

## 1. System Context

```
                                    ┌─────────────────────┐
                                    │       User          │
                                    └─────────┬───────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────┐
                              │     Host AI (Claude Code)     │
                              │                               │
                              │  ┌─────────────────────────┐  │
                              │  │   Skills (SKILL.md)      │  │
                              │  │  - Orchestrator (Router)  │  │
                              │  │  - Consolidator          │  │
                              │  │  - Comparator            │  │
                              │  │  - Solution Researcher   │  │
                              │  │  - Landscape Researcher  │  │
                              │  └────────────┬────────────┘  │
                              └───────────────┼───────────────┘
                                              │
                          ┌───────────────────┼───────────────────┐
                          │                   │                   │
                          ▼                   ▼                   ▼
                 ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
                 │   Engine    │    │   Domain     │    │   Reports   │
                 │  (Python)   │    │  Knowledge   │    │  (Output)   │
                 │             │    │   (.md)      │    │             │
                 └──────┬──────┘    └─────────────┘    └─────────────┘
                        │
                        ▼
               ┌─────────────────┐
               │  Chrome (CDP)   │
               │  7 tabs/pages   │
               └────────┬────────┘
                        │
        ┌───────┬───────┼───────┬───────┬───────┬───────┐
        ▼       ▼       ▼       ▼       ▼       ▼       ▼
    Claude  ChatGPT  Copilot  Perpl.  Grok  DeepSeek  Gemini
```

**Key interactions:**
- User communicates with Claude Code (host AI)
- Claude Code follows SKILL.md instructions to orchestrate the workflow
- Orchestrator acts as a **router** (Phase 0 routing decision tree) dispatching to the appropriate skill
- Engine is owned by orchestrator skill at `skills/orchestrator/engine/`
- Matrix scripts are owned by comparator skill at `skills/comparator/`
- Engine manages Chrome via Playwright + CDP
- Engine runs 7 platforms in parallel, saves results to `reports/`
- Claude Code reads results and performs consolidation

**Skill Topology (v4.0 — Intent-Based Routing):**

```
User → Orchestrator Skill (Router + Engine Owner)
  |--- landscape-researcher → engine → consolidator → launch_report.py → domain enrichment
  |--- solution-researcher  → engine → consolidator → comparator → domain enrichment
  |--- comparator           (direct)
  '--- Direct multi-AI      → engine → consolidator (generic)
```

**Four operating modes:**
1. **Landscape research:** Market landscape analysis on a domain — landscape-researcher builds prompt, runs engine, consolidates 9-section report (Top 20 commercial + Top 20 OSS), auto-launches HTML viewer, enriches domain knowledge.
2. **Solution research:** A specific product is researched using a structured prompt template, consolidated into a CIR, auto-compared against a matrix, and domain knowledge is enriched.
3. **Comparator (direct):** User requests a matrix update directly — comparator skill invoked without engine run.
4. **Generic (direct multi-AI):** Any arbitrary prompt is submitted to 7 AIs, responses are collected and synthesized. No specialized skill involved.

---

## 2. Component Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    multi-ai-skills/ (Workspace Root)             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │             skills/orchestrator/ (Router + Engine Owner)   │   │
│  │                                                          │   │
│  │  SKILL.md  ── Intent routing + engine invocation          │   │
│  │                                                          │   │
│  │  engine/ (Python)                                        │   │
│  │    orchestrator.py ─── config.py ─── utils.py            │   │
│  │         │                                                │   │
│  │         ├── prompt_echo.py  (generic echo detection)     │   │
│  │         ├── agent_fallback.py  (browser-use fallback)    │   │
│  │         ├── rate_limiter.py  (usage tracking & budgets)  │   │
│  │         ├── collate_responses.py  (archive collation)    │   │
│  │         │                                                │   │
│  │         └── platforms/                                   │   │
│  │              ├── base.py  (lifecycle engine)              │   │
│  │              ├── claude_ai.py                             │   │
│  │              ├── chatgpt.py                               │   │
│  │              ├── copilot.py                               │   │
│  │              ├── perplexity.py                             │   │
│  │              ├── grok.py                                   │   │
│  │              ├── deepseek.py                               │   │
│  │              └── gemini.py                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │             skills/ (Other Skills — each has SKILL.md)    │   │
│  │                                                          │   │
│  │  GENERIC:                                                │   │
│  │  consolidator/SKILL.md    ── Any AI responses → synth.   │   │
│  │                                                          │   │
│  │  SPECIALIZED:                                            │   │
│  │  comparator/              ── Matrix build & comparison   │   │
│  │      SKILL.md                                            │   │
│  │      matrix_ops.py        ── 9 XLSX operations           │   │
│  │      matrix_builder.py    ── Build matrix from scratch   │   │
│  │  solution-researcher/     ── Solution research workflow   │   │
│  │      SKILL.md                                            │   │
│  │      prompt-template.md                                  │   │
│  │      consolidation-guide.md                              │   │
│  │  landscape-researcher/    ── Market landscape research    │   │
│  │      SKILL.md                                            │   │
│  │      prompt-template.md                                  │   │
│  │      consolidation-guide.md                              │   │
│  │      launch_report.py     ── HTML report viewer launcher │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │   domains/   │   │   reports/   │   │ references/  │        │
│  │  devops-     │   │  status.json │   │ platform-    │        │
│  │  platforms.md│   │  *-raw-*.md  │   │ setup.md     │        │
│  │  (enriched   │   │  preview.html│   │              │        │
│  │   by both    │   │              │   │              │        │
│  │  researchers)│   │              │   │              │        │
│  └──────────────┘   └──────────────┘   └──────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

**All 5 SKILL.md files** contain a Self-Improve phase and a Run Log section (see Section 6.10).

### 2.2 Component Responsibilities

| Component | Responsibility | Domain Knowledge |
|-----------|---------------|-----------------|
| `skills/orchestrator/engine/orchestrator.py` | Chrome lifecycle, CLI parsing, parallel dispatch, staggered launch, auto-collation | None |
| `skills/orchestrator/engine/rate_limiter.py` | Pre-flight budget checks, usage persistence, cooldowns, staggered ordering | None |
| `skills/orchestrator/engine/collate_responses.py` | Merge per-platform raw response files into single archive; callable standalone | None |
| `skills/orchestrator/engine/prompt_echo.py` | Extract prompt signatures, detect echoed prompts | None |
| `skills/orchestrator/engine/platforms/*.py` | Per-platform UI automation (navigate, inject, extract) + rate limit detection | None |
| `skills/orchestrator/engine/agent_fallback.py` | Vision-based fallback when selectors break | None |
| `skills/orchestrator/` | Workflow: intent routing (Phase 0) → dispatch to skill or run engine → collect results | None |
| `skills/consolidator/` | Workflow: read responses → synthesize report + domain enrichment | Via consolidation guide |
| `skills/comparator/` | Workflow: read CIR → tick judgment → XLSX operations (owns matrix scripts) | Via domain knowledge |
| `skills/comparator/matrix_ops.py` | XLSX manipulation: add-platform, reorder, verify, combo, etc. | None |
| `skills/comparator/matrix_builder.py` | Build new XLSX matrix from JSON config | None |
| `skills/solution-researcher/` | Workflow: build prompt → orchestrate → consolidate → compare → domain enrichment | Via domain knowledge |
| `skills/landscape-researcher/` | Workflow: build prompt → orchestrate → consolidate → launch report → domain enrichment | Via domain knowledge |
| `skills/landscape-researcher/launch_report.py` | Start HTTP server and open `preview.html?report=<path>` for HTML report viewing | None |
| `domains/*.md` | Evaluation criteria, terminology, archetypes, inference patterns | Self (enriched by ALL skills) |

---

## 3. Data Flow

### 3.1 Engine Orchestration Flow (Used by Both Modes)

```
User prompt (text)
    │
    ▼
┌─────────────────────────────────────────────┐
│  Orchestrator Skill (SKILL.md)              │
│  1. Write prompt to temp file               │
│  2. Invoke engine CLI                       │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Engine (orchestrator.py)                   │
│  1. load_prompts() → full, condensed, sigs  │
│  2. Launch/connect Chrome via CDP           │
│  3. Create AgentFallbackManager             │
│  4. Rate limiter pre-flight checks          │
│     → Skip over-budget platforms            │
│  5. Staggered launch (5s apart, by budget)  │
│     Each platform:                          │
│     a) page.goto(url)                       │
│     a') check_rate_limit(page)  ← NEW       │
│     b) configure_mode(mode)                 │
│     c) inject_prompt(prompt)                │
│     d) click_send()                         │
│     e) post_send(mode)                      │
│     f) poll_completion(timeout)             │
│        └─ check_rate_limit() each poll cycle│
│     g) extract_response()                   │
│     h) save → {Platform}-raw-response.md    │
│  6. record_usage() per platform             │
│  7. write_status(status.json)               │
│  8. collate_responses() →                  │
│     {task-name} - Raw AI Responses.md       │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  reports/{task-name}/                       │
│  ├── status.json                            │
│  ├── Claude.ai-raw-response.md              │
│  ├── ChatGPT-raw-response.md                │
│  ├── ...5 more...                           │
│  ├── {task-name} - Raw AI Responses.md      │
│  └── agent-fallback-log.json (if any)       │
└─────────────────────────────────────────────┘
```

### 3.2 Solution Research Flow (Specialized — Only When Explicitly Requested)

```
User: "Research Facets.cloud (DevOps IDP)"
    │
    ▼
┌─────────────────────────────────────────────┐
│  Solution Researcher Skill                  │
│  Phase 0: Extract URL, scope, domain        │
│  Phase 1: Build prompt                      │
│    - Load prompt-template.md                │
│    - Fill [PRIMARY_URL], [SCOPE_CONTEXT]    │
│    - Load domains/devops-platforms.md        │
│    - Append evaluation criteria             │
│    - Generate condensed prompt              │
│    - Write to /tmp/research-prompt.md       │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Orchestrator Skill                         │
│  → Engine CLI → 7 platforms → reports/      │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Consolidator Skill                         │
│  - Reads raw responses archive              │
│  - Reads consolidation-guide.md             │
│  - Produces CIR with prescribed structure   │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Solution Researcher Skill (continued)      │
│  Phase 5: Propose domain knowledge updates  │
│  Phase 6: Present deliverables to user      │
└─────────────────────────────────────────────┘
```

### 3.3 Landscape Research Flow (v4.0)

```
User: "Market landscape analysis of DevOps platforms"
    │
    ▼
┌─────────────────────────────────────────────┐
│  Orchestrator Skill (Router)               │
│  Phase 0: Intent routing → landscape       │
│  → Dispatches to landscape-researcher      │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Landscape Researcher Skill                │
│  Phase 1: Build prompt from template       │
│    - Load prompt-template.md               │
│    - Load domains/{domain}.md              │
│    - Append evaluation criteria            │
│    - Write to /tmp/landscape-prompt.md     │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Engine (orchestrator.py)                  │
│  → 7 platforms → reports/{task-name}/      │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Consolidator Skill                        │
│  - Reads raw responses archive             │
│  - Reads consolidation-guide.md (9-section)│
│  - Produces Market Landscape Report        │
│    (Top 20 commercial + Top 20 OSS)        │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Landscape Researcher Skill (continued)    │
│  Phase 4: launch_report.py                 │
│    → HTTP server + preview.html?report=... │
│  Phase 5: Domain knowledge enrichment      │
│    → Append general domain knowledge       │
│  Phase N: Self-Improve                     │
│    → Append run log entry to SKILL.md      │
└─────────────────────────────────────────────┘
```

### 3.4 Comparator Flow

```
CIR (from consolidator) + Existing matrix (.xlsx)
    │
    ▼
┌─────────────────────────────────────────────┐
│  Comparator Skill (SKILL.md)               │
│  Phase 1: Load context                     │
│    - Read domains/{domain}.md              │
│    - Run matrix_ops.py info + extract      │
│  Phase 2: Process CIR (LLM judgment)       │
│    - Identify CIR variant (A or B)         │
│    - Map features: {feat: true/false}      │
│    - Apply inference patterns from domain  │
│    - Identify new rows (if any)            │
│    - Write features.json + new-rows.json   │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Comparator (matrix_ops.py)                │
│  1. add-platform --features --new-rows     │
│  2. reorder-columns (auto after add)       │
│  → Output: updated .xlsx                   │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Comparator Skill (continued)              │
│  Phase 4: Verify (scores + archetype)      │
│  Phase 5: Domain knowledge enrichment      │
│  Phase 6: Present ranked scores            │
└─────────────────────────────────────────────┘
```

### 3.5 Generic Pipeline (Any Task)

The orchestrator and consolidator are generic tools for **any** task — not only solution research. When the user submits an arbitrary prompt (question, analysis request, comparison, etc.), the generic pipeline runs:

```
User request (any prompt)
    │
    ▼
┌─────────────────────────────────────────────┐
│  Orchestrator Skill                         │
│  1. Write prompt to temp file               │
│  2. Run engine → 7 AIs in parallel          │
│  3. Collect raw responses                   │
│  4. Assemble raw responses archive          │
└─────────────┬───────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────┐
│  Consolidator Skill                         │
│  1. Read raw responses archive              │
│  2. Synthesize: consensus, disagreements,   │
│     unique insights, gaps, reliability      │
│  3. Output consolidated report              │
│  4. Domain enrichment (if domain provided)  │
└─────────────┬───────────────────────────────┘
              │
              ▼
reports/
├── [Topic] - Raw AI Responses.md
└── [Topic] - Consolidated Report.md
```

### 3.6 Solution Research Pipeline (Specialized)

When the user explicitly asks for **solution research** on a specific product, the solution-researcher skill orchestrates the full specialized pipeline:

```
User request (e.g., "Research Northflank.com")
    │
    ├─ Phase 0-1: Build prompt from template (solution-researcher)
    │    └─ Append domain knowledge to prompt
    │
    ├─ Phase 2: Orchestrator → 7 AIs in parallel (skills/orchestrator/engine/orchestrator.py)
    │
    ├─ Phase 3-4: Read results → Consolidate with CIR structure (consolidator)
    │    └─ Domain enrichment proposed
    │
    ├─ Phase 5b: Auto-invoke comparator (if matrix exists for this domain)
    │    ├─ LLM reads CIR → tick decisions
    │    ├─ matrix_ops.py add-platform → reorder-columns
    │    └─ Domain enrichment proposed
    │
    └─ Phase 6: Present deliverables
         ├─ Raw AI Responses archive
         ├─ Consolidated Intelligence Report (CIR)
         ├─ Updated comparison matrix (.xlsx)
         └─ Proposed domain knowledge updates
```

**Key distinction:** The solution-researcher and landscape-researcher are the specialized paths that use prompt templates + consolidation guides. The solution-researcher uniquely invokes the comparator. The landscape-researcher uniquely launches an HTML report viewer. The generic pipeline (orchestrator → consolidator) works with any arbitrary prompt.

---

## 1a. Dependency Bootstrap Architecture

Before any skill can invoke the engine, the Python virtual environment at `skills/orchestrator/engine/.venv` must exist. Two install paths lead to the same canonical bootstrap script (`setup.sh`). A third path (clone/dev) invokes it directly.

### Install Paths

```
Plugin install path:
  Claude Desktop / claude plugin install
    └─► SessionStart hook (hooks/hooks.json)
          └─► install.sh  (thin delegate — exec bash setup.sh "$@")
                └─► setup.sh  (canonical bootstrap)
                      ├── creates skills/orchestrator/engine/.venv (Python 3.11+)
                      ├── pip install playwright openpyxl
                      ├── playwright install chromium
                      ├── creates .env template
                      ├── runs smoke test
                      └── writes .installed sentinel

skills.sh install path:
  npx skills add alo-exp/multai
    └─► SKILL.md files installed (no scripts run)
          └─► Orchestrator SKILL.md Phase 1 venv check
                ├── .venv present? → proceed normally
                └── .venv absent?  → show "run bash setup.sh" message
                                          └─► User runs: bash setup.sh

Clone/dev path:
  git clone → bash setup.sh  (direct)
```

### Key Behaviors

| Behavior | Detail |
|----------|--------|
| **Idempotency** | If `.venv` already exists, `setup.sh` reuses it without re-checking the system Python version or reinstalling packages. |
| **`.installed` sentinel** | Written by `setup.sh` at the repo root. The `SessionStart` hook checks for this file and skips re-running `setup.sh` on every subsequent session. |
| **`--with-fallback` flag** | Optional. When passed to `setup.sh`, also installs `browser-use`, `anthropic`, and `fastmcp` for the vision-based agent fallback path. |
| **Python version** | Python 3.11 or later is required. `setup.sh` validates the system Python version before creating the venv. |

### Key Locations

| Artifact | Path |
|----------|------|
| Canonical bootstrap | `setup.sh` (repo root) |
| Hook delegate | `install.sh` (repo root) |
| Virtual environment | `skills/orchestrator/engine/.venv` |
| Requirements file | `skills/orchestrator/engine/requirements.txt` |
| Sentinel file | `.installed` (repo root, gitignored) |

---

### 3.7 Cross-Skill Domain Knowledge Enrichment

All skills participate in domain knowledge enrichment:

| Skill | When it enriches | What it proposes |
|-------|-----------------|-----------------|
| **landscape-researcher** | Phase 5 (after consolidation) | General domain knowledge, market segmentation, emerging categories |
| **solution-researcher** | Phase 5 (after consolidation) | New evaluation categories, new terminology, cross-skill general knowledge |
| **consolidator** | Phase 4 (after synthesis) | Source reliability observations, cross-AI disagreements |
| **comparator** | Phase 5 (after matrix update) | New archetypes, inference patterns, tick-count baselines, feature equivalences |

Enrichment is **append-only** and **timestamped**. All proposed changes require user approval.

### 3.8 Prompt-Echo Detection Flow

```
Prompt text (6000+ chars)
    │
    ▼
auto_extract_prompt_sigs(prompt)
    │ Finds ALL-CAPS phrases: "SYSTEM ROLE & MINDSET",
    │ "ANALYSIS PROTOCOL", "CONSTRAINTS", etc.
    ▼
prompt_sigs = ["SYSTEM ROLE & MINDSET", "ANALYSIS PROTOCOL", ...]
    │
    ▼  (set on each platform instance)
platform.prompt_sigs = prompt_sigs
    │
    ▼  (during extract_response)
is_prompt_echo(extracted_text, self.prompt_sigs)
    │ Checks if extracted_text[:3000] contains any signature
    ▼
True → skip (this is the echoed prompt, not the AI response)
False → accept (this is the actual AI response)
```

---

## 4. Module Design

### 4.1 skills/orchestrator/engine/prompt_echo.py

```python
"""Generic prompt-echo detection module."""

def auto_extract_prompt_sigs(prompt: str, max_sigs: int = 5) -> list[str]:
    """Extract distinctive phrases from the prompt.
    Strategy: ALL-CAPS phrases (section headers), then long distinctive words.
    Used to detect when a platform echoes the user's prompt on the page."""

def is_prompt_echo(text: str, prompt_sigs: list[str], sample_size: int = 3000) -> bool:
    """Return True if text appears to be the echoed user prompt."""
```

### 4.2 skills/orchestrator/engine/rate_limiter.py

```python
@dataclass
class PreflightResult:
    allowed: bool
    wait_seconds: int = 0
    reason: str = ""
    budget_remaining: int = 0
    budget_total: int = 0

class RateLimiter:
    def __init__(self, tier: str = "free", state_path: str | None = None): ...
    def load_state(self) -> None: ...             # Read JSON, prune expired
    def save_state(self) -> None: ...             # Atomic write (tmp + rename)
    def preflight_check(self, platform: str, mode: str) -> PreflightResult: ...
    def record_usage(self, platform: str, mode: str, status: str, duration_s: float) -> None: ...
    def get_staggered_order(self, platforms: list[str], mode: str) -> list[tuple[str, float]]: ...
    def get_budget_summary(self, mode: str) -> dict[str, dict]: ...
```

**Pre-flight checks (in order):**
1. Daily cap not exceeded (if `daily_cap > 0`)
2. Rolling window budget not exhausted (`count_in_window < max_requests`)
3. Cooldown elapsed since last request (`time_since_last >= cooldown_seconds`)
4. Exponential backoff if recently rate-limited (`cooldown * 2^min(consecutive_rate_limits, 4)`)

**Persistence:** `~/.chrome-playwright/rate-limit-state.json` — atomic writes, auto-prunes expired records.

### 4.3 skills/orchestrator/engine/collate_responses.py

```python
# Canonical platform order for archive sections
_PLATFORM_ORDER = ["Claude.ai", "ChatGPT", "Microsoft-Copilot",
                   "Perplexity", "Grok", "DeepSeek", "Google-Gemini"]

def collate(output_dir: str, task_name: str) -> Path | None:
    """Merge all *-raw-response.md files in output_dir into a single archive.
    Reads status.json for per-platform metadata (mode, chars, duration, status).
    Returns Path to archive, or None if no response files found."""

def main() -> None:
    """Standalone entry point: python3 collate_responses.py <output-dir> [task-name]"""
```

**Output file:** `{output_dir}/{task_name} - Raw AI Responses.md`

**Archive format:**
- Header: `# {task_name} — Raw AI Responses` with generated timestamp, mode, platform count
- One `## {Platform}` section per platform in canonical order, with metadata italics line
- Sections separated by `---` dividers
- Called automatically by `orchestrator.py` after every run; also callable standalone

### 4.4 skills/orchestrator/engine/orchestrator.py

```python
def parse_args() -> argparse.Namespace:
    """Generic CLI: --prompt/--prompt-file, --mode, --output-dir, --platforms,
       --tier, --skip-rate-check, --budget, --stagger-delay."""

def load_prompts(args) -> tuple[str, str, list[str]]:
    """Load full prompt, condensed prompt, and auto-extract echo sigs."""

async def run_single_platform(
    platform_name, context, full_prompt, condensed_prompt,
    prompt_sigs, mode, output_dir, agent_manager
) -> dict:
    """Create page, set platform.prompt_sigs, run lifecycle."""

async def _staggered_run(
    platform_name, delay_seconds, context, full_prompt, condensed_prompt,
    prompt_sigs, mode, output_dir, agent_manager, limiter
) -> dict:
    """Wait stagger delay, run platform, record usage."""

def show_budget(args) -> None:
    """Print rate limit budget table and exit."""

async def orchestrate(args) -> list[dict]:
    """Rate limiter init → pre-flight → staggered launch → status output."""
```

### 4.5 skills/orchestrator/engine/platforms/base.py

```python
class BasePlatform:
    name: str = ""
    url: str = ""
    display_name: str = ""
    agent_manager = None
    prompt_sigs: list[str] = []    # Set by orchestrator

    async def run(self, page, prompt, mode, output_dir) -> PlatformResult: ...
    async def check_rate_limit(self, page) -> str | None: ...  # Override per-platform
    async def configure_mode(self, page, mode) -> str: ...     # Override
    async def completion_check(self, page) -> bool: ...        # Override
    async def extract_response(self, page) -> str: ...         # Override
```

**Rate limit lifecycle integration:**
- `check_rate_limit()` called after `page.goto()` / before `configure_mode()` — early exit
- `check_rate_limit()` called each poll cycle in `_poll_completion()` — mid-generation detection
- Base class provides common pattern detection; all 7 platforms override with specific selectors

### 4.6 Platform Extraction (Generic Pattern)

All platforms follow the same decoupled extraction pattern:

```python
from prompt_echo import is_prompt_echo

# Primary: platform-specific selector (CSS class, aria-label, etc.)
text = await specific_selector.inner_text()
if text and len(text) > threshold and not is_prompt_echo(text, self.prompt_sigs):
    return text

# Secondary: generic Markdown heading detection
body = await page.evaluate("document.body.innerText")
for marker in ["# ", "## "]:
    # Scan all occurrences, pick LAST one not matching prompt
    for idx in reversed(positions):
        candidate = body[idx:]
        if not is_prompt_echo(candidate, self.prompt_sigs) and len(candidate) > 500:
            return candidate

# Tertiary: full body text (with prompt-echo guard)
```

---

## 5. Interface Contracts

### 5.1 Engine CLI Contract

**Input:** Command-line arguments (see SRS Section 6.1)
- Includes `--task-name` (recommended; routes output to `reports/{task-name}/`)
- Includes `--tier` (free/paid), `--skip-rate-check`, `--budget`, `--stagger-delay`

**Output:** Files in `reports/{task-name}/` (or `--output-dir` if no `--task-name`):
- `status.json` — always written
- `{Platform}-raw-response.md` — one per successful platform
- `{task-name} - Raw AI Responses.md` — auto-generated collated archive (always written)
- `agent-fallback-log.json` — only if fallback events occurred

**Side effects:**
- `~/.chrome-playwright/rate-limit-state.json` — usage state read/updated per run

**Exit codes:**
- 0: At least one platform completed successfully (or `--budget` mode)
- 1: All platforms failed

### 5.2 Skill Invocation Contract

Skills are invoked by the host AI (Claude Code) following SKILL.md instructions. Skills communicate via files:

| From | To | Via |
|------|----|-----|
| Orchestrator Skill → Engine | CLI invocation | `python3 skills/orchestrator/engine/orchestrator.py --prompt-file ...` |
| Engine → Orchestrator Skill | File output | `reports/status.json`, `reports/*-raw-response.md` |
| Orchestrator Skill → Consolidator Skill | File input | `[Topic] - Raw AI Responses.md` |
| Solution Researcher → Orchestrator | CLI args | Prompt file path, mode, platforms |
| Solution Researcher → Consolidator | File input | Raw archive + consolidation-guide.md |
| Consolidator → Solution Researcher | File output | `[Product] - Consolidated Intelligence Report.md` |
| Solution Researcher → Comparator | Skill invocation | CIR path + matrix path + domain name |
| Comparator → matrix_ops.py | CLI invocation | `python3 skills/comparator/matrix_ops.py add-platform ...` |
| Comparator → matrix_builder.py | CLI invocation | `python3 skills/comparator/matrix_builder.py --config ...` |
| Landscape Researcher → Engine | Via orchestrator | Prompt file path, mode, platforms |
| Landscape Researcher → Consolidator | File input | Raw archive + consolidation-guide.md (9-section) |
| Landscape Researcher → launch_report.py | CLI invocation | `python3 skills/landscape-researcher/launch_report.py --report-dir ... --report-file ...` |
| matrix_ops.py → Comparator | JSON stdout | `{ticks_applied, new_rows_added, orphans, ...}` |
| All skills ↔ Domain Knowledge | Read/append | `domains/{domain}.md` (enriched by all skills) |

### 5.3 Domain Knowledge File Contract

**Format:** Markdown with required and optional sections:

Required sections (minimum for any domain):
1. `## Evaluation Categories` — bullet list of domain-specific capability groups
2. `## Key Terminology` — domain vocabulary and abbreviations
3. `## Evaluation Criteria` — numbered list of weighting criteria for consolidation

Optional sections (populated by comparator and accumulated over time):
4. `## Platform Archetypes` — platform types with expected tick ranges
5. `## Inference Patterns` — reusable domain-specific judgment rules
6. `## CIR Evidence Rules` — how to interpret CIR variants for tick decisions
7. `## Matrix Categories` — lifecycle-ordered category list
8. `## CIR-to-Matrix Category Cross-Reference` — section mapping table
9. `## Common Feature Name Equivalences` — CIR↔matrix name mappings
10. `## New Row Guidelines` — rules for adding features to mature matrices
11. `## Priority Weights` — scoring weights by priority level

**Enrichment protocol:** ALL skills (landscape-researcher, solution-researcher, consolidator, comparator) propose timestamped append-only additions. Additions are appended, never deleted. The host AI presents proposed changes for user approval.

### 5.4 Matrix XLSX Contract

**Layout (auto-detected):**
- With title: Row1=title(merged), Row2=headers, Row3=COUNTIF, Row4=score, Row5+=data
- Without title: Row1=headers, Row2=COUNTIF, Row3=score, Row4+=data

**Column layout:** ColA=feature/category, ColB=priority, ColC+=platforms

**Detection:** `_Layout(ws)` checks if cell B1 == "Priority" to determine which format.

**Golden Rules (enforced by matrix_ops.py):**
1. Never hardcode styles — clone from existing cells
2. Unmerge before writing, re-merge after
3. Never use ws.insert_rows() — corrupts rows
4. Row type detection by col-A value + col-B presence
5. Cache styles before column reorder
6. Validate features against matrix (orphan check)

---

## 6. Key Design Decisions

### 6.1 Why separate engine from skills?

The engine is a Python process that manages Chrome and Playwright. Skills are markdown instructions for the host AI. Separating them means:
- The engine can be invoked by ANY skill (not just solution research)
- Skills can be added/modified without touching Python code
- The engine has no dependency on the host AI type (could work with Claude, GPT, etc.)

### 6.2 Why auto-extract prompt signatures instead of requiring explicit sigs?

The `auto_extract_prompt_sigs()` function makes the engine truly generic. The caller doesn't need to know about prompt-echo detection internals. The algorithm (find ALL-CAPS headers + distinctive long words) works for any structured prompt. An explicit `--prompt-sigs` flag is available as an escape hatch.

### 6.3 Why generic Markdown heading markers instead of domain-specific markers?

Hardcoded markers like "Executive Summary" or "Capability Analysis Report" only work for solution research prompts. Generic markers (`# `, `## `) detect the start of any structured AI response. Combined with prompt-echo filtering, this correctly identifies the AI response regardless of the prompt type.

### 6.4 Why file-based communication between skills?

Skills run in the host AI's context (Claude Code). The simplest, most reliable communication mechanism is the filesystem. Files are:
- Inspectable by the user
- Persistent across skill invocations
- Not dependent on IPC, sockets, or APIs
- Compatible with any host AI that can read/write files

### 6.5 Why offload XLSX operations to Python (not LLM)?

The comparator's predecessor was a 752-line SKILL.md that instructed the LLM to manually manage openpyxl operations, cell styles, formula writing, merge/unmerge, and golden-rule compliance — consuming ~33K tokens per add-platform cycle. The new approach:
- **Python handles all deterministic XLSX work** (matrix_ops.py, matrix_builder.py) — styles, formulas, merges, row detection, validation
- **LLM handles only judgment calls** — reading CIRs, deciding ticks, applying inference patterns
- **Result:** ~78% token reduction (33K → ~7K tokens per add-platform cycle)
- **6 Golden Rules baked into code** — the LLM cannot accidentally violate them
- **CLI + JSON pattern** — scripts output structured JSON to stdout; LLM reads results

### 6.6 Why auto-detect XLSX layout?

Existing matrices may not have a title row (headers in row 1), while newly built matrices include one (row 1 = title, row 2 = headers). The `_Layout` class auto-detects the format by checking if cell B1 == "Priority", making all operations work on both formats without manual configuration.

### 6.7 Why domain knowledge as .md files (not code)?

Domain knowledge is consumed by the host AI during consolidation (Phase 5). Since the host AI reads markdown natively, a .md file is the most natural format. It's also:
- Human-readable and editable
- Enrichable by the host AI without coding
- Versionable alongside the rest of the project

### 6.8 Why centralized rate limiting with persistent state?

AI platforms enforce usage limits (requests per time window, daily caps) that vary by subscription tier and mode. Without tracking, repeated orchestration runs risk hitting platform rate limits, wasting 15-50 minutes per timed-out platform and potentially triggering longer bans.

The `rate_limiter.py` module:
- **Pre-flight budget checks** skip platforms before launch (saves wall-clock time)
- **Staggered launch ordering** (5s apart, most budget first) avoids burst traffic patterns
- **Exponential backoff** after rate-limit hits (cooldown × 2^n, max 16×) prevents repeat violations
- **Persistent state** (`~/.chrome-playwright/rate-limit-state.json`) survives across sessions and project directories
- **Two-tier system** (free/paid) accommodates different subscription levels with 3-10× budget differences

### 6.9 Why per-platform `check_rate_limit()` in the base lifecycle?

Rate limit indicators are platform-specific (different banner text, different UI patterns). By adding `check_rate_limit()` as a base lifecycle method with per-platform overrides:
- Detection happens at two points: after page load (early exit) and each poll cycle (mid-generation)
- Previously only 2 of 7 platforms detected rate limits; now all 7 do
- A rate-limited platform exits immediately instead of polling until timeout (saves 5-15 minutes per platform)

### 6.10 Self-Improving Skills Pattern

Each skill follows a **Self-Improve** pattern: after every successful run, the skill appends a timestamped entry to a `## Run Log` section in its own `SKILL.md`. The entry records the task context, what worked, what failed, and any parameter adjustments the skill made during the run. The skill may also update its own templates, scripts, or default parameters based on what it learned.

**Scope boundary:** A skill only modifies files within its own directory (`skills/{skill-name}/`). It never edits another skill's files, the engine, or domain knowledge outside the enrichment protocol described in Section 3.7.

**Purpose:** This creates a continuous improvement loop without human intervention. Each run refines the skill's heuristics, prompt wording, and operational parameters. The cumulative run log also serves as an **audit trail** -- reviewers can trace when and why a skill changed its own behaviour. Because entries are append-only and timestamped, no historical context is lost, and regressions can be traced back to the specific run that introduced them.

### 6.11 Dependency Bootstrap (v4.1)

The project supports two distinct installation paths, both of which converge on `setup.sh` as the canonical bootstrap:

#### Plugin Install Path (Claude Desktop GUI / `claude plugin install`)

```
SessionStart hook (hooks/hooks.json)
    │
    └──► install.sh  (thin delegate — exec bash setup.sh "$@")
              │
              └──► setup.sh
                        │
                        ├── Creates skills/orchestrator/engine/.venv (Python 3.11+)
                        ├── Installs playwright>=1.40.0, openpyxl>=3.1.0
                        ├── Runs playwright install chromium
                        ├── Creates .env template
                        └── Writes .installed sentinel
```

The `SessionStart` hook fires `install.sh` on the first session. The `.installed` sentinel file prevents re-invocation on all subsequent sessions. The user takes no manual action.

#### skills.sh Install Path (`npx skills add alo-exp/multai`)

```
npx skills add alo-exp/multai
    │
    └──► SKILL.md files installed only (no hook runs)
              │
              └──► orchestrator/SKILL.md Phase 1 venv check
                        │
                        ├── .venv present? → proceed normally
                        └── .venv absent?  → show "run bash setup.sh" message
                                                    │
                                                    └──► User runs: bash setup.sh
```

The user must manually run `bash setup.sh` after a `skills.sh` install. The orchestrator Phase 1 detects the missing `.venv` and provides the exact command.

#### Clone / Dev Path

```
git clone → bash setup.sh
```

Direct `bash setup.sh` invocation. Same result as above.

#### Key Locations

| Artifact | Path |
|----------|------|
| Bootstrap script | `setup.sh` (repo root) |
| Hook delegate | `install.sh` (repo root) |
| Virtual environment | `skills/orchestrator/engine/.venv` |
| Requirements file | `skills/orchestrator/engine/requirements.txt` |
| Sentinel file | `.installed` (repo root, gitignored) |

---

## 7. Error Handling Strategy

| Layer | Error | Handling |
|-------|-------|---------|
| Engine | Chrome not found | Exit with error message; SKILL.md Phase 1 pre-checks |
| Engine | Platform timeout | Save partial content if >500 chars; mark as `partial` or `timeout` |
| Engine | Platform over budget (pre-flight) | Skip platform before launch; mark as `rate_limited` in results |
| Engine | Platform rate limited (page banner) | Detect via `check_rate_limit()` on page load + each poll cycle; mark as `rate_limited` |
| Engine | Platform rate limited (mid-generation) | `check_rate_limit()` in poll loop exits early; partial content saved if available |
| Engine | Extraction returns <200 chars | Try Agent fallback; if still fails, mark as `failed` |
| Engine | Playwright selector fails | Try Agent fallback (browser-use); if fails, raise error |
| Engine | Agent fallback disabled | Re-raise original Playwright error |
| Skill | Engine exit code 1 | Report failure to user; suggest re-run with `--platforms` subset |
| Skill | Partial results | Proceed with consolidation using available responses |
| Skill | Domain file not found | Proceed without domain knowledge; note in output |
