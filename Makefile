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
