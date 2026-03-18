# Test Strategy and Plan

**Project:** Multi-AI Orchestrator Platform
**Version:** 4.1
**Date:** 2026-03-18

| Version | Date | Summary |
|---------|------|---------|
| 2.0 | 2026-03-13 | Initial test strategy for generic restructuring |
| 3.0 | 2026-03-13 | Added matrix engine tests (matrix_ops, matrix_builder, comparator) |
| 3.1 | 2026-03-14 | Added rate limiter tests (preflight, record, persistence, backoff, detection) |
| 3.2 | 2026-03-14 | Added task-name and collation tests (collate_responses, --task-name routing) |
| 4.0 | 2026-03-16 | Added routing, landscape-researcher, launch_report, preview.html, domain enrichment, and self-improvement tests; updated all engine path references |
| 4.1 | 2026-03-18 | Added setup bootstrap tests (TC-SETUP-1–3), plugin hook tests (TC-HOOK-1–2), venv check test (TC-VENV-1) |

---

## 1. Test Strategy Overview

### 1.1 Goals

1. Verify correctness of the orchestration engine (CLI, prompt-echo detection, rate limiting, output routing, auto-collation)
2. Ensure no regression in platform automation behaviour after each change
3. Validate all skill invocation contracts (orchestrator, consolidator, comparator, solution-researcher, landscape-researcher)
4. Verify matrix XLSX operations are deterministic, idempotent, and respect the 6 Golden Rules
5. Confirm rate limiting enforces budgets and cooldowns correctly across sessions
6. Confirm extensibility: new task types and domains work without engine changes

### 1.2 Test Pyramid

```
         ┌─────────────────┐
         │   E2E Tests      │   Slow, few, real Chrome + live platforms
         │   (manual + CI)  │
         ├─────────────────┤
         │  Integration     │   Engine CLI, file I/O, skill contract,
         │  Tests           │   matrix ops, collation, rate limit state
         ├─────────────────┤
         │  Unit Tests      │   prompt_echo.py, rate_limiter.py,
         │  (pytest, fast)  │   collate_responses.py, config.py,
         └─────────────────┘   matrix_ops.py, arg parsing
```

### 1.3 Constraints

| Constraint | Impact |
|------------|--------|
| Live AI platforms require active subscriptions | E2E tests cannot run in CI without real accounts |
| Chrome + Playwright required for integration tests | CI needs a Chrome installation or headless setup |
| Platform UIs change without notice | E2E tests may break from upstream UI changes (not our bug) |
| Cross-origin iframes (ChatGPT DR) | Cannot unit-test iframe extraction; requires live browser |
| Agent fallback requires `ANTHROPIC_API_KEY` | Fallback tests skipped if key not set |
| Rate limit state is machine-global | Test state must use a temp file path to avoid corrupting real state |
| XLSX tests require openpyxl | Must be installed in test environment |

---

## 2. Unit Tests

### 2.1 `skills/orchestrator/engine/prompt_echo.py`

| Test ID | Test Case | Input | Expected Output |
|---------|-----------|-------|-----------------|
| UT-PE-01 | Extracts ALL-CAPS phrases from structured prompt | Prompt with "SYSTEM ROLE & MINDSET", "ANALYSIS PROTOCOL" sections | List containing those phrases |
| UT-PE-02 | Limits extraction to `max_sigs` | Prompt with 10 ALL-CAPS phrases, `max_sigs=5` | List of 5 items |
| UT-PE-03 | Returns empty list for plain-text prompt | "Hello, what can you do?" | `[]` |
| UT-PE-04 | Falls back to long distinctive words if no ALL-CAPS found | Prompt with no ALL-CAPS but 15+ char words | List with those words |
| UT-PE-05 | `is_prompt_echo` returns True for echoed prompt | text = first 3000 chars of prompt, sigs from same prompt | `True` |
| UT-PE-06 | `is_prompt_echo` returns False for AI response | text = "# Executive Summary\nThis platform provides..." | `False` |
| UT-PE-07 | `is_prompt_echo` ignores text beyond `sample_size` | sig at position 3500, sample_size=3000 | `False` |
| UT-PE-08 | Backward compatibility with solution-research prompt sigs | Current prompt-template.md content | Sigs include "SYSTEM ROLE & MINDSET", "CONSTRAINTS (NON-NEGOTIABLE)" |

