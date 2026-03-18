# Changelog

All notable changes to `multi-ai-skills` are documented in this file.

---

## [4.1.0] — 2026-03-18

### Summary

Dependency bootstrap overhaul. Introduced `setup.sh` as the canonical one-time installer, refactored `install.sh` to a thin delegate, fixed the `SessionStart` plugin hook chain, added `requirements.txt` under the engine directory, added a venv existence check in the orchestrator Phase 1, and updated all documentation for v4.1.

---

### New Files

| File | Description |
|------|-------------|
| `setup.sh` | Canonical bootstrap script (Python 3.11+): creates `skills/orchestrator/engine/.venv`, installs `playwright>=1.40.0` and `openpyxl>=3.1.0`, runs `playwright install chromium`, creates `.env` template, runs smoke test. `--with-fallback` flag also installs `browser-use==0.12.2`, `anthropic>=0.76.0`, `fastmcp>=2.0.0`. Idempotent: reuses existing `.venv` on re-run without re-checking system Python version. |
| `skills/orchestrator/engine/requirements.txt` | Explicit requirements file listing `playwright>=1.40.0` and `openpyxl>=3.1.0`. |
| `tests/test_setup_bootstrap.py` | 17 new tests covering TC-SETUP-1/3, TC-VENV-1, TC-HOOK-1/2, TC-LAUNCH-1/2. Total test suite: 75 tests (was 58). Now 93 with v4.2 additions. |

---

### Updated Files

| File | Change |
|------|--------|
| `install.sh` | Refactored from full install logic to a single-line delegate: `exec bash setup.sh "$@"`. Called by the `SessionStart` hook. |
| `skills/orchestrator/SKILL.md` | Phase 1 now checks for `.venv` existence before invoking the engine. Shows `bash setup.sh` instructions if missing. |

---

### Plugin Hook Chain

```
SessionStart hook (hooks/hooks.json)
    └──► install.sh  (delegates to setup.sh)
              └──► setup.sh  (creates .venv, installs deps, writes .installed sentinel)
```

The `.installed` sentinel file prevents re-invocation on subsequent sessions.

---

### Installation Paths (v4.1)

| Path | How dependencies are installed |
|------|-------------------------------|
| Plugin install (`claude plugin install`) | Automatic on first session start via `SessionStart` hook → `install.sh` → `setup.sh` |
| skills.sh install (`npx skills add alo-exp/multai`) | Manual: user runs `bash setup.sh` after install. SKILL.md Phase 1 detects missing `.venv` and prompts. |
| Clone / dev | Manual: `git clone` then `bash setup.sh` |

---

### Documentation Updates

| File | Changes |
|------|---------|
| `README.md` | Quick Start updated: `bash install.sh` → `bash setup.sh`; plugin auto-install note; project structure updated; Python ≥3.11; Running Tests uses `.venv/bin/python` |
| `USER-GUIDE.md` | Section 3.2 replaced with `bash setup.sh`; Section 3.3 uses `bash setup.sh --with-fallback`; Section 4 structure updated; Prerequisites Python 3.11+; Section 13 notes venv activation; Appendix C v4.1 entry |
| `docs/SRS.md` | Version table v4.1; Section 1.1 v4.1 bullet; Section 1.3 new definitions; Section 3.11 new FRs (FR-SETUP-1–3, FR-HOOK-1–2, FR-VENV-1); NFR-05 Python 3.11+ |
| `docs/Test-Strategy-and-Plan.md` | Version table v4.1; Section 2.8 new test cases (TC-SETUP-1–3, TC-VENV-1, TC-HOOK-1–2); Section 3.1 Python 3.11+ |
| `docs/CICD-Strategy-and-Plan.md` | Version table v4.1; Stage 1 setup.sh note; Stage 2 bash syntax checks; Stage 4 smoke test; GitHub Actions syntax check step; Python 3.11+ |
| `docs/Architecture-and-Design.md` | Version table v4.1; Section 6.11 Dependency Bootstrap (plugin path, skills.sh path, venv locations, sentinel) |

---

## [4.0.0] — 2026-03-16

### Summary

Complete architectural restructure. Introduced the `landscape-researcher` skill, an intelligent routing layer in the orchestrator, self-improving skills with run logs, self-contained skill ownership of Python scripts, and a shared domain knowledge model enriched by both research skills.

---

### New Files

| File | Description |
|------|-------------|
| `skills/landscape-researcher/SKILL.md` | Full end-to-end landscape research skill (6 phases) |
| `skills/landscape-researcher/prompt-template.md` | Parametrized landscape research prompt (`[SOLUTION_CATEGORY]`, `[TARGET_AUDIENCE]`, `[SCOPE_MODIFIERS]`) |
| `skills/landscape-researcher/consolidation-guide.md` | 9-section Market Landscape Report structure (consolidator authority) |
| `skills/landscape-researcher/launch_report.py` | Stdlib-only HTTP server launcher; opens `preview.html?report=<url-encoded-path>` |
| `domains/devops-platforms.md` | Shared domain knowledge file (enriched by both landscape-researcher and solution-researcher) |
| `CHANGELOG.md` | This file |

---

### Topology Changes

| Before | After |
|--------|-------|
| No routing layer — skills invoked directly | Orchestrator Phase 0 is an intelligent router |
| Engine at `engine/` (project root) | Engine at `skills/orchestrator/engine/` (orchestrator-owned) |
| `matrix_ops.py` / `matrix_builder.py` at `engine/` | Moved to `skills/comparator/` (comparator-owned) |
| No landscape research skill | `skills/landscape-researcher/` (new) |
| Skills had no self-improvement mechanism | Every skill has Self-Improve phase + `## Run Log` |
| Domain knowledge enriched by solution-researcher only | Domain knowledge enriched by both landscape-researcher and solution-researcher |
| Preview HTML hardcoded to one report | `preview.html?report=<path>` — query-param driven |

