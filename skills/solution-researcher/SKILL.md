---
name: solution-researcher
description: >
  Orchestrates a simultaneous 7-AI competitive intelligence research round on any
  software product. Builds a capability-analysis prompt from a template, invokes
  the orchestrator engine, then invokes the consolidator skill to produce a
  Consolidated Intelligence Report (CIR).

  USE THIS SKILL whenever the user asks to research a software product, run
  competitive intelligence, benchmark a tool, or find out what a platform can do.
  Trigger when the user provides a product URL, names a specific software product
  and asks to research/analyze/evaluate it, or says "competitive intelligence",
  "capabilities report", "benchmark this tool", or "what can X do?".

  Supports any product domain (DevOps, PM tools, security, etc.) via pluggable
  domain knowledge files. If a domain file exists, evaluation criteria are appended
  to the prompt and used during consolidation.

  DEEP vs. REGULAR mode: If the user includes the keyword 'deep' in their request,
  use Deep Research modes on all platforms.
---

# Solution Research Skill

This skill orchestrates a full solution research workflow: build prompt, run 7 AIs,
consolidate results, enrich domain knowledge, and optionally update the comparison
matrix. Follow the phases below in order.

---

## Phase 0 — Extract Inputs

Extract from the user's request:
- **Primary URL** — the product's main website (required)
- **Scope context** — one-line description of what the product does (required)
- **Additional URLs** *(optional)* — docs, API reference, changelog, etc.
- **GitHub / repository URL** *(optional)* — for open-source products
- **Domain** *(optional)* — e.g., `devops-platforms`, `project-management`, `security-tools`
- **Research depth** — if the user includes **`deep`**, set `MODE = DEEP`. Otherwise `MODE = REGULAR`.

If Primary URL or Scope context is missing, ask the user before proceeding.

If the user doesn't specify a domain, try to infer from the scope context. Check if `domains/{domain}.md` exists.

---

## Phase 1 — Build Prompt

### Step 1: Load prompt template

Read `skills/solution-researcher/prompt-template.md`. The template contains a fenced code block with the raw prompt. Extract the prompt text from inside the code fence (between ``` markers).

### Step 2: Fill placeholders

Replace these placeholders in the extracted prompt:
- `[PRIMARY_URL]` → the product's URL
- `[SCOPE_CONTEXT]` → one-line product description
- `[ADDITIONAL_URLS]` → comma-separated extra URLs (or remove the line if none)
- `[GITHUB_URL]` → repository URL (or `N/A` if not applicable)

### Step 3: Append domain knowledge (if available)

If `domains/{domain}.md` exists:
1. Read the file
2. Append its content to the prompt under a new section:

```
DOMAIN-SPECIFIC EVALUATION CRITERIA
The following categories, terminology, and evaluation criteria are specific to the
{domain} domain. Use them to guide your analysis:

[content of domains/{domain}.md]
```

### Step 4: Generate condensed prompt

Create a condensed version (≤900 chars) for constrained platforms:

```
Analyze [PRIMARY_URL] ([SCOPE_CONTEXT]).
Produce: 1) Detailed Capability Report with Executive Summary, capability groups (5-12),
sub-capabilities with descriptions, plan/tier availability, and constraints.
2) Assumptions, Gaps & Ambiguities table.
3) Marketing Claims vs Demonstrated Capabilities comparison.
4) Product-agnostic Capabilities Checklist for competitive benchmarking.
Be precise. Use Markdown formatting.
```

### Step 5: Write prompt to temp file

```bash
cat > /tmp/research-prompt.md << 'PROMPT_EOF'
[FILLED PROMPT TEXT]
PROMPT_EOF
```

---

## Phase 2 — Invoke Orchestrator Engine

Generate a task name from the product name (e.g., `harness-oss`, `port-io`).

Run the engine:
```bash
cd <workspace-root>

python3 skills/orchestrator/engine/orchestrator.py \
    --prompt-file /tmp/research-prompt.md \
    --condensed-prompt "<condensed version from Step 4>" \
    --mode [DEEP|REGULAR] \
    --task-name "<product-task-name>"