### 2.2 `skills/orchestrator/engine/rate_limiter.py`

All tests must use a temporary state file path to avoid touching the real `~/.chrome-playwright/rate-limit-state.json`.

| Test ID | Test Case | Input | Expected Output |
|---------|-----------|-------|-----------------|
| UT-RL-01 | Fresh state allows all platforms | New `RateLimiter`, no state file | `preflight_check(any_platform, "REGULAR").allowed == True` |
| UT-RL-02 | Budget exhausted blocks platform | Record `max_requests` usages within window | `preflight_check().allowed == False`, reason contains "budget" |
| UT-RL-03 | Cooldown blocks immediately after request | Record 1 usage; check again instantly | `allowed == False`, reason contains "Cooldown" |
| UT-RL-04 | Cooldown clears after `cooldown_seconds` | Record usage; manually advance time past cooldown | `allowed == True` |
| UT-RL-05 | Exponential backoff after rate_limited event | Record `status=rate_limited`; preflight | `wait_seconds >= cooldown * 2` |
| UT-RL-06 | Backoff caps at 16× | Record 5+ rate_limited events | `wait_seconds <= cooldown * 16` |
| UT-RL-07 | State persists to JSON and reloads | Save state; create new `RateLimiter` from same file; load_state | Usage records present after reload |
| UT-RL-08 | State write is atomic (tmp + rename) | Inspect write: temp file used then renamed | No partial writes visible |
| UT-RL-09 | Expired records pruned on load | Add records older than `window_seconds`; reload | Expired records not counted |
| UT-RL-10 | Daily cap enforced | `daily_cap=3`; record 3 usages today | 4th preflight blocked with daily cap reason |
| UT-RL-11 | Staggered order: most budget first | 3 platforms: 1 used, 1 at 50%, 1 fresh | Fresh platform at delay=0, used platform last |
| UT-RL-12 | Rate-limited platform penalized in stagger order | 1 platform recently rate-limited | Rate-limited platform sorted last |
| UT-RL-13 | Budget summary returns correct remaining count | Record 2 usages on claude_ai | `summary["claude_ai"]["remaining"] == total - 2` |
| UT-RL-14 | `free` and `paid` tier configs differ | Compare `RateLimiter("free")` vs `RateLimiter("paid")` budgets | Paid has higher `max_requests` |

### 2.3 `skills/orchestrator/engine/collate_responses.py`

| Test ID | Test Case | Input | Expected Output |
|---------|-----------|-------|-----------------|
| UT-CR-01 | Collates all 7 response files in canonical order | Dir with 7 `*-raw-response.md` files | Archive header lists Claude.ai first, Gemini last |
| UT-CR-02 | Uses task name in archive filename | `task_name="My Task"` | File created as `My Task - Raw AI Responses.md` |
| UT-CR-03 | Includes metadata from status.json | status.json with chars, duration_s, mode_used per platform | Archive section headers contain metadata |
| UT-CR-04 | Handles missing status.json gracefully | Dir with response files but no status.json | Archive created without metadata (no error) |
| UT-CR-05 | Partial results (some platforms missing) | Only 3 of 7 response files present | Archive contains 3 sections; header shows "3/7" |
| UT-CR-06 | Returns None and prints message if no files | Empty directory | Returns `None`, no file created |
| UT-CR-07 | Re-running collation overwrites existing archive | Existing archive present | Archive replaced cleanly |

### 2.4 `skills/orchestrator/engine/config.py`

| Test ID | Test Case | Expected |
|---------|-----------|----------|
| UT-CF-01 | All 7 platforms in `PLATFORM_URLS` | 7 entries |
| UT-CF-02 | All 7 platforms in `TIMEOUTS` with `regular` and `deep` | 7 entries × 2 keys |
| UT-CF-03 | All 7 platforms in `RATE_LIMITS` with `free` and `paid` tiers | 7 × 2 × 2 entries |
| UT-CF-04 | `RATE_LIMITS` each entry is `RateLimitConfig` with positive `max_requests` | All pass |
| UT-CF-05 | `STAGGER_DELAY` is positive integer | `> 0` |
| UT-CF-06 | `DEFAULT_TIER` is "free" | `== "free"` |
| UT-CF-07 | `POLL_INTERVAL` is positive | `> 0` |

