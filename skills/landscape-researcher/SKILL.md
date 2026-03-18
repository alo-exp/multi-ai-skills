---
name: landscape-researcher
description: >
  Market Landscape Researcher: orchestrates a full end-to-end landscape research
  workflow for any software solution category. Builds a research prompt from a
  proven template, runs it across 7 AI platforms in parallel (via the orchestrator
  skill), synthesises the responses into a structured 9-section Market Landscape
  Report, and auto-launches an interactive HTML report viewer.

  USE THIS SKILL whenever the user wants any of: a market landscape report,
  competitive landscape analysis, market overview, vendor landscape, category
  survey, ecosystem analysis, or industry landscape for any software category.

  Also trigger when the user says things like "map the market for X", "give me a
  Gartner-style analysis of X", "which tools are leaders in X", "compare all the
  tools in X", "landscape for X", or "research the X market".

  This skill is also invoked by the orchestrator skill's routing logic when it
  detects landscape-research intent.

  DEEP mode is the default — landscape reports benefit from deep, multi-source
  research.
---

# Landscape Researcher Skill

This skill produces a world-class, analyst-grade Market Landscape Report for any
software solution category by running your prompt across 7 AI platforms and
synthesising the results. Follow the phases below in order.

---

## Phase 0 — Extract Inputs

Extract from the user's request (ask if missing):

- **Solution category** *(required)* — e.g., "Platform Engineering Solutions", "Project Management SaaS", "Customer Data Platforms"
- **Target audience** *(optional, default: "CTOs, Heads of Engineering/Operations/Product, and senior procurement leads at SMBs")*
- **Scope modifiers** *(optional)* — e.g., "focus on open-source options", "exclude enterprise-only tools", "SMB focus only"
- **Domain** *(optional)* — infer from the category if possible (e.g., "devops-platforms"). Check if `domains/{domain}.md` exists.
- **Mode** — default is `DEEP`. Override to `REGULAR` only if the user explicitly asks for a faster/lighter run.

---

## Phase 1 — Build Prompt

### Step 1: Load the prompt template

