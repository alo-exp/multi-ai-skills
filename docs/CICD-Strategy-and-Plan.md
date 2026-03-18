# CI/CD Strategy and Plan

**Project:** Multi-AI Orchestrator Platform
**Version:** 4.1
**Date:** 2026-03-18

| Version | Date | Summary |
|---------|------|---------|
| 2.0 | 2026-03-13 | Initial CI/CD strategy for generic restructuring |
| 3.0 | 2026-03-13 | Added matrix engine files to compile checks and test suite |
| 3.1 | 2026-03-14 | Added rate_limiter.py compile check, rate limit unit tests, regression checks |
| 3.2 | 2026-03-14 | Added collate_responses.py compile check, collation tests, budget smoke test |
| 4.0 | 2026-03-16 | Updated engine paths to skills/orchestrator/engine/; added landscape-researcher and comparator script lint targets; added landscape smoke test |
| 4.1 | 2026-03-18 | Added setup.sh smoke test; updated Python requirement to 3.11+; updated install step to use engine/requirements.txt |

---

## 1. Overview

### 1.1 Context

This project is a desktop-local automation tool, not a web service. It runs on the user's machine with their Chrome profile and AI platform logins. This fundamentally shapes the CI/CD strategy:

- **No deployment pipeline** — the tool runs locally, not on a server
- **No container builds** — Chrome must use the user's real profile with active sessions
- **Limited CI scope** — E2E tests require live AI platforms and cannot run in standard CI
- **Primary value of CI** — catching code errors, import failures, and regressions early

### 1.2 Goals

1. Catch Python syntax errors and import failures on every change
2. Run unit tests automatically on every change
3. Validate that the engine CLI accepts the correct interface
4. Ensure no domain-specific strings leak into the generic engine
5. Verify rate limit budgets are configured for all 7 platforms
6. Provide a clear versioning and release process

---

## 2. Build Pipeline

### 2.1 Pipeline Stages

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  1. Install   │───▶│  2. Lint &    │───▶│  3. Unit      │───▶│  4. Regression│
│  Dependencies │    │  Compile     │    │  Tests       │    │  Checks      │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

### 2.2 Stage 1: Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r skills/orchestrator/engine/requirements.txt
pip install pytest  # Test runner
```

> **Note:** `setup.sh` is the user-facing bootstrap (creates `skills/orchestrator/engine/.venv`, installs deps, runs `playwright install chromium`). CI installs dependencies directly via pip as shown above — no Chromium browser installation needed for unit tests and regression checks.

**Duration:** ~30s
**Gate:** Exit code 0

### 2.3 Stage 2: Lint and Compile

```bash
# Core engine files
python3 -m py_compile skills/orchestrator/engine/orchestrator.py
python3 -m py_compile skills/orchestrator/engine/config.py
python3 -m py_compile skills/orchestrator/engine/utils.py
python3 -m py_compile skills/orchestrator/engine/prompt_echo.py
python3 -m py_compile skills/orchestrator/engine/agent_fallback.py
python3 -m py_compile skills/orchestrator/engine/rate_limiter.py
python3 -m py_compile skills/orchestrator/engine/collate_responses.py

# Comparator skill files
python3 -m py_compile skills/comparator/matrix_ops.py
python3 -m py_compile skills/comparator/matrix_builder.py

# Landscape-researcher skill files
python3 -m py_compile skills/landscape-researcher/launch_report.py