### 2.5 `skills/orchestrator/engine/orchestrator.py` — Argument Parsing

| Test ID | Test Case | Input | Expected |
|---------|-----------|-------|----------|
| UT-OR-01 | `--prompt` accepted | `--prompt "Hello"` | `args.prompt == "Hello"` |
| UT-OR-02 | `--prompt-file` accepted | `--prompt-file /tmp/p.md` | `args.prompt_file == "/tmp/p.md"` |
| UT-OR-03 | `--prompt` and `--prompt-file` mutually exclusive | Both provided | argparse error |
| UT-OR-04 | `--mode` defaults to REGULAR | No `--mode` flag | `args.mode == "REGULAR"` |
| UT-OR-05 | `--platforms` default is "all" | No `--platforms` flag | `args.platforms == "all"` |
| UT-OR-06 | `--tier` defaults to "free" | No `--tier` flag | `args.tier == "free"` |
| UT-OR-07 | `--task-name` sets output to reports subdir | `--task-name "My Run"` | `_resolve_output_dir(args)` ends with `"reports/My Run"` |
| UT-OR-08 | `--task-name` overrides `--output-dir` | Both provided | `_resolve_output_dir` uses task-name path |
| UT-OR-09 | `--budget` flag parsed | `--budget` | `args.budget == True` |
| UT-OR-10 | `--skip-rate-check` flag parsed | `--skip-rate-check` | `args.skip_rate_check == True` |
| UT-OR-11 | `--stagger-delay` accepts integer | `--stagger-delay 10` | `args.stagger_delay == 10` |

### 2.6 `skills/comparator/matrix_ops.py`

| Test ID | Test Case | Expected |
|---------|-----------|----------|
| UT-MX-01 | `info` returns correct row/column counts | JSON with `platform_count`, `feature_count` matching test matrix |
| UT-MX-02 | `extract-features` returns all matrix rows | JSON list length == feature count from UT-MX-01 |
| UT-MX-03 | `add-platform` with all-true features ticks all rows | All features in output JSON show `ticked: true` |
| UT-MX-04 | `add-platform` with orphan features reports them | Feature not in matrix → `orphans` list in output |
| UT-MX-05 | `scores` returns sorted descending order | Platform with more ticks scores higher |
| UT-MX-06 | `reorder-columns` sorts by score descending | Highest-scoring platform in leftmost column |
| UT-MX-07 | `add-platform` is idempotent | Running twice produces identical XLSX | Second run output == first run output |
| UT-MX-08 | Auto-detect layout (with title row) | Matrix with merged title row → `_Layout.has_title == True` |
| UT-MX-09 | Auto-detect layout (without title row) | Matrix where B1=="Priority" → `_Layout.has_title == False` |

### 2.7 v4.0 Additions: Routing, Landscape, Preview, Domain, Self-Improvement Tests

#### Orchestrator Routing Tests

| Test ID | Test Case | Input | Expected Output |
|---------|-----------|-------|-----------------|
| TC-ROUTE-1 | Orchestrator routes landscape intent to landscape-researcher | "market landscape analysis on DevOps platforms" | Dispatches to landscape-researcher skill |
| TC-ROUTE-2 | Orchestrator routes product research to solution-researcher | "research Humanitec.com" | Dispatches to solution-researcher skill |
| TC-ROUTE-3 | Orchestrator routes matrix update to comparator | "add Harness to comparison matrix" | Dispatches to comparator skill |
| TC-ROUTE-4 | Orchestrator routes generic question to direct multi-AI | "what are pros and cons of Rust vs Go?" | Runs engine directly → consolidator (no specialized skill) |

#### Landscape Report Launcher Tests