Read `skills/landscape-researcher/prompt-template.md`. Extract the prompt from inside the fenced code block (between the ``` markers).

### Step 2: Fill placeholders

Replace these placeholders in the extracted prompt:
- `[SOLUTION_CATEGORY]` → the solution category from Phase 0
- `[TARGET_AUDIENCE]` → the target audience (use the default if not specified)
- `[SCOPE_MODIFIERS]` → any scope modifiers, or **remove the entire `[SCOPE MODIFIERS]` line** if none

### Step 3: Optionally append domain knowledge

If `domains/{domain}.md` exists, append its content to the prompt under a new section:

```
DOMAIN-SPECIFIC CONTEXT
The following context from prior research in this domain may inform your analysis.
Use it to calibrate terminology, identify expected archetypes, and validate vendor coverage:

[content of domains/{domain}.md]
```

### Step 4: Generate condensed prompt

Create a condensed version (≤900 chars) for constrained platforms:

```
Produce a comprehensive Market Landscape Report for [SOLUTION_CATEGORY].
Cover: market definition & scope, market overview with size/CAGR, competitive
positioning (2×2 matrix, wave assessment, value curve), 5-10 key trends with SMB
impact, Top 20 commercial SMB solutions (overview + pros/cons + best-for/avoid-if),
Top 20 OSS solutions (same format), buying guidance with shortlist recipes, and
future outlook. Analyst voice, SMB lens throughout. No fabrication.
```

### Step 5: Write to temp file

```bash
cat > /tmp/landscape-prompt.md << 'PROMPT_EOF'
[FILLED PROMPT TEXT]
PROMPT_EOF
```

---

## Phase 2 — Invoke Orchestrator Engine

Generate a task name using the current date and time:
```
market-landscape-{YYYYMMDD}-{HHMM}
```

Run the engine (adjust path relative to your working directory — should be the `multai/` root):

```bash
cd <workspace-root>

python3 skills/orchestrator/engine/orchestrator.py \
    --prompt-file /tmp/landscape-prompt.md \
    --condensed-prompt "<condensed prompt from Step 4>" \
    --mode DEEP \
    --task-name "market-landscape-{YYYYMMDD}-{HHMM}"
```

Set Bash timeout to **60 minutes** for DEEP mode.

The engine writes raw responses to `reports/{task-name}/` and auto-collates them into:
`reports/{task-name}/{task-name} - Raw AI Responses.md`

**Read `reports/{task-name}/status.json`** to verify which platforms responded before proceeding.

---

## Phase 3 — Invoke Consolidator

Invoke the consolidator skill with:
- **Raw responses archive:** `reports/{task-name}/{task-name} - Raw AI Responses.md`
- **Consolidation guide:** `skills/landscape-researcher/consolidation-guide.md`
- **Domain knowledge:** `domains/{domain}.md` (if it exists)

The consolidator reads the guide as the sole structural authority and produces the report.

**Expected output path:**
```
reports/{task-name}/{Solution Category} - Market Landscape Report.md
```

---

## Phase 4 — Launch Report Viewer

Run the launch script to start the HTTP preview server and open the report in the browser:

```bash
python3 skills/landscape-researcher/launch_report.py \
    --report-dir "{task-name}" \
    --report-file "{Solution Category} - Market Landscape Report.md" \
    --port 7788
```

The script:
1. Starts `python3 -m http.server 7788 --directory reports/` (skips if port already in use)
2. Builds a URL with the `?report=` query parameter (URL-encoded)
3. Opens the browser and prints the URL

**Present the URL to the user:**
```
Report available at:
http://localhost:7788/preview.html?report={task-name}/{encoded-filename}
```

---

## Phase 5 — Domain Knowledge Enrichment

After the report is generated, propose timestamped append-only additions to
`domains/{domain}.md`. The goal is to enrich the shared domain knowledge so that
future landscape runs AND future solution research runs can benefit.

### What to propose:

- **New or updated vendor archetypes** — e.g., "AI-Augmented Platform Engineering" emerged as a new subsegment
- **Emerging vendors to watch** — vendors mentioned by 2+ sources that aren't in the domain file yet
- **Market-wide trend signals** — category-level shifts observed across multiple vendors (not product-specific)
- **Category boundary clarifications** — what this landscape run revealed about inclusions/exclusions
- **Market size updates** — any verified figures that update or replace existing estimates

### Format (append-only, never overwrite):

```markdown
## Additions from landscape: {Solution Category} ({YYYY-MM-DD}) — landscape-researcher
- Archetype: [name] — [definition, criteria]
- Vendor: [name] — [category/archetype, notable for: ...]
- Trend: [trend name] — [signal observed, source count]
- Market size: [figure] — [confidence level, source]
```

**Present proposed additions to the user for approval before writing.**

---

## Phase 6 — Self-Improve

After each successful run, this skill updates its own files based on what was learned.
This keeps the skill sharp without requiring manual maintenance.

### What to update:

1. **Append a run log entry** to the `## Run Log` section at the bottom of this file:
   ```
   ### {YYYY-MM-DD} — {Solution Category} ({mode})
   - Platforms responded: {list}
   - Report quality: {brief assessment}
   - Prompt observations: {what worked / what could be improved}
   - Consolidation observations: {what worked / what could be improved}
   - Launch observations: {any issues with launch_report.py}
   - Changes made: {list any updates to prompt-template.md, consolidation-guide.md, launch_report.py}
   ```

2. **Update `prompt-template.md`** if you observed that the prompt produced:
   - Responses missing key sections consistently
   - Misinterpretation of Top 20 requirement (e.g., AIs only producing 10)
   - Poor-quality cons (euphemistic or vague)
   - Any other systematic quality gap

3. **Update `consolidation-guide.md`** if consolidation produced:
   - Sections out of order
   - Missing quality checklist items
   - Synthesis rules that caused information loss
   - A new structural improvement worth capturing

4. **Update `launch_report.py`** if the launch failed or produced an incorrect URL.

**Scope boundary:** Only update files inside `skills/landscape-researcher/`. Never modify the engine, other skills, or domain files (those are handled in Phase 5).

---

## Run Log

<!-- Append new entries at the top of this section after each run -->

### 2026-03-18 — Kubernetes container orchestration (TC-DOMAIN-1) — DEEP mode (1 platform)
- Platforms responded: 1/1 — Google Gemini Deep Research (40,901 chars, 212s, 1 source used: DR crawl)
- Source archive: `reports/e2e08-gemini-dr-v3/e2e08-gemini-dr-v3 - Raw AI Responses.md`
- Report quality: High — Gemini Deep Research produced a structured 9-section enterprise analysis covering architecture, resilience, resource optimization, CI/CD, security, multi-cloud, AI/ML convergence, GreenOps, and ecosystem trends with quantitative case studies (AppDirect, Galaxy FinX)
- Prompt observations: Generic prompt ("main benefits of container orchestration platforms like Kubernetes") produced comprehensive coverage but was not scoped to SMB landscape format; for a full landscape run, the prompt-template.md should be used to target Top 20 commercial + OSS structure
- Consolidation observations: Single-source DR run — no cross-source synthesis required; consolidation-guide.md 9-section structure not fully applied (single source, Phase 5 domain enrichment was the primary objective of this run)
- Domain enrichment: 7 timestamped additions to `domains/devops-platforms.md` — GreenOps trend, MLOps term, Kubeflow vendor, k0rdent vendor, 82% K8s adoption stat, VPA term, AI-powered K8s optimization trend
- Launch observations: No launch_report.py execution (TC-DOMAIN-1 targeted Phase 5 domain enrichment only)
- Changes made: none to prompt-template.md, consolidation-guide.md, or launch_report.py
