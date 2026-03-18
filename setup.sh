#!/usr/bin/env bash
# MultAI — one-time bootstrap for the Playwright/Browser-Use engine
# Run from the repo root: bash setup.sh
# Optional: bash setup.sh --with-fallback   (also installs browser-use agent)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$SCRIPT_DIR/skills/orchestrator/engine"
VENV_DIR="$ENGINE_DIR/.venv"
WITH_FALLBACK=false

for arg in "$@"; do
  [[ "$arg" == "--with-fallback" ]] && WITH_FALLBACK=true
done

# ── helpers ──────────────────────────────────────────────────────────────────
info()    { echo "  → $*"; }
success() { echo "  ✓ $*"; }
warn()    { echo "  ⚠ $*"; }
die()     { echo "  ✗ ERROR: $*" >&2; exit 1; }

echo ""
echo "MultAI Setup"
echo "────────────────────────────────────────────"

# ── Python version check + venv selection ────────────────────────────────────
# If .venv already exists and has a working python, use it directly —
# no need to re-validate the system python version on subsequent runs.
if [[ -x "$VENV_DIR/bin/python" ]] && "$VENV_DIR/bin/python" --version > /dev/null 2>&1; then
  PYTHON="$VENV_DIR/bin/python"
  PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  info "Existing .venv Python $PY_VER — reusing"
else
  info "Checking Python version..."
  # Search for python 3.11+ — prefer Homebrew, then system
  PYTHON=""
  for candidate in python3.13 python3.12 python3.11 python3; do
    candidate_path=$(command -v "$candidate" 2>/dev/null || true)
    if [[ -n "$candidate_path" ]]; then
      PY_MAJOR=$("$candidate_path" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
      PY_MINOR=$("$candidate_path" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
      if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]]; then
        PYTHON="$candidate_path"
        break
      fi
    fi
  done
  [[ -z "$PYTHON" ]] && die "Python 3.11+ not found. Install it from https://www.python.org/downloads/ or via Homebrew: brew install python@3.13"
  PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  success "Python $PY_VER"

  # ── Virtual environment ─────────────────────────────────────────────────────
  info "Creating virtual environment at skills/orchestrator/engine/.venv ..."
  "$PYTHON" -m venv "$VENV_DIR"
  success "Virtual environment created"
fi

PIP="$VENV_DIR/bin/pip"
PYTHON_VENV="$VENV_DIR/bin/python"

# ── Core dependencies ─────────────────────────────────────────────────────────
info "Installing core dependencies (playwright, openpyxl)..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet "playwright>=1.40.0" "openpyxl>=3.1.0"
success "Core dependencies installed"

# ── Playwright browsers ───────────────────────────────────────────────────────
info "Installing Playwright Chromium browser..."
"$PYTHON_VENV" -m playwright install chromium
success "Chromium installed"

# ── Optional: browser-use fallback ───────────────────────────────────────────
if [[ "$WITH_FALLBACK" == true ]]; then
  info "Installing browser-use agent fallback (--with-fallback)..."
  "$PIP" install --quiet "browser-use==0.12.2" "anthropic>=0.76.0" "fastmcp>=2.0.0"
  success "browser-use fallback installed"
else
  warn "Skipping browser-use fallback (add --with-fallback to enable it)"
fi

# ── Smoke test ────────────────────────────────────────────────────────────────
info "Running smoke test..."
if smoke_output=$("$PYTHON_VENV" "$ENGINE_DIR/orchestrator.py" --budget --tier free 2>&1); then
  success "Engine smoke test passed"
else
  warn "Smoke test returned non-zero — output:"
  echo "$smoke_output" | head -10 | sed 's/^/    /'
  warn "Check your Chrome / profile setup (see skills/orchestrator/platform-setup.md)"
fi

echo ""
echo "────────────────────────────────────────────"
echo "  Setup complete. You're ready to use MultAI."
echo ""
echo "  Next: open Claude Code in this directory and invoke a skill, e.g.:"
echo "    /orchestrator  →  route a research task"
echo "    /landscape-researcher  →  market landscape analysis"
echo "    /solution-researcher   →  competitive intelligence on a product"
echo ""
echo "  See USER-GUIDE.md for full usage instructions."
echo ""

# ── .env template (if missing) ───────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  info "Creating .env template..."
  cat > "$ENV_FILE" <<'EOF'
# MultAI environment configuration
# Add optional API keys for the browser-use agent fallback.

# ANTHROPIC_API_KEY=your_anthropic_key_here
# GOOGLE_API_KEY=your_google_api_key_here
EOF
  success ".env template created — add API keys if using the agent fallback"
fi