| Test ID | Test Case | Input | Expected Output |
|---------|-----------|-------|-----------------|
| TC-LAUNCH-1 | `launch_report.py --no-browser` prints URL-encoded path | `--report-dir reports/test --report-file "Test Report.md" --no-browser` | Stdout contains correctly URL-encoded `preview.html?report=` path; browser not opened |
| TC-LAUNCH-2 | `launch_report.py` skips server if port in use | Port 8000 already bound by another process | Script prints message about port in use; does not crash; still outputs URL |

#### Preview HTML Tests

| Test ID | Test Case | Input | Expected Output |
|---------|-----------|-------|-----------------|
| TC-PREVIEW-1 | `preview.html?report=<path>` loads specified report | URL with `?report=reports/test/Test.md` query param | Report content loaded; charts rendered |
| TC-PREVIEW-2 | `preview.html` with no param loads default report | URL with no query parameter | Default report loaded successfully |

#### Domain Enrichment Tests

| Test ID | Test Case | Input | Expected Output |
|---------|-----------|-------|-----------------|
| TC-DOMAIN-1 | landscape-researcher proposes domain additions after run | Completed landscape research run with domain specified | Proposed additions are append-only; contain timestamps; include general domain knowledge |
| TC-DOMAIN-2 | solution-researcher domain additions include cross-skill knowledge | Completed solution research run with domain specified | Proposed additions include cross-skill general knowledge (not just product-specific findings) |

#### Self-Improvement Tests

| Test ID | Test Case | Input | Expected Output |
|---------|-----------|-------|-----------------|
| TC-SELF-1 | Each SKILL.md gains Run Log entry after successful run | Successful run of any of the 5 skills | SKILL.md contains new timestamped entry in Run Log section; entry count increased by 1 |

### 2.8 v4.1 Setup Bootstrap, Plugin Hook, and Venv Check Tests

| Test ID | Test Case | Setup | Expected |
|---------|-----------|-------|----------|
| TC-SETUP-1 | `setup.sh` creates `.venv` and installs playwright + openpyxl | Run `bash setup.sh` in a clean directory | `.venv/bin/python -c "import playwright, openpyxl"` exits 0 |
| TC-SETUP-2 | `setup.sh --with-fallback` also installs browser-use | Run `bash setup.sh --with-fallback` | `.venv/bin/python -c "import browser_use"` exits 0 |
| TC-SETUP-3 | `setup.sh` is idempotent | Run `bash setup.sh` twice in succession | Second run exits 0 with no error |
| TC-VENV-1 | Orchestrator Phase 1 detects missing `.venv` and shows setup message | Delete `skills/orchestrator/engine/.venv`; inspect SKILL.md Phase 1 instruction | Phase 1 check message contains "bash setup.sh" |
| TC-HOOK-1 | Plugin `SessionStart` hook invokes `install.sh → setup.sh` on first session | Fresh plugin install via `claude plugin install` | `skills/orchestrator/engine/.venv` exists after first Claude Code session |
| TC-HOOK-2 | `.installed` sentinel prevents re-run of setup on subsequent sessions | `.installed` file already present | `setup.sh` is not called again on second and subsequent sessions |

---

## 3. Integration Tests

Integration tests verify engine CLI behaviour end-to-end without requiring live AI platform responses.

### 3.1 Prerequisites

- Python 3.11+ with `playwright`, `openpyxl`, `asyncio`
- Chrome installed (for CDP connection tests)
- No AI platform subscriptions required (tests stop before or mock prompt submission)

### 3.2 Engine CLI Tests

| Test ID | Test Case | Setup | Verification |
|---------|-----------|-------|-------------|
| IT-01 | `--task-name` creates subdirectory | `--prompt "Test" --task-name "My Run"` | `reports/My Run/` exists |
| IT-02 | `status.json` written to task subdirectory | Same as IT-01 | `reports/My Run/status.json` exists |
| IT-03 | Archive auto-generated after run | `--task-name "My Run"` | `reports/My Run/My Run - Raw AI Responses.md` exists |
| IT-04 | `--budget` prints table and exits 0 | `--prompt "x" --budget` | Exit code 0; stdout contains platform names and budget numbers |
| IT-05 | `--skip-rate-check` bypasses pre-flight | Run with exhausted budget + flag | Platform not skipped |
| IT-06 | Rate limiter state file created after run | Fresh machine, run one platform | `~/.chrome-playwright/rate-limit-state.json` exists with 1 usage record |
| IT-07 | Pre-flight skips over-budget platform | Exhaust budget; run again | Platform shows `rate_limited` without launching |
| IT-08 | `_resolve_output_dir` with no task-name | No `--task-name`, default `--output-dir` | Output written to `reports/` root |
| IT-09 | `collate_responses.py` standalone CLI | `python3 skills/orchestrator/engine/collate_responses.py reports/existing-dir/ "Label"` | Archive created in that dir |
| IT-10 | Engine exit code 0 on partial success | At least 1 platform succeeds | `$? == 0` |
| IT-11 | Engine exit code 1 on all-fail | All platforms fail | `$? == 1` |

