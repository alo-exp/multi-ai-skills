# Changelog

All notable changes to MultAI are documented in this file.

Versioning scheme: `Major.Minor.YYMMDDX Phase` — see [CI/CD Strategy](docs/CICD-Strategy-and-Plan.md) Section 7.1.

---

## 0.2.260331A Alpha — Orchestration Reliability & Tab Reuse

**Date:** 2026-03-31

### Engine: 7 Reliability Fixes

#### 1 — Explicit Playwright-Only Enforcement (SKILL.md)
Added a prominent `CRITICAL` banner to `skills/orchestrator/SKILL.md` explicitly banning Claude-in-Chrome MCP tools, computer-use tools, and any manual browser automation from being used in place of the Python Playwright engine. Prevents the host AI from attempting to do browser automation itself instead of invoking the script.

#### 2 — Sign-In Page Detection
New `is_sign_in_page()` method on `BasePlatform` detects login/sign-in pages via URL pattern matching (`/login`, `/signin`, `accounts.google.com`, etc.) and password-field presence. When detected, the engine attempts agent fallback to navigate past the page; if still on a login screen, returns a clear `STATUS_NEEDS_LOGIN` (🔑) result rather than silently failing or hanging.

New status code `STATUS_NEEDS_LOGIN = "needs_login"` added to `config.py` with a 🔑 icon in `STATUS_ICONS`.

#### 3 — Broader Agent Fallback Coverage
Agent fallback is now triggered in additional code paths previously missing coverage:
- Navigation failure (`page.goto()` errors)
- `click_send()` errors (previously fell through to Enter key only)
- `configure_mode()` errors (previously re-raised without agent attempt)

#### 4 — Pre-Flight: Warn-Only, Never Skip
Pre-flight rate-limit checks changed from a hard gate to warnings only. All requested platforms now always proceed to the browser — a platform is excluded only if it:
- Shows a sign-in page (`needs_login`)
- Is network-unreachable (`failed`)
- Returns on-page quota exhaustion (`rate_limited`)

This eliminates the prior behaviour where platforms were silently skipped due to budget/cooldown state.

#### 5 — Dynamic Global Timeout
The global `asyncio.wait_for` ceiling is now calculated dynamically:

```
global_timeout = max(per_platform_timeouts) + (num_platforms − 1) × stagger_delay + 60s
```

This ensures the last staggered platform always gets its full per-platform wait time before the hard ceiling fires, preventing premature cancellation of slow-finishing platforms.

#### 6 — Follow-Up Mode (`--followup`)
New `--followup` CLI flag. When set, the engine finds each platform's existing open browser tab (matched by URL domain) and injects the new prompt directly into the current conversation — no navigation, no mode reconfiguration, no new tabs. Use this for follow-up questions on the same research topic.

#### 7 — Tab Reuse for New Topics
Default behaviour (without `--followup`): the engine still finds existing open tabs for each platform, but navigates to the new-conversation URL within the found tab rather than opening a new one. Tab URLs are persisted to `~/.chrome-playwright/tab-state.json` after each run.

New `PLATFORM_URL_DOMAINS` constant in `config.py` maps each platform to its hostname for tab matching.

### Tests
- `UT-OR-12`: `--followup` flag defaults to `False`, set to `True` when supplied
- `UT-CF-09`: `PLATFORM_URL_DOMAINS` has 7 entries matching `PLATFORM_URLS` keys
- `UT-CF-10`: `STATUS_NEEDS_LOGIN` defined and present in `STATUS_ICONS`
- Total: 96 → **98 tests**

### Website & Docs
- `docs/index.html`: dark mode now default on first visit
- `docs/index.html`: comparison table headings center-aligned
- `README.md`: rate limiting, agent fallback, and tab reuse sections updated
- All doc headers and version badge bumped to `0.2.260331A Alpha`

---

## 0.2.260318A Alpha — Release Pipeline & Doc Restructure

**Date:** 2026-03-18

### Versioning
- Adopted hybrid semver + CalVer scheme: `Major.Minor.YYMMDDX Phase`
- Previous internal versions (v2.0–v4.2) consolidated into `0.2.260318A Alpha`
- All doc headers, pyproject.toml, website, and git tags updated

### Engine Hardening (15 bugs fixed across 3 E2E test rounds)
- Rate limiter timezone fix: `_count_today()` now uses local midnight consistently
- Agent fallback model names extracted to `config.py` constants
- All 7 platform adapters hardened: multi-selector fallbacks, improved rate-limit detection, DEEP mode toggles

### Documentation Restructure
- `USER-GUIDE.md` → `CONTRIBUTOR-GUIDE.md` (technical contributor reference)
- New `USER-GUIDE.md` created (friendly end-user guide, 296 lines)
- Rebranded all docs from "Multi-AI Skills" to "MultAI"
- Report viewer: DOCS nav row in top bar + sidebar footer links

### CI/CD Pipeline
- `.github/workflows/ci.yml` — GitHub Actions (Python 3.11/3.12/3.13 matrix)
- Security scanning: pip-audit + secret detection + plugin manifest validation
- 96 automated tests (91 in CI + 5 local-only venv tests)
- Full CI/CD Strategy doc rewrite with branching model, rollback procedure, Phase 2/3 roadmap

---

## [4.1.0] — 2026-03-18 (Internal)

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
