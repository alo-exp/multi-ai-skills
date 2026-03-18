---
name: multi-ai-orchestrator
description: >
  Intelligent Multi-AI Router & Orchestrator. Owns and invokes the
  Playwright/Browser-Use multi-AI engine at skills/orchestrator/engine/.

  This skill is the PRIMARY ENTRY POINT for all research and multi-AI tasks.
  It reads the user's intent and routes to the correct specialist skill:

  - "landscape" / "market map" / "ecosystem" / "vendor landscape" / "market
    overview" / "competitive landscape" / "category survey" / "industry
    landscape" / "Gartner-style" → landscape-researcher skill

  - Product URL + research intent, specific product name + evaluate/benchmark/
    research/analyze, "competitive intelligence", "capabilities report" →
    solution-researcher skill

  - "comparison matrix" / "add platform" / "update matrix" / "combo column" /
    "verify ticks" / "reorder matrix" → comparator skill

  - Any other multi-AI task, arbitrary prompt, or general question →
    direct multi-AI (this skill runs the engine and consolidates generically)

  USE THIS SKILL proactively whenever the user asks to run something across
  multiple AIs, compare AI outputs, get multi-source perspectives, or whenever
  a specialist skill (landscape-researcher, solution-researcher, comparator)
  would be appropriate. When in doubt, activate this skill — it will route
  correctly.
---

# Multi-AI Orchestrator Skill

This skill is the entry point for all research and multi-AI workflows. It routes
to the right specialist skill or, for arbitrary tasks, runs the engine directly
and consolidates generically. Follow the phases below.

---

## Phase 0 — Route Decision

Identify the user's intent and announce your routing decision **before acting**.

```
Routing decision tree:

"landscape" / "market map" / "ecosystem" / "vendor landscape" / "market overview"
"competitive landscape" / "category survey" / "industry landscape" / "Gartner-style"
  → ROUTE: landscape-researcher skill (invoke its Phase 0 onward)

Product URL + research intent
  OR specific product name + evaluate / benchmark / research / analyze
  OR "competitive intelligence" / "capabilities report"
  → ROUTE: solution-researcher skill (invoke its Phase 0 onward)

"comparison matrix" / "add platform" / "update matrix" / "combo column"
"verify ticks" / "reorder matrix"
  → ROUTE: comparator skill (invoke its Phase 0 onward)

Everything else (arbitrary prompt, general question, multi-source analysis
without a specific product or landscape intent)
  → Direct multi-AI (continue to Phase 1 below)
```

Tell the user which route you've selected: *"Routing to [skill name] — [brief reason]."*
Accept a user override: if they say "no, do X instead", re-route accordingly.

---

## Phase 1 — Setup (Direct Multi-AI Path)

*Skip this phase if you've routed to a specialist skill.*

### Accept inputs:
- **Prompt** — the full prompt text, or a path to a prompt file (required)
- **Mode** — `DEEP` or `REGULAR` (default: REGULAR)
- **Condensed prompt** *(optional)* — shorter version for constrained platforms
- **Topic label** *(optional)* — used for naming the output archive

If the prompt is inline text, write it to a temp file:
```bash
cat > /tmp/orchestrator-prompt.md << 'PROMPT_EOF'
[PROMPT TEXT HERE]
PROMPT_EOF
```

### Verify environment:

Check that the engine's virtual environment exists and is bootstrapped:

```bash
ls skills/orchestrator/engine/.venv/bin/python 2>/dev/null && echo "venv OK" || echo "venv MISSING"
```

**If the output is `venv MISSING`**, stop and tell the user:

> "The MultAI engine environment is not set up yet. Please run the one-time bootstrap from the repo root:
>
> ```bash
> bash setup.sh
> ```
>
> This installs Playwright, Chromium, and openpyxl into an isolated virtual environment. Run `bash setup.sh --with-fallback` to also install the browser-use agent. Once complete, re-invoke this skill."

Do not proceed to Phase 2 until the venv exists.

---

## Phase 2 — Run the Engine