### 3.3 Skill Contract Tests

| Test ID | Test Case | Verification |
|---------|-----------|-------------|
| IT-SC-01 | Archive file in correct subdirectory | After engine run with `--task-name`, archive in `reports/{task-name}/` |
| IT-SC-02 | Archive contains all successful platform responses | Archive sections match status=complete platforms |
| IT-SC-03 | Consolidator reads archive and produces report | Given sample archive, consolidator produces `.md` output |
| IT-SC-04 | Solution researcher full chain | Prompt build → orchestrate → consolidate → 2 deliverables |
| IT-SC-05 | Comparator reads CIR, produces features.json | Given sample CIR + matrix, features.json has all matrix features |
| IT-SC-06 | `matrix_ops.py add-platform` updates XLSX | features.json + matrix → updated XLSX with new column |
| IT-SC-07 | Domain knowledge enrichment proposed | After comparator run, proposed additions contain timestamped entries |

### 3.4 Orchestrator Routing Tests

| Test ID | Test Case | Input | Verification |
|---------|-----------|-------|-------------|
| IT-RT-01 | Landscape intent routes to landscape-researcher | User prompt "Research the IDP landscape" | `skills/landscape-researcher/SKILL.md` invoked; orchestrator + consolidator called within that flow |
| IT-RT-02 | Product URL routes to solution-researcher | User prompt "Research Northflank.com" | `skills/solution-researcher/SKILL.md` invoked; prompt-template used |
| IT-RT-03 | Matrix operation routes to comparator | User prompt "Add Northflank to the matrix" | `skills/comparator/SKILL.md` invoked; `matrix_ops.py add-platform` called |
| IT-RT-04 | General prompt routes directly to orchestrator | User prompt "What are best practices for CI/CD?" | `skills/orchestrator/SKILL.md` invoked directly; no specialized skill |

### 3.5 `skills/landscape-researcher/launch_report.py` Tests

| Test ID | Test Case | Input | Verification |
|---------|-----------|-------|-------------|
| IT-LR-01 | No-browser flag skips browser launch | `python3 launch_report.py --no-browser` | Report generated; no browser process spawned; exit code 0 |
| IT-LR-02 | Port-in-use handling | Start a listener on default port; run `launch_report.py` | Script detects port conflict and either selects next available port or exits with clear error message |
| IT-LR-03 | Default launch opens report in browser | `python3 launch_report.py` (with available port) | HTTP server starts; browser opened to `localhost:{port}`; preview.html served |

### 3.6 `reports/preview.html` Tests

| Test ID | Test Case | Input | Verification |
|---------|-----------|-------|-------------|
| IT-PV-01 | Query-param loads correct report | Open `preview.html?report=My+Report` | Page renders content from `reports/My Report/` directory |
| IT-PV-02 | Missing query-param shows index or error | Open `preview.html` (no params) | Page shows a list of available reports or a clear "no report selected" message |
| IT-PV-03 | Non-existent report path handled gracefully | Open `preview.html?report=nonexistent` | Page shows error message; no JavaScript crash |

---

## 4. End-to-End Tests

E2E tests require a real Chrome with active AI platform logins.

### 4.1 Test Environment

- macOS/Linux workstation with Chrome and active sessions on all 7 platforms
- Python venv with all dependencies (`playwright`, `openpyxl`, `browser-use`)
- `ANTHROPIC_API_KEY` set (for Agent fallback tests)

### 4.2 Test Matrix