---

### Updated Files

#### `skills/orchestrator/SKILL.md`
- Added **Phase 0 — Route Decision** (routing decision tree; announce route; accept user override)
- Routing targets: landscape intent → `landscape-researcher`; product URL + research intent → `solution-researcher`; matrix ops → `comparator`; everything else → direct multi-AI
- Updated all engine invocation paths to `skills/orchestrator/engine/orchestrator.py`
- Added **Phase 5** (direct path): invoke consolidator generically after direct multi-AI runs
- Added **Phase 6 — Self-Improve** with `## Run Log` section

#### `skills/consolidator/SKILL.md`
- Phase 2 clarified: "The consolidation guide is the sole structural authority for output format. Do not introduce task-type knowledge beyond what the guide specifies."
- Added **Phase 5 — Self-Improve** with `## Run Log` section

#### `skills/solution-researcher/SKILL.md`
- Engine path updated to `skills/orchestrator/engine/orchestrator.py`
- Phase 5b comparator reference updated to `skills/comparator/matrix_ops.py`
- Phase 5 (domain enrichment): explicitly specifies general domain knowledge additions (archetypes, terminology, trend signals, inference patterns) — not just product-specific data — so landscape-researcher runs also benefit
- Added **Phase 7 — Self-Improve** with `## Run Log` section

#### `skills/comparator/SKILL.md`
- All `python3 engine/matrix_ops.py` references → `python3 skills/comparator/matrix_ops.py`
- All `python3 engine/matrix_builder.py` references → `python3 skills/comparator/matrix_builder.py`
- Added **Phase 7 — Self-Improve** with `## Run Log` section

#### `reports/preview.html`
- Replaced hardcoded `loadFile(...)` call with query-param-driven loader:
  ```javascript
  (function() {
    const params = new URLSearchParams(window.location.search);
    const report = params.get('report');
    if (report) {
      loadFile(decodeURIComponent(report));
    } else {
      loadFile('market-landscape-20260315-2128/Platform Engineering Solutions - Market Landscape Report.md');
    }
  })();
  ```
- Both landscape reports and CIRs render correctly via the existing `injectCharts()` handler

---

### Documentation Updates

| File | Changes |
|------|---------|
| `docs/Architecture-and-Design.md` | Rewritten topology section; landscape research data flow; domain knowledge sharing model; self-improving skills pattern (§6.10); all engine/comparator path references updated |
| `docs/SRS.md` | Added FR-LR (landscape-researcher FRs), FR-NEW-1–7 (routing, landscape, domain enrichment, self-improve, query-param preview); updated engine/comparator paths; updated Top 10 → Top 20 throughout; added UC-06 (landscape research use case) |
| `docs/Test-Strategy-and-Plan.md` | Added §3.4 Orchestrator Routing Tests (IT-RT-01–04), §3.5 launch_report.py Tests (IT-LR-01–03), §3.6 preview.html Tests (IT-PV-01–03); updated all path references |
| `docs/CICD-Strategy-and-Plan.md` | Updated all `engine/` paths → `skills/orchestrator/engine/`; updated matrix script paths → `skills/comparator/`; added `launch_report.py` to lint gate; added landscape workflow smoke test; updated requirements.txt path |

---

### Design Principles (v4.0)

1. **Skill ownership of Python** — Each skill owns its support scripts. Orchestrator owns the Playwright/Browser-Use engine. Comparator owns XLSX ops scripts. Skills are portable, self-contained modules.

2. **Intelligent routing** — The orchestrator is the single entry point. It announces its routing decision before acting and accepts user overrides.

3. **Self-improving skills** — Every skill has a Self-Improve phase that appends a timestamped `## Run Log` entry to its own SKILL.md and updates its own templates/scripts after each successful run. Scope boundary: skills only modify files inside their own `skills/{skill-name}/` directory.

4. **Shared domain knowledge** — `domains/{domain}.md` is a living document enriched by both `landscape-researcher` (market-wide signals, archetypes, vendor movements) and `solution-researcher` (product terminology, inference patterns, feature equivalences). All additions are append-only, timestamped, and require user approval before writing.

5. **Query-param report viewer** — `preview.html?report=<url-encoded-path>` loads any report dynamically. `launch_report.py` constructs the correct URL and opens the browser.

---

### Migration from 260308A

This implementation is a clean restructure of `solution-research-skill-260308A/`. The original directory is unchanged. Key file movements:

| 260308A source | multi-ai-skills destination |
|---|---|
| `engine/` (minus matrix scripts) | `skills/orchestrator/engine/` |
| `engine/matrix_ops.py` | `skills/comparator/matrix_ops.py` |
| `engine/matrix_builder.py` | `skills/comparator/matrix_builder.py` |
| `references/market-landscape-prompt.md` | `skills/landscape-researcher/prompt-template.md` |
| `references/platform-setup.md` | `skills/orchestrator/platform-setup.md` |
| `references/prompt-template.md` | `skills/solution-researcher/prompt-template.md` |
| `skills/solution-researcher/consolidation-guide.md` | `skills/solution-researcher/consolidation-guide.md` |
| `skills/*/SKILL.md` | `skills/*/SKILL.md` (updated) |
| `domains/devops-platforms.md` | `domains/devops-platforms.md` |
| `docs/*.md` | `docs/*.md` (updated for v4.0) |
| `.claude/launch.json` | `.claude/launch.json` |
| `reports/preview.html` | `reports/preview.html` (query-param update) |