```bash
cd <workspace-root>

python3 skills/orchestrator/engine/orchestrator.py \
    --prompt-file <PROMPT_FILE_PATH> \
    --mode [DEEP|REGULAR] \
    --task-name "<Short Task Name>"
```

Output goes to `reports/<Short Task Name>/`.
The engine auto-collates all responses into `reports/<task-name>/<task-name> - Raw AI Responses.md`.

**CLI options:**
| Flag | Required | Description |
|------|----------|-------------|
| `--prompt-file` | Yes* | Path to prompt file |
| `--prompt` | Yes* | Literal prompt text (*mutually exclusive with --prompt-file*) |
| `--task-name` | **Recommended** | Short run label — output saved to `reports/{task-name}/` |
| `--condensed-prompt` | No | Condensed prompt text for constrained platforms |
| `--condensed-prompt-file` | No | Path to condensed prompt file (alternative to `--condensed-prompt`) |
| `--mode` | No | `DEEP` or `REGULAR` (default: REGULAR) |
| `--output-dir` | No | Override output directory (ignored if `--task-name` is set) |
| `--platforms` | No | Comma-separated platform names, or `all` (default: `all`) |
| `--chrome-profile` | No | Chrome profile name (default: `Default`) |
| `--headless` | No | Run headlessly (not recommended) |
| `--fresh` | No | Force launch new Chrome instance |
| `--tier` | No | Subscription tier: `free` or `paid` (default: `free`) |
| `--skip-rate-check` | No | Bypass rate limit pre-flight checks |
| `--budget` | No | Show rate limit budget summary and exit |
| `--stagger-delay` | No | Seconds between platform launches (default: `5`) |

**Timeouts:**
- REGULAR mode: 15-minute global ceiling → set Bash timeout to 20 min
- DEEP mode: 50-minute global ceiling → set Bash timeout to 60 min

### Rate Limiting

The engine tracks usage per platform and enforces conservative rate limits.

1. **Pre-flight check**: platforms over budget are skipped with `rate_limited` status
2. **Staggered launch**: platforms launch 5 seconds apart (configurable)
3. **Cooldown enforcement**: minimum time between consecutive runs per platform
4. **Usage persistence**: state saved to `~/.chrome-playwright/rate-limit-state.json`
5. **Runtime detection**: all 7 platforms check for rate-limit banners

Check budget before running:
```bash
python3 skills/orchestrator/engine/orchestrator.py --prompt "test" --budget --tier free
```

---

## Phase 3 — Read Results

After the engine completes, outputs are in `reports/<task-name>/`:

| File | Description |
|------|-------------|
| `status.json` | Per-platform terminal status and metadata |
| `{Platform}-raw-response.md` | Individual raw response per platform |
| `{task-name} - Raw AI Responses.md` | **Auto-generated archive** — all responses collated |

Platform statuses: `complete` / `partial` / `failed` / `timeout` / `rate_limited`

---

## Phase 4 — Auto-Collation

The engine automatically runs `collate_responses.py` at end of each run.
To re-run collation manually on an existing output dir:
```bash
python3 skills/orchestrator/engine/collate_responses.py reports/<task-name>/ "<Task Name>"
```

---

## Phase 5 — Invoke Consolidator (Direct Multi-AI Path)

*Skip this phase if you've routed to a specialist skill — they invoke the consolidator themselves.*

Invoke the consolidator skill with:
- **Raw responses archive:** `reports/{task-name}/{task-name} - Raw AI Responses.md`
- **No consolidation guide** (generic synthesis — the consolidator applies its default structure)
- **No domain knowledge file** (unless the user specified a domain)

The consolidator will produce a generic synthesis covering: summary, consensus areas,
disagreements, unique insights, gaps, and source reliability.

---

## Phase 6 — Self-Improve

After each successful direct multi-AI run, append a run log entry and note any
observations about the engine, rate limiting, or routing logic.

**Scope boundary:** Only update files inside `skills/orchestrator/`. Never modify
other skills' files or the domain files.

---

## Run Log

<!-- Append new entries at the top of this section after each run -->