| Test ID | Scenario | Mode | Platforms | Pass Criteria |
|---------|----------|------|-----------|---------------|
| E2E-01 | Simple prompt, single platform | REGULAR | claude_ai | status=complete, >500 chars |
| E2E-02 | Simple prompt, all platforms with task-name | REGULAR | all | ≥5/7 succeed; archive in `reports/{task-name}/` |
| E2E-03 | Rate limit pre-flight skip | REGULAR | All (with exhausted platform) | Over-budget platform shows rate_limited without loading |
| E2E-04 | Prompt-echo detection | REGULAR | chatgpt | Extracted text does NOT contain prompt signatures |
| E2E-05 | Solution research, all platforms | DEEP | all | ≥5/7 succeed; CIR produced |
| E2E-06 | Comparator: add platform to matrix | — | — | XLSX updated with new column; scores table populated |
| E2E-07 | ChatGPT DR panel extraction | DEEP | chatgpt | Extracted via frame, >1000 chars |
| E2E-08 | Gemini Deep Research | DEEP | gemini | "Start research" clicked; response >5000 chars |
| E2E-09 | Agent fallback triggered | REGULAR | Any | Fallback log entry; response still extracted |
| E2E-10 | Condensed prompt on constrained platform | REGULAR | grok | Condensed prompt injected; response extracted |
| E2E-11 | Rate limit detection mid-run | REGULAR | Any rate-limited | check_rate_limit() detects banner; platform exits early with rate_limited |
| E2E-12 | Budget persists across sessions | REGULAR | claude_ai | After 1st run, 2nd run budget shows reduced count |

### 4.3 Platform-Specific Regression Tests

| Platform | Key Verification |
|----------|-----------------|
| Claude.ai | Panel selector extraction; generic `# ` marker fallback; rate limit detection ("Usage limit reached", "too many messages") |
| ChatGPT (REGULAR) | Article selector; prompt-echo filtered via `self.prompt_sigs`; rate limit detection ("usage cap") |
| ChatGPT (DEEP) | Three-layer DR panel: frame.evaluate → frame_locator → coordinates |
| Copilot | "Copilot said" marker primary; generic `# ` secondary; rate limit detection ("conversation limit") |
| Perplexity | Answer card extraction; rate limit detection ("Pro search limit", "out of Pro searches") |
| Grok | Physical typing injection; rate limit detection ("Message limit reached") |
| DeepSeek | Markdown-body selector primary; generic `# ` secondary; rate limit detection ("server is busy") |
| Gemini | Response container selector; `_seen_stop` guard; Flash fallback detection ("switched to Flash") |

---

## 5. Regression Test Suite

### 5.1 Regression Checklist

Run after any engine change:

| Check | Command |
|-------|---------|
| All engine Python files compile | `python3 -m py_compile skills/orchestrator/engine/orchestrator.py skills/orchestrator/engine/config.py skills/orchestrator/engine/utils.py skills/orchestrator/engine/prompt_echo.py skills/orchestrator/engine/agent_fallback.py skills/orchestrator/engine/rate_limiter.py skills/orchestrator/engine/collate_responses.py` |
| All comparator Python files compile | `python3 -m py_compile skills/comparator/matrix_ops.py skills/comparator/matrix_builder.py` |
| All platform files compile | `for f in skills/orchestrator/engine/platforms/*.py; do python3 -m py_compile "$f"; done` |
| Landscape launcher compiles | `python3 -m py_compile skills/landscape-researcher/launch_report.py` |
| No domain-specific strings in engine/ | `! grep -ri "solution.research" skills/orchestrator/engine/` |
| No DevOps strings in engine/ | `! grep -ri "devops" skills/orchestrator/engine/` |
| No hardcoded `_PROMPT_SIGS` | `! grep -r "_PROMPT_SIGS" skills/orchestrator/engine/platforms/` |
| All 7 concrete platforms have `check_rate_limit()` | `grep -l "check_rate_limit" skills/orchestrator/engine/platforms/*.py \| grep -v base.py \| wc -l` returns 7 |
| CLI accepts `--task-name` | `python3 skills/orchestrator/engine/orchestrator.py --help \| grep -q "task-name"` |
| CLI accepts `--budget` | `python3 skills/orchestrator/engine/orchestrator.py --help \| grep -q "budget"` |
| CLI accepts `--tier` | `python3 skills/orchestrator/engine/orchestrator.py --help \| grep -q "tier"` |
| CLI rejects old `--url` flag | `python3 skills/orchestrator/engine/orchestrator.py --url x 2>&1 \| grep -q "error"` |
| Budget command runs and exits | `python3 skills/orchestrator/engine/orchestrator.py --prompt "x" --budget` exits 0 with table output |
| Collate script runs standalone | `python3 skills/orchestrator/engine/collate_responses.py reports/harness-oss/ "Test"` exits 0 |