# All platform files
for f in skills/orchestrator/engine/platforms/*.py; do python3 -m py_compile "$f"; done

# Optional: ruff or flake8 lint
# ruff check skills/orchestrator/engine/ --select E,F,W

# Bash script syntax checks
bash -n setup.sh
bash -n install.sh
```

**Duration:** ~5s
**Gate:** All 11 core files (7 engine + 2 comparator + 1 landscape + 1 launcher) + all platform files compile without errors; bash scripts pass syntax check

### 2.4 Stage 3: Unit Tests

```bash
cd skills/orchestrator/engine && python3 -m pytest ../../../tests/ -v --tb=short
```

Test modules (v4.2):
- `tests/test_prompt_echo.py` — 8 tests (UT-PE-01 to UT-PE-08)
- `tests/test_rate_limiter.py` — 14 tests (UT-RL-01 to UT-RL-14)
- `tests/test_collate_responses.py` — 7 tests (UT-CR-01 to UT-CR-07)
- `tests/test_config.py` — 7 tests (UT-CF-01 to UT-CF-07)
- `tests/test_orchestrator_args.py` — 11 tests (UT-OR-01 to UT-OR-11)
- `tests/test_matrix_ops.py` — 9 tests (UT-MX-01 to UT-MX-09)
- `tests/test_matrix_builder.py` — 9 tests (UT-MB-01 to UT-MB-09)
- `tests/test_utils.py` — 9 tests (UT-UT-01 to UT-UT-09)
- `tests/test_launch_report.py` — 2 tests (TC-LAUNCH-1 to TC-LAUNCH-2)
- `tests/test_setup_bootstrap.py` — 17 tests (TC-SETUP-1/3, TC-VENV-1, TC-HOOK-1/2, TC-LAUNCH-1/2)

**Total unit tests:** 93
**Duration:** ~10s
**Gate:** All tests pass

### 2.5 Stage 4: Regression Checks

```bash
# No domain-specific strings in engine/ (exclude .venv and __pycache__)
! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "solution.research" skills/orchestrator/engine/
! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "devops" skills/orchestrator/engine/
! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "capability.analysis" skills/orchestrator/engine/
! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "executive.summary" skills/orchestrator/engine/

# No hardcoded _PROMPT_SIGS in platform files
! grep -r "_PROMPT_SIGS" skills/orchestrator/engine/platforms/*.py

# All 7 platforms have check_rate_limit
test "$(grep -l "check_rate_limit" skills/orchestrator/engine/platforms/*.py | grep -v base.py | wc -l | tr -d ' ')" = "7"

# All 7 platforms in RATE_LIMITS config
python3 -c "
import sys; sys.path.insert(0,'skills/orchestrator/engine')
from config import RATE_LIMITS
assert len(RATE_LIMITS) == 7, f'Expected 7 platforms, got {len(RATE_LIMITS)}'
for p, tiers in RATE_LIMITS.items():
    assert 'free' in tiers and 'paid' in tiers, f'{p} missing tier'
    for t, modes in tiers.items():
        assert 'REGULAR' in modes and 'DEEP' in modes, f'{p}/{t} missing mode'
print('RATE_LIMITS OK: 7 platforms × 2 tiers × 2 modes')
"

# Budget command works and exits 0
python3 skills/orchestrator/engine/orchestrator.py --prompt "x" --budget 2>&1 | grep -q "Rate Limit Budget"

# CLI accepts new flags
python3 skills/orchestrator/engine/orchestrator.py --help | grep -q "task-name"
python3 skills/orchestrator/engine/orchestrator.py --help | grep -q "tier"
python3 skills/orchestrator/engine/orchestrator.py --help | grep -q "budget"

# Old CLI flags rejected
python3 skills/orchestrator/engine/orchestrator.py --url x 2>&1 | grep -q "error"

# Collation script runs standalone
python3 skills/orchestrator/engine/collate_responses.py reports/harness-oss/ "Regression Test"

# Landscape-researcher launch script compiles
python3 -m py_compile skills/landscape-researcher/launch_report.py

# Landscape workflow smoke test (v4.0)
python3 skills/landscape-researcher/launch_report.py --report-dir test --report-file "Test.md" --no-browser

# Setup bootstrap smoke test (v4.1)
bash -n setup.sh    # syntax check
bash -n install.sh  # syntax check
```

**Duration:** ~10s
**Gate:** All checks pass

---

## 3. CI Environment

### 3.1 Recommended CI Platform

**GitHub Actions** (if the repo is on GitHub) or any CI that supports:
- Python 3.11+
- pip install
- No Chrome required (unit tests and most regression checks only)

### 3.2 GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'  # 3.11+ required; 3.12 used in CI

      - name: Install dependencies
        run: |
          pip install -r skills/orchestrator/engine/requirements.txt
          pip install pytest

      - name: Compile check — core engine files
        run: |
          python -m py_compile skills/orchestrator/engine/orchestrator.py
          python -m py_compile skills/orchestrator/engine/config.py
          python -m py_compile skills/orchestrator/engine/utils.py
          python -m py_compile skills/orchestrator/engine/prompt_echo.py
          python -m py_compile skills/orchestrator/engine/agent_fallback.py
          python -m py_compile skills/orchestrator/engine/rate_limiter.py
          python -m py_compile skills/orchestrator/engine/collate_responses.py
          python -m py_compile skills/comparator/matrix_ops.py
          python -m py_compile skills/comparator/matrix_builder.py
          python -m py_compile skills/landscape-researcher/launch_report.py

      - name: Compile check — platform files
        run: |
          for f in skills/orchestrator/engine/platforms/*.py; do python -m py_compile "$f"; done

      - name: Unit tests
        run: cd skills/orchestrator/engine && python -m pytest ../../../tests/ -v --tb=short

      - name: Regression checks
        run: |
          ! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "solution.research" skills/orchestrator/engine/
          ! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "devops" skills/orchestrator/engine/
          ! grep -r "_PROMPT_SIGS" skills/orchestrator/engine/platforms/*.py
          python -c "
          import sys; sys.path.insert(0,'skills/orchestrator/engine')
          from config import RATE_LIMITS
          assert len(RATE_LIMITS) == 7
          print('RATE_LIMITS: OK')
          "
          python skills/orchestrator/engine/orchestrator.py --prompt "x" --budget 2>&1 | grep -q "Rate Limit Budget"
          python skills/orchestrator/engine/orchestrator.py --help | grep -q "task-name"

      - name: Landscape smoke test (v4.0)
        run: |
          python skills/landscape-researcher/launch_report.py --report-dir test --report-file "Test.md" --no-browser

      - name: Setup bootstrap syntax check (v4.1)
        run: |
          bash -n setup.sh
          bash -n install.sh
```

### 3.3 What CI Cannot Test

| Aspect | Reason | Mitigation |
|--------|--------|------------|
| Platform extraction (7 AIs) | Requires active logins | Manual E2E tests |
| Chrome CDP lifecycle | Requires Chrome + display | Manual integration tests |
| Agent fallback (browser-use) | Requires ANTHROPIC_API_KEY or GOOGLE_API_KEY + Chrome | Manual with key set |
| Skill invocation (SKILL.md) | Requires Claude Code host AI | Manual via Claude Code |
| Deep Research mode | Requires platform subscriptions | Manual E2E |
| Rate limit state file creation | Requires actual orchestration run | Manual IT-06 |
| XLSX visual output | Requires Excel/Numbers | Manual inspection |

---

## 4. Local Development Workflow

### 4.1 Pre-Commit Checks

Developers should run before committing:

```bash
# Quick check (~15s)
make check

# Full check including E2E smoke test (~2 min)
make check e2e-smoke
```

### 4.2 Makefile

```makefile
.PHONY: check test compile regression e2e e2e-smoke budget-check landscape-smoke

compile:
	@echo "Compile checking engine and skill scripts..."
	@python3 -m py_compile skills/orchestrator/engine/orchestrator.py
	@python3 -m py_compile skills/orchestrator/engine/config.py
	@python3 -m py_compile skills/orchestrator/engine/utils.py
	@python3 -m py_compile skills/orchestrator/engine/prompt_echo.py
	@python3 -m py_compile skills/orchestrator/engine/agent_fallback.py
	@python3 -m py_compile skills/orchestrator/engine/rate_limiter.py
	@python3 -m py_compile skills/orchestrator/engine/collate_responses.py
	@python3 -m py_compile skills/comparator/matrix_ops.py
	@python3 -m py_compile skills/comparator/matrix_builder.py
	@python3 -m py_compile skills/landscape-researcher/launch_report.py
	@for f in skills/orchestrator/engine/platforms/*.py; do python3 -m py_compile "$$f"; done
	@echo "All files compile OK"

test:
	cd skills/orchestrator/engine && python3 -m pytest ../../../tests/ -v --tb=short

regression:
	@echo "Checking for domain-specific strings in engine/..."
	@! grep -ri "solution.research" skills/orchestrator/engine/ && echo "OK: no solution.research"
	@! grep -ri "devops" skills/orchestrator/engine/ && echo "OK: no devops"
	@! grep -r "_PROMPT_SIGS" skills/orchestrator/engine/platforms/ && echo "OK: no _PROMPT_SIGS"
	@python3 -c "import sys; sys.path.insert(0,'skills/orchestrator/engine'); from config import RATE_LIMITS; assert len(RATE_LIMITS)==7" && echo "OK: 7 platforms in RATE_LIMITS"
	@python3 skills/orchestrator/engine/orchestrator.py --prompt "x" --budget 2>&1 | grep -q "Rate Limit Budget" && echo "OK: budget command works"
	@python3 skills/orchestrator/engine/orchestrator.py --help | grep -q "task-name" && echo "OK: --task-name flag present"
	@echo "Regression checks passed"

check: compile test regression

budget-check:
	python3 skills/orchestrator/engine/orchestrator.py --prompt "x" --budget --tier free
	python3 skills/orchestrator/engine/orchestrator.py --prompt "x" --budget --tier paid

landscape-smoke:
	python3 skills/landscape-researcher/launch_report.py --report-dir test --report-file "Test.md" --no-browser

e2e-smoke:
	python3 skills/orchestrator/engine/orchestrator.py \
	    --prompt "Hello, what is 2+2?" \
	    --mode REGULAR \
	    --platforms claude_ai \
	    --task-name "CI-smoke-test"

e2e:
	python3 skills/orchestrator/engine/orchestrator.py \
	    --prompt "Hello, what can you do?" \
	    --mode REGULAR \
	    --task-name "E2E-full-test"
```

---

## 5. Versioning Strategy

### 5.1 Version Scheme

`{major}.{minor}` with date tracking in CHANGELOG.md

| Increment | When |
|-----------|------|
| Major (e.g., 2→3) | Architectural changes, new major subsystems (comparator, rate limiter) |
| Minor (e.g., 3.1→3.2) | New features within existing architecture (collation, --task-name) |

**Current version:** 4.0 (2026-03-16)

### 5.2 What Gets Versioned

| Component | Versioning | Where Tracked |
|-----------|-----------|---------------|
| Engine (Python) | In `CHANGELOG.md` | Semantic entries per version |
| Skills (SKILL.md) | In `CHANGELOG.md` | Per-skill entries |
| Domain knowledge (.md) | In the file itself | Enrichment entries appended with timestamps |
| Docs (SRS, Architecture, Test, CI/CD) | Version number + date in file header | Updated with each version |

### 5.3 CHANGELOG Format

```markdown
## Version X.Y — Short Title

**Date:** YYYY-MM-DD

### Problem / Context
[What was the issue or opportunity]

### Architecture change
| Aspect | Before | After |

### New files
| File | Purpose |

### Modified files
| File | Change |

### Key design decisions
1. Decision + rationale
```

---

## 6. Release Process

### 6.1 Steps

1. **Develop** — Make changes on a feature branch (or directly on main for small fixes)
2. **Pre-commit** — Run `make check` (compile + tests + regression); all must pass
3. **Budget check** — Run `make budget-check` to confirm rate limit configs are correct
4. **Update docs** — Update CHANGELOG.md, and any impacted SRS/Architecture/Test docs
5. **Tag** — `git tag v4.x` (or next version)
6. **E2E smoke** — Run `make e2e-smoke` on local machine with Chrome to confirm the engine starts

### 6.2 Release Artifacts

This is a local tool; there is no package to publish. The "release" is the state of the repository at a tagged commit. Users pull the latest code and run it.

---

## 7. Test Infrastructure Evolution

### 7.1 Phase 1 (Current — v4.0)

- Unit tests for prompt_echo, rate_limiter, collate_responses, config, orchestrator args, matrix_ops
- Compile checks for all engine files (skills/orchestrator/engine/) + comparator scripts (skills/comparator/) + landscape launcher (skills/landscape-researcher/launch_report.py) + 7 platform files
- Regression grep checks + config validation checks
- Budget smoke test (CLI output verification)
- Landscape workflow smoke test (`launch_report.py --no-browser`)
- Manual E2E validation

### 7.2 Phase 2 (Future — If Warranted)

- **HTML snapshot tests:** Save platform page HTML; test extraction logic against snapshots (no live browser)
- **Playwright dry-run mode:** Engine flag `--dry-run` that connects to Chrome and navigates but stops before injection
- **Matrix snapshot tests:** Save reference XLSX outputs; compare after `matrix_ops` operations to detect regressions
- **Scheduled E2E:** Weekly cron job on local machine running all 7 platforms and reporting drift
- **Rate limit state replay:** Test rate limiter with pre-seeded state files to verify budget and cooldown enforcement

### 7.3 Phase 3 (Future — If Multi-Developer)

- Pre-commit hooks via `pre-commit` framework (`make check` on every commit)
- Branch protection rules requiring CI pass before merge
- Automated CHANGELOG generation from commit messages
- Platform selector health checks: scheduled script navigating to each AI platform and verifying key selectors still exist