```

Set Bash timeout to 60 min for DEEP, 20 min for REGULAR.

The engine writes raw responses to `reports/{task-name}/` and auto-collates them into:
`reports/{task-name}/{task-name} - Raw AI Responses.md`

---

## Phase 3 — Read Results

Read `reports/{task-name}/status.json` to verify all platforms have terminal statuses.

---

## Phase 4 — Invoke Consolidator

Invoke the consolidator skill with:
- **Raw responses archive:** `reports/{task-name}/{task-name} - Raw AI Responses.md`
- **Consolidation guide:** `skills/solution-researcher/consolidation-guide.md`
- **Domain knowledge:** `domains/{domain}.md` (if available)

The consolidator will produce a Consolidated Intelligence Report (CIR).

---

## Phase 5 — Domain Knowledge Enrichment

After consolidation, review the CIR for new patterns and propose append-only additions
to `domains/{domain}.md`. These additions should include **general domain knowledge** —
not just product-specific data — so that future landscape-researcher runs can also benefit.

### What to propose:

- **New capability categories** not in the domain file
- **New terminology** specific to this domain (including terms introduced by this vendor)
- **New inference patterns** — rules for deriving capability X from the presence of Y
- **New feature name equivalences** — when the CIR uses a different name for a known feature
- **Archetype insights** — if this product represents a new or refined archetype
- **Trend signals** — if the product embodies a trend worth tracking at the domain level

```markdown
## Additions from {Product Name} research ({YYYY-MM-DD}) — solution-researcher
- New category: [name]
- New term: [term] — [definition]
- Inference pattern: [pattern description]
- Trend signal: [trend] — [observation]
```

If no domain file exists and the user specified a domain, propose creating one with the
initial categories, terminology, and criteria discovered during this research.

**Present proposed changes to the user for approval before writing.**

---

## Phase 5b — Auto-Invoke Comparator

After consolidation and domain enrichment, automatically check if a comparison matrix
exists for this domain:

1. **Check for existing matrix:** Look in `reports/` for an existing `.xlsx` matrix file for this domain.
2. **If a matrix exists:**
   - Invoke the comparator skill with:
     - **CIR path:** the just-produced Consolidated Intelligence Report
     - **Matrix path:** the most recent `.xlsx` matrix for this domain
     - **Domain:** the current domain name
   - The comparator uses `skills/comparator/matrix_ops.py` to add the new platform column and reorder by score.
3. **If no matrix exists:** Skip this phase. The user can manually invoke the comparator later.

---

## Phase 6 — Present Deliverables

1. Confirm all files are saved in the `reports/` folder:
   - `{product-task-name}/{task-name} - Raw AI Responses.md`
   - `{Product Name} - Consolidated Intelligence Report.md`
   - Updated comparison matrix (if Phase 5b ran)
2. Present files and ranked scores (if comparator ran) to the user
3. If domain knowledge changes were proposed, present them for approval

---

## Phase 7 — Self-Improve

After a successful run, update this skill's own files based on what was learned.

1. **Append a run log entry** to the `## Run Log` section below:
   ```
   ### {YYYY-MM-DD} — {Product Name} ({mode})
   - Platforms responded: {list}
   - CIR quality: {brief assessment}
   - Prompt observations: {what worked / what could improve}
   - Consolidation observations: {structure issues / missed capabilities}
   - Comparator observations: {accuracy, orphan rate, archetype fit}
   - Changes made: {list any updates to prompt-template.md, consolidation-guide.md}
   ```

2. **Update `prompt-template.md`** if prompt quality issues were observed.
3. **Update `consolidation-guide.md`** if CIR structure issues were found.

**Scope boundary:** Only update files inside `skills/solution-researcher/`. Never modify
the engine, other skills, or domain files (domain enrichment is done in Phase 5 with user approval).

---

## Run Log

<!-- Append new entries at the top of this section after each run -->