---

## 6. Test Data and Fixtures

### 6.1 Fixture Files

| File | Purpose |
|------|---------|
| `tests/fixtures/sample-research-prompt.md` | Real solution-research prompt for echo-detection regression |
| `tests/fixtures/simple-prompt.txt` | "Hello, what can you do?" — minimal generic prompt |
| `tests/fixtures/sample-ai-response.md` | Real AI response for extraction testing |
| `tests/fixtures/sample-status.json` | Example status.json for collation and skill contract tests |
| `tests/fixtures/sample-raw-archive.md` | Example raw archive for consolidator input testing |
| `tests/fixtures/sample-matrix.xlsx` | Minimal XLSX matrix with 3 platforms and 10 features for matrix_ops testing |
| `tests/fixtures/sample-features.json` | Example features.json with 10 true/false entries |
| `tests/fixtures/sample-cir.md` | Example CIR (Variant A) for comparator testing |

### 6.2 Mock Data

| Mock | Use |
|------|-----|
| Mock Chrome (stub CDP) | Integration tests verifying CLI parsing without real Chrome |
| Mock platform page (HTML snapshot) | Unit tests for extraction logic using stored HTML |
| Temp rate-limit state file | Unit tests for rate_limiter.py — isolated from real machine state |

---

## 7. Test Execution Plan

### 7.1 Development Phase (per change)

| When | What | How |
|------|------|-----|
| After any Python file change | Compile check | `python3 -m py_compile <file>` |
| After `prompt_echo.py` change | Unit tests UT-PE-01–08 | `pytest tests/test_prompt_echo.py` |
| After `rate_limiter.py` change | Unit tests UT-RL-01–14 | `pytest tests/test_rate_limiter.py` |
| After `collate_responses.py` change | Unit tests UT-CR-01–07 | `pytest tests/test_collate_responses.py` |
| After `orchestrator.py` change | Unit tests UT-OR-01–11 | `pytest tests/test_orchestrator_args.py` |
| After `config.py` change | Unit tests UT-CF-01–07 | `pytest tests/test_config.py` |
| After `matrix_ops.py` change | Unit tests UT-MX-01–09 | `pytest tests/test_matrix_ops.py` |
| After `launch_report.py` change | Unit tests TC-LAUNCH-1–2 | `pytest tests/test_launch_report.py` |
| After all engine changes | Full regression checklist (Section 5.1) | `make check` |

### 7.2 Validation Phase (after feature completion)

| When | What | How |
|------|------|-----|
| After rate limiter implementation | E2E-03: pre-flight skip | Manual with exhausted budget |
| After collation implementation | E2E-02: all-platforms with task-name | `--task-name "Validation"` run |
| After comparator implementation | E2E-06: add-platform | Run comparator skill on sample CIR |
| After any platform file change | Platform regression (Section 4.3) | Manual E2E for affected platform |

### 7.3 Acceptance Criteria

The system is considered production-ready when:

1. All unit tests pass (pytest) — 0 failures
2. All compile checks pass — 0 errors
3. Regression checklist is clean
4. At least one successful E2E run with all 7 platforms in REGULAR mode, archive auto-generated in named subdirectory
5. At least one successful E2E solution research run in DEEP mode with CIR + updated matrix
6. Rate limit pre-flight correctly skips an over-budget platform in a real run
7. Budget command shows correct remaining counts before and after a run
8. Solution researcher works without domain file (UC-03)
9. Domain knowledge file enriched after research + comparison run
