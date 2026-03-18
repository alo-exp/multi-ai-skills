# CI/CD Strategy and Plan

**Project:** MultAI
**Version:** 0.2.260318B Alpha
**Date:** 2026-03-18

| Version | Date | Summary |
|---------|------|---------|
| 2.0 | 2026-03-13 | Initial CI/CD strategy for generic restructuring |
| 3.0 | 2026-03-13 | Added matrix engine files to compile checks and test suite |
| 3.1 | 2026-03-14 | Added rate_limiter.py compile check, rate limit unit tests, regression checks |
| 3.2 | 2026-03-14 | Added collate_responses.py compile check, collation tests, budget smoke test |
| 4.0 | 2026-03-16 | Updated engine paths to skills/orchestrator/engine/; added landscape-researcher and comparator targets |
| 4.1 | 2026-03-18 | Added setup.sh smoke test; updated Python requirement to 3.11+; updated install step |
| 4.2 | 2026-03-18 | Full rewrite — synced Makefile and GitHub Actions with actual code; added security scanning, coverage, matrix testing, plugin-specific CI, branching model, and Phase 2/3 acceptance criteria |
| 0.2.260318A | 2026-03-18 | Adopted hybrid semver+CalVer scheme (`Major.Minor.YYMMDDX Phase`). All previous internal versions (2.0–4.2) consolidated. Added version display to website. |

---

## 1. Overview

### 1.1 Context

MultAI is a desktop-local automation tool, not a web service. It runs on the user's machine with their Chrome profile and AI platform logins. It is distributed as a **Claude Code plugin**. This fundamentally shapes the CI/CD strategy:

- **No deployment pipeline** — the tool runs locally, not on a server
- **No container builds** — Chrome must use the user's real profile with active sessions
- **Limited CI scope** — E2E tests require live AI platforms and cannot run in standard CI
- **Plugin distribution** — users install via `claude plugin install`; the repo IS the release artifact
- **Primary value of CI** — catching code errors, import failures, regressions, and plugin manifest correctness early

### 1.2 Goals

1. Catch Python syntax errors and import failures on every change
2. Run 96 automated tests on every push and pull request
3. Validate the engine CLI accepts the correct interface
4. Ensure no domain-specific strings leak into the generic engine
5. Verify rate limit budgets are configured for all 7 platforms
6. Validate plugin manifest files (`hooks.json`, `settings.json`) are well-formed
7. Run security scans (dependency vulnerabilities, secret detection)
8. Enforce minimum test coverage threshold
9. Provide a clear versioning, branching, and release process
10. Test across Python 3.11, 3.12, and 3.13

---

## 2. Build Pipeline

### 2.1 Pipeline Stages

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  1. Install   │───▶│  2. Lint &    │───▶│  3. Unit      │───▶│  4. Regression│───▶│  5. Security  │
│  Dependencies │    │  Compile     │    │  Tests       │    │  Checks      │    │  & Quality   │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

### 2.2 Stage 1: Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r skills/orchestrator/engine/requirements.txt
pip install pytest pytest-cov  # Test runner + coverage
```

> **Note:** `setup.sh` is the user-facing bootstrap (creates `skills/orchestrator/engine/.venv`, installs deps, runs `playwright install chromium`). CI installs dependencies directly via pip as shown above — no Chromium browser installation needed for unit tests and regression checks.

**Duration:** ~30s
**Gate:** Exit code 0

### 2.3 Stage 2: Lint and Compile

```bash
# Core engine files (7 modules)
python3 -m py_compile skills/orchestrator/engine/orchestrator.py
python3 -m py_compile skills/orchestrator/engine/config.py
python3 -m py_compile skills/orchestrator/engine/utils.py
python3 -m py_compile skills/orchestrator/engine/prompt_echo.py
python3 -m py_compile skills/orchestrator/engine/agent_fallback.py
python3 -m py_compile skills/orchestrator/engine/rate_limiter.py
python3 -m py_compile skills/orchestrator/engine/collate_responses.py

# Comparator skill files (2 modules)
python3 -m py_compile skills/comparator/matrix_ops.py
python3 -m py_compile skills/comparator/matrix_builder.py

# Landscape-researcher launcher (1 module)
python3 -m py_compile skills/landscape-researcher/launch_report.py

# All platform files (7 platforms + base class + __init__)
for f in skills/orchestrator/engine/platforms/*.py; do python3 -m py_compile "$f"; done

# Bash script syntax checks
bash -n setup.sh
bash -n install.sh
```

**Duration:** ~5s
**Gate:** All 10 core files + all platform files compile without errors; both shell scripts pass syntax check

### 2.4 Stage 3: Unit Tests

```bash
# Uses the engine venv which has all dependencies pre-installed
skills/orchestrator/engine/.venv/bin/python -m pytest tests/ -v --tb=short
```

Test modules (v4.2):

| Test File | Tests | IDs |
|-----------|-------|-----|
| `tests/test_prompt_echo.py` | 8 | UT-PE-01 to UT-PE-08 |
| `tests/test_rate_limiter.py` | 14 | UT-RL-01 to UT-RL-14 |
| `tests/test_collate_responses.py` | 9 | UT-CR-01 to UT-CR-09 |
| `tests/test_config.py` | 8 | UT-CF-01 to UT-CF-08 |
| `tests/test_orchestrator_args.py` | 11 | UT-OR-01 to UT-OR-11 |
| `tests/test_matrix_ops.py` | 9 | UT-MX-01 to UT-MX-09 |
| `tests/test_matrix_builder.py` | 9 | UT-MB-01 to UT-MB-09 |
| `tests/test_utils.py` | 9 | UT-UT-01 to UT-UT-09 |
| `tests/test_launch_report.py` | 2 | TC-LAUNCH-1 to TC-LAUNCH-2 |
| `tests/test_setup_bootstrap.py` | 17 | TC-SETUP, TC-VENV, TC-HOOK, TC-LAUNCH |
| **Total** | **96** | |

**Duration:** ~4s
**Gate:** All 96 tests pass

### 2.5 Stage 4: Regression Checks

These are structural invariants that must hold across all changes:

```bash
# ── Domain isolation: no domain-specific strings in generic engine ──
# These patterns are checked by `make regression` — keep in sync with the Makefile
! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "solution.research" skills/orchestrator/engine/
! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "devops" skills/orchestrator/engine/

# Additional domain patterns (optional — add to Makefile if a violation appears)
# ! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "capability.analysis" skills/orchestrator/engine/
# ! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "executive.summary" skills/orchestrator/engine/

# ── No hardcoded prompt signatures in platform files ──
! grep -r "_PROMPT_SIGS" skills/orchestrator/engine/platforms/*.py

# ── All 7 platforms implement check_rate_limit ──
test "$(grep -l 'check_rate_limit' skills/orchestrator/engine/platforms/*.py | grep -v base.py | wc -l | tr -d ' ')" = "7"

# ── RATE_LIMITS config covers all 7 platforms × 2 tiers × 2 modes ──
python3 -c "
import sys; sys.path.insert(0,'skills/orchestrator/engine')
from config import RATE_LIMITS
assert len(RATE_LIMITS) == 7, f'Expected 7 platforms, got {len(RATE_LIMITS)}'
for p, tiers in RATE_LIMITS.items():
    assert 'free' in tiers and 'paid' in tiers, f'{p} missing tier'
    for t, modes in tiers.items():
        assert 'REGULAR' in modes and 'DEEP' in modes, f'{p}/{t} missing mode'
print('RATE_LIMITS OK: 7 platforms x 2 tiers x 2 modes')
"

# ── CLI interface integrity ──
python3 skills/orchestrator/engine/orchestrator.py --help | grep -q "task-name"
python3 skills/orchestrator/engine/orchestrator.py --help | grep -q "tier"
python3 skills/orchestrator/engine/orchestrator.py --help | grep -q "budget"
python3 skills/orchestrator/engine/orchestrator.py --url x 2>&1 | grep -q "error"   # Old flag rejected

# ── Budget command functional ──
python3 skills/orchestrator/engine/orchestrator.py --prompt "x" --budget 2>&1 | grep -q "Rate Limit Budget"

# ── Landscape smoke test ──
python3 skills/landscape-researcher/launch_report.py --report-dir test --report-file "Test.md" --no-browser
```

**Duration:** ~10s
**Gate:** All checks pass

### 2.6 Stage 5: Security and Quality

```bash
# ── Dependency vulnerability scan ──
pip install pip-audit
pip-audit -r skills/orchestrator/engine/requirements.txt

# ── Secret detection (no .env, API keys, or tokens committed) ──
! grep -ri --include="*.py" --include="*.sh" --include="*.json" \
    "sk-[a-zA-Z0-9]" . 2>/dev/null       # Anthropic key pattern
! grep -ri --include="*.py" --include="*.sh" --include="*.json" \
    "AIza[a-zA-Z0-9]" . 2>/dev/null       # Google API key pattern

# ── Plugin manifest validation ──
python3 -c "
import json
hooks = json.load(open('hooks/hooks.json'))
assert 'hooks' in hooks, 'hooks.json missing hooks key'
settings = json.load(open('settings.json'))
assert 'permissions' in settings, 'settings.json missing permissions key'
print('Plugin manifests OK')
"

# ── Coverage threshold (informational in CI, enforced locally) ──
# python3 -m pytest tests/ --cov=skills/orchestrator/engine --cov-report=term-missing --cov-fail-under=70
```

**Duration:** ~15s
**Gate:** No known vulnerabilities in dependencies; no leaked secrets; plugin manifests valid

---

## 3. CI Environment

### 3.1 Recommended CI Platform

**GitHub Actions** (the repo is on GitHub) with:
- Python 3.11, 3.12, 3.13 matrix testing
- pip dependency caching
- No Chrome required (unit tests and regression checks only)

### 3.2 GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12', '3.13']
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('skills/orchestrator/engine/requirements.txt') }}
          restore-keys: ${{ runner.os }}-pip-

      - name: Install dependencies
        run: |
          pip install -r skills/orchestrator/engine/requirements.txt
          pip install pytest pytest-cov pip-audit

      - name: Compile check — engine + skill files
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

      - name: Bash syntax check
        run: |
          bash -n setup.sh
          bash -n install.sh

      - name: Unit tests with coverage
        run: |
          python -m pytest tests/ -v --tb=short \
            --cov=skills/orchestrator/engine \
            --cov-report=term-missing

      - name: Regression checks
        run: |
          # Domain isolation
          ! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "solution.research" skills/orchestrator/engine/
          ! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "devops" skills/orchestrator/engine/
          ! grep -r "_PROMPT_SIGS" skills/orchestrator/engine/platforms/*.py

          # 7 platforms have check_rate_limit
          test "$(grep -l 'check_rate_limit' skills/orchestrator/engine/platforms/*.py | grep -v base.py | wc -l | tr -d ' ')" = "7"

          # RATE_LIMITS config completeness
          python -c "
          import sys; sys.path.insert(0,'skills/orchestrator/engine')
          from config import RATE_LIMITS
          assert len(RATE_LIMITS) == 7
          print('RATE_LIMITS: OK')
          "

          # CLI interface
          python skills/orchestrator/engine/orchestrator.py --prompt "x" --budget 2>&1 | grep -q "Rate Limit Budget"
          python skills/orchestrator/engine/orchestrator.py --help | grep -q "task-name"
          python skills/orchestrator/engine/orchestrator.py --help | grep -q "tier"
          python skills/orchestrator/engine/orchestrator.py --url x 2>&1 | grep -q "error"

      - name: Plugin manifest validation
        run: |
          python -c "
          import json
          hooks = json.load(open('hooks.json'))
          assert 'hooks' in hooks, 'hooks.json missing hooks key'
          settings = json.load(open('settings.json'))
          assert 'permissions' in settings, 'settings.json missing permissions key'
          print('Plugin manifests OK')
          "

      - name: Landscape smoke test
        run: |
          python skills/landscape-researcher/launch_report.py --report-dir test --report-file "Test.md" --no-browser

      - name: Dependency vulnerability scan
        run: pip-audit -r skills/orchestrator/engine/requirements.txt
        continue-on-error: true  # Advisory — does not block merge

      - name: Secret detection
        run: |
          ! grep -ri --include="*.py" --include="*.sh" --include="*.json" "sk-[a-zA-Z0-9]" . 2>/dev/null
          ! grep -ri --include="*.py" --include="*.sh" --include="*.json" "AIza[a-zA-Z0-9]" . 2>/dev/null
```

### 3.3 What CI Cannot Test

| Aspect | Reason | Mitigation |
|--------|--------|------------|
| Platform extraction (7 AIs) | Requires active logins | Manual E2E tests (Section 8) |
| Chrome CDP lifecycle | Requires Chrome + display | Manual integration tests |
| Agent fallback (browser-use) | Requires API keys + Chrome | Manual with key set |
| Skill invocation (SKILL.md) | Requires Claude Code host AI | Manual via Claude Code |
| Deep Research mode | Requires platform subscriptions | Manual E2E |
| Rate limit state file creation | Requires actual orchestration run | Manual IT-06 |
| XLSX visual output | Requires Excel/Numbers | Manual inspection |
| Plugin install flow (`claude plugin install`) | Requires published plugin | Manual post-release |

---

## 4. Local Development Workflow

### 4.1 Pre-Commit Checks

Developers should run before committing:

```bash
# Quick check — compile + 96 tests + regression (~15s)
make check

# Full check including E2E smoke test (~2 min, requires Chrome)
make check e2e-smoke
```

### 4.2 Makefile (Canonical — Source of Truth)

The actual `Makefile` in the repo root is the single source of truth for all targets. The CI workflow calls the same commands. Here is the current Makefile, reproduced verbatim:

```makefile
# MultAI — Development Targets
# Run `make check` before every commit.

VENV_PYTHON = skills/orchestrator/engine/.venv/bin/python
ENGINE      = skills/orchestrator/engine
COMPARATOR  = skills/comparator
LANDSCAPE   = skills/landscape-researcher

.PHONY: compile test regression check budget-check landscape-smoke e2e-smoke

# ── Stage 1: Compile ──────────────────────────────────────────────────────────
compile:
	@echo "=== Compile: engine files ==="
	python3 -m py_compile $(ENGINE)/orchestrator.py
	python3 -m py_compile $(ENGINE)/config.py
	python3 -m py_compile $(ENGINE)/utils.py
	python3 -m py_compile $(ENGINE)/prompt_echo.py
	python3 -m py_compile $(ENGINE)/agent_fallback.py
	python3 -m py_compile $(ENGINE)/rate_limiter.py
	python3 -m py_compile $(ENGINE)/collate_responses.py
	@echo "=== Compile: comparator files ==="
	python3 -m py_compile $(COMPARATOR)/matrix_ops.py
	python3 -m py_compile $(COMPARATOR)/matrix_builder.py
	@echo "=== Compile: landscape launcher ==="
	python3 -m py_compile $(LANDSCAPE)/launch_report.py
	@echo "=== Compile: platform files ==="
	@for f in $(ENGINE)/platforms/*.py; do python3 -m py_compile "$$f"; done
	@echo "=== Compile: shell scripts ==="
	bash -n setup.sh
	bash -n install.sh
	@echo "All compile checks passed."

# ── Stage 2: Unit Tests ──────────────────────────────────────────────────────
test:
	$(VENV_PYTHON) -m pytest tests/ -v --tb=short

# ── Stage 3: Regression ──────────────────────────────────────────────────────
regression:
	@echo "=== Regression: no domain strings in engine ==="
	@! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "solution.research" $(ENGINE)/
	@! grep -ri --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ "devops" $(ENGINE)/
	@! grep -r "_PROMPT_SIGS" $(ENGINE)/platforms/*.py
	@echo "=== Regression: 7 platforms with check_rate_limit ==="
	@test "$$(grep -l 'check_rate_limit' $(ENGINE)/platforms/*.py | grep -v base.py | wc -l | tr -d ' ')" = "7"
	@echo "=== Regression: RATE_LIMITS config ==="
	@python3 -c "\
	import sys; sys.path.insert(0,'$(ENGINE)'); \
	from config import RATE_LIMITS; \
	assert len(RATE_LIMITS) == 7, f'Expected 7, got {len(RATE_LIMITS)}'; \
	print('RATE_LIMITS: 7 platforms OK')"
	@echo "=== Regression: CLI flags ==="
	@python3 $(ENGINE)/orchestrator.py --help | grep -q "task-name"
	@python3 $(ENGINE)/orchestrator.py --help | grep -q "tier"
	@python3 $(ENGINE)/orchestrator.py --help | grep -q "budget"
	@python3 $(ENGINE)/orchestrator.py --url x 2>&1 | grep -q "error"
	@echo "=== Regression: budget command ==="
	@python3 $(ENGINE)/orchestrator.py --prompt "x" --budget 2>&1 | grep -q "Rate Limit Budget"
	@echo "All regression checks passed."

# ── Combined ──────────────────────────────────────────────────────────────────
check: compile test regression
	@echo ""
	@echo "All checks passed."

# ── Convenience ───────────────────────────────────────────────────────────────
budget-check:
	python3 $(ENGINE)/orchestrator.py --prompt "x" --budget --tier free
	@echo ""
	python3 $(ENGINE)/orchestrator.py --prompt "x" --budget --tier paid

landscape-smoke:
	python3 $(LANDSCAPE)/launch_report.py --report-dir test --report-file "Test.md" --no-browser

e2e-smoke:
	python3 $(ENGINE)/orchestrator.py --prompt "What is 2+2?" --mode REGULAR --platforms claude_ai --task-name "smoke-test"
```

### 4.3 Makefile Target Reference

| Target | Duration | What It Does | Requires Chrome? |
|--------|----------|-------------|------------------|
| `make compile` | ~3s | `py_compile` all 10 core + 9 platform .py files + `bash -n` for 2 shell scripts | No |
| `make test` | ~4s | `pytest` — 96 tests across 10 test files | No |
| `make regression` | ~5s | Domain isolation, platform count, config structure, CLI interface, budget command | No |
| `make check` | ~12s | `compile` + `test` + `regression` (the pre-commit gate) | No |
| `make budget-check` | ~3s | Display rate limit budgets for free and paid tiers | No |
| `make landscape-smoke` | ~2s | Verify `launch_report.py` produces URL output with `--no-browser` | No |
| `make e2e-smoke` | ~2 min | Run a single-platform REGULAR orchestration on claude_ai | **Yes** |

---

## 5. Security

### 5.1 Dependency Scanning

```bash
pip-audit -r skills/orchestrator/engine/requirements.txt
```

**Policy:**
- Critical/High vulnerabilities block release
- Medium vulnerabilities noted in CHANGELOG, fixed within 2 weeks
- `pip-audit` runs in CI as advisory (non-blocking) to avoid false-positive build breakage

### 5.2 Secret Detection

The repo must never contain API keys, tokens, or credentials. CI checks for common patterns:

```bash
# Anthropic API key pattern (sk-ant-...)
! grep -ri --include="*.py" --include="*.sh" --include="*.json" "sk-[a-zA-Z0-9]" .

# Google API key pattern (AIza...)
! grep -ri --include="*.py" --include="*.sh" --include="*.json" "AIza[a-zA-Z0-9]" .
```

**`.gitignore` protection:** The `.env` file (where users store API keys) is gitignored. The `rate-limit-state.json` file (in `~/.chrome-playwright/`) is outside the repo entirely.

### 5.3 Plugin Manifest Validation

Since MultAI is distributed as a Claude Code plugin, the manifest files must be valid JSON with expected structure:

```bash
python3 -c "
import json
hooks = json.load(open('hooks.json'))
assert 'hooks' in hooks
settings = json.load(open('settings.json'))
assert 'permissions' in settings
print('Plugin manifests OK')
"
```

---

## 6. Branching Model

### 6.1 Strategy: Trunk-Based Development

MultAI uses trunk-based development with short-lived feature branches:

```
main ─────●────●────●────●────●──── (always releasable)
            \       /
             ●────●    feature/add-perplexity-deep-mode
```

**Rules:**
- `main` is always the releasable state. Every commit on `main` should pass `make check`.
- Feature branches are short-lived (1-3 days max).
- No long-lived develop/staging branches — unnecessary for a local tool.
- Direct commits to `main` are allowed for single-file fixes (typos, config tweaks).
- Multi-file changes use feature branches with PR review.

### 6.2 Branch Naming Convention

| Pattern | Use |
|---------|-----|
| `feature/<description>` | New features (e.g., `feature/add-gemini-deep-mode`) |
| `fix/<description>` | Bug fixes (e.g., `fix/copilot-selector-update`) |
| `docs/<description>` | Documentation only (e.g., `docs/cicd-rewrite`) |

### 6.3 Branch Protection (If Multi-Developer)

When multiple contributors join:
- Require `make check` CI to pass before merge
- Require 1 approval on PRs touching `skills/orchestrator/engine/`
- No force-push to `main`

---

## 7. Versioning Strategy

### 7.1 Version Scheme

`{Major}.{Minor}.{YYMMDDX} {Phase}` — hybrid semver + CalVer.

| Component | Meaning | Example |
|-----------|---------|---------|
| **Major** | Breaking changes, architectural overhauls | `0` → `1` |
| **Minor** | New features within existing architecture | `0.1` → `0.2` |
| **YYMMDDX** | Calendar date + daily increment letter. Updated with **every commit**. | `260318A`, `260318B`, `260319A` |
| **Phase** | Maturity label: `Alpha`, `Beta`, `RC`, or omitted for GA | `Alpha` |

**Formats by context:**

| Context | Format | Example |
|---------|--------|---------|
| Git tags | `vMajor.Minor.YYMMDDX-phase` | `v0.2.260318A-alpha` |
| Doc headers | `Version: Major.Minor.YYMMDDX Phase` | `Version: 0.2.260318A Alpha` |
| pyproject.toml | `version = "Major.Minor.YYMMDD"` (PEP 440; letter in metadata) | `version = "0.2.260318"` |
| Website / UI | Display version with phase | `v0.2.260318A Alpha` |
| CHANGELOG | `## Major.Minor.YYMMDDX Phase — Title` | `## 0.2.260318A Alpha — Initial Release` |

**Current version:** 0.2.260318A Alpha

### 7.2 What Gets Versioned

| Component | Versioning | Where Tracked |
|-----------|-----------|---------------|
| Engine (Python) | In `CHANGELOG.md` | Semantic entries per version |
| Skills (SKILL.md) | In `CHANGELOG.md` | Per-skill entries |
| Domain knowledge (.md) | In the file itself | Enrichment entries appended with timestamps |
| Docs (SRS, Architecture, Test, CI/CD) | Version number + date in file header | Updated with each version |
| Plugin manifests (`hooks.json`, `settings.json`) | In `CHANGELOG.md` | Only when permissions or hooks change |

### 7.3 CHANGELOG Format

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

## 8. Release Process

### 8.1 Release Checklist

1. **Develop** — Make changes on a feature branch (or directly on main for small fixes)
2. **Pre-commit** — Run `make check`; all 96 tests + regression checks must pass
3. **Budget check** — Run `make budget-check` to confirm rate limit configs are correct
4. **Update docs** — Update CHANGELOG.md, and any impacted SRS/Architecture/Test/CI-CD docs
5. **Version bump** — Update version numbers in doc headers
6. **Tag** — `git tag v4.x` (or next version)
7. **E2E smoke** — Run `make e2e-smoke` on local machine with Chrome to confirm the engine starts
8. **Plugin test** — Verify `claude plugin install` works from a clean environment (post-push)

### 8.2 Release Artifacts

MultAI is distributed as a Claude Code plugin. The "release" is the state of the repository at a tagged commit. Users install or update via:

```bash
claude plugin install alo-exp/multai
```

There is no separate package to publish (no PyPI, no npm). The GitHub repository IS the distribution channel.

### 8.3 Rollback Procedure

If a release introduces a regression:

1. **Identify** — User reports issue or `make check` fails on latest `main`
2. **Hotfix** — Create `fix/<description>` branch from previous tag, apply fix, merge to `main`
3. **Tag** — Create new patch version (e.g., `v4.2.1`)
4. **Notify** — Update CHANGELOG with rollback note
5. **Users re-install** — `claude plugin install alo-exp/multai` pulls latest `main`

For catastrophic regressions where a hotfix isn't immediately available:
```bash
git revert <commit>   # Revert the breaking change
git tag v4.x.1        # Tag the revert
```

---

## 9. Plugin-Specific CI Considerations

### 9.1 Plugin Manifest Files

MultAI's plugin identity is defined by two files that CI must validate:

| File | Purpose | Validation |
|------|---------|------------|
| `hooks.json` | Defines lifecycle hooks (session_start → install.sh) | Valid JSON, has `hooks` key, references existing scripts |
| `settings.json` | Default permissions and settings for Claude Code | Valid JSON, has `permissions` key |
| `install.sh` | First-run bootstrap (delegates to setup.sh) | `bash -n` syntax check, references setup.sh |
| `setup.sh` | Dependency installer (venv, pip, playwright) | `bash -n` syntax check |

### 9.2 Plugin Install Smoke Test (Manual)

After every release tag, verify on a clean machine (or clean directory):

```bash
# 1. Install from GitHub
claude plugin install alo-exp/multai

# 2. Start Claude Code in the plugin directory
claude

# 3. Type a test prompt — should trigger orchestrator routing
> What is 2+2?

# 4. Verify setup.sh ran (venv exists, deps installed)
ls skills/orchestrator/engine/.venv/bin/python
```

This cannot be automated in CI because it requires the Claude Code runtime.

---

## 10. Test Infrastructure Evolution

### 10.1 Phase 1 (Current — v4.2)

**Implemented and running in `make check`:**

- 96 automated tests across 10 test files (pytest)
- Compile checks for 10 core modules + 9 platform files + 2 shell scripts
- Regression checks: domain isolation (2 patterns), prompt signature guard, platform count, RATE_LIMITS structure, CLI interface (4 flags), budget command
- Landscape workflow smoke test
- Plugin manifest validation (hooks.json, settings.json)
- Bash syntax checks (setup.sh, install.sh)

### 10.2 Phase 2 (Next — Trigger: First External Contributor)

| Item | What | Acceptance Criteria | Effort |
|------|------|---------------------|--------|
| **HTML snapshot tests** | Save AI platform page HTML; test extraction logic against snapshots | 7 snapshot files (1/platform), extraction returns expected chars ±10% | 2 days |
| **Playwright dry-run mode** | Engine flag `--dry-run` connecting to Chrome, navigating, stopping before injection | `--dry-run` exits 0 with 7 "navigated" log lines; no prompt injected | 1 day |
| **Matrix snapshot tests** | Save reference XLSX; compare after `matrix_ops` operations | `add-platform` output matches reference cell-by-cell (excluding timestamps) | 1 day |
| **Rate limit state replay** | Pre-seeded state JSON files testing budget/cooldown enforcement | 5 scenarios: fresh, mid-budget, exhausted, cooldown-active, daily-cap-hit | 1 day |
| **Coverage threshold** | `pytest --cov-fail-under=70` enforced in CI | CI fails if engine coverage drops below 70% | 0.5 day |
| **Pre-commit hooks** | `pre-commit` framework running `make check` on every commit | `.pre-commit-config.yaml` exists, `pre-commit install` works | 0.5 day |

### 10.3 Phase 3 (Future — Trigger: 3+ Contributors or Public Release)

| Item | What | Acceptance Criteria | Effort |
|------|------|---------------------|--------|
| **Scheduled E2E** | Weekly cron GitHub Action running all 7 platforms on a self-hosted runner | Cron job produces `status.json` with 7 entries; Slack notification on drift | 3 days |
| **Platform selector health checks** | Script navigating to each AI platform, verifying key selectors exist | 7-platform report: selector found/missing/changed with screenshot diff | 2 days |
| **Automated CHANGELOG generation** | Conventional commits + auto-generated CHANGELOG entries | `npm run changelog` produces correct markdown from commit messages | 1 day |
| **Branch protection rules** | Require CI pass + 1 approval before merge | GitHub branch protection enabled on `main` | 0.5 day |
| **Dependency auto-update** | Dependabot or Renovate for Python dependencies | PRs auto-created for outdated deps; CI runs on those PRs | 0.5 day |
| **Doc-code sync check** | CI verifies doc test counts match `pytest --collect-only` | Script compares doc "Total: N" with actual collected count; fails on mismatch | 1 day |

---

## 11. Monitoring and Notifications

### 11.1 CI Failure Notification

**Current (single developer):** GitHub email notifications on workflow failure (default).

**Future (multi-developer):** Add Slack webhook notification step:

```yaml
- name: Notify on failure
  if: failure()
  uses: slackapi/slack-github-action@v2
  with:
    webhook: ${{ secrets.SLACK_WEBHOOK }}
    payload: |
      {"text": "CI failed on ${{ github.ref }}: ${{ github.event.head_commit.message }}"}
```

### 11.2 Platform Drift Detection

AI platforms update their UIs without notice, breaking Playwright selectors. Currently detected manually during E2E runs. Phase 3 adds automated weekly health checks (see Section 10.3).

**Current drift detection signals:**
- E2E test fails with "extraction returned 0 chars"
- Agent fallback fires (logged to `agent-fallback-log.json`)
- Rate limit state shows `STATUS_FAILED` for a previously-working platform
