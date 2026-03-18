#!/usr/bin/env bash
# version-stamp.sh — Propagate version from pyproject.toml to all locations.
#
# Usage:
#   bash scripts/version-stamp.sh              # stamp current version everywhere
#   bash scripts/version-stamp.sh --check      # verify all locations match (CI mode)
#   bash scripts/version-stamp.sh --bump 0.2.260319A Alpha   # set new version + stamp
#
# Source of truth: pyproject.toml `version` field (PEP 440: "Major.Minor.YYMMDD")
# Display version: passed as argument or auto-derived from git tag.
#
# Locations updated:
#   1. pyproject.toml                    (PEP 440 format: "0.2.260318")
#   2. .claude-plugin/plugin.json        (same as pyproject.toml)
#   3. .claude-plugin/marketplace.json   (same as pyproject.toml)
#   4. docs/index.html                   (display format: "v0.2.260318A Alpha")
#   5. docs/SRS.md                       (display format)
#   6. docs/Architecture-and-Design.md   (display format)
#   7. docs/Test-Strategy-and-Plan.md    (display format)
#   8. docs/CICD-Strategy-and-Plan.md    (display format)
#   9. CONTRIBUTOR-GUIDE.md              (display format)
#  10. USER-GUIDE.md                     (display format)

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# ── Read current PEP 440 version from pyproject.toml ──
PEP_VERSION=$(grep '^version' pyproject.toml | sed 's/version *= *"\(.*\)"/\1/')

# ── Derive display version ──
# Try git tag first (e.g., v0.2.260318A-alpha → 0.2.260318A Alpha)
DISPLAY_VERSION=""
GIT_TAG=$(git describe --tags --exact-match 2>/dev/null || echo "")
if [ -n "$GIT_TAG" ]; then
    # v0.2.260318A-alpha → 0.2.260318A Alpha
    DISPLAY_VERSION=$(echo "$GIT_TAG" | sed 's/^v//' | sed 's/-alpha/ Alpha/' | sed 's/-beta/ Beta/' | sed 's/-rc/ RC/')
fi

# Fallback: scan doc headers for current display version
if [ -z "$DISPLAY_VERSION" ]; then
    DISPLAY_VERSION=$(grep -m1 'Version:' docs/SRS.md | sed 's/.*Version:\*\* *//; s/ *$//')
fi

# ── Handle arguments ──
MODE="stamp"
if [ "${1:-}" = "--check" ]; then
    MODE="check"
    # In check mode, always read display version from files (not tag)
    # since the tag may not exist yet for the current version
    DISPLAY_VERSION=$(grep -m1 'Version:' docs/SRS.md | sed 's/.*Version:\*\* *//; s/ *$//')
elif [ "${1:-}" = "--bump" ]; then
    shift
    if [ $# -lt 1 ]; then
        echo "Usage: version-stamp.sh --bump <display-version>"
        echo "  e.g.: version-stamp.sh --bump '0.2.260319A Alpha'"
        exit 1
    fi
    DISPLAY_VERSION="$*"
    # Extract PEP version: "0.2.260319A Alpha" → "0.2.260319"
    PEP_VERSION=$(echo "$DISPLAY_VERSION" | sed 's/\([0-9]*\.[0-9]*\.[0-9]*\).*/\1/')
    MODE="bump"
fi

echo "PEP 440 version:  $PEP_VERSION"
echo "Display version:  $DISPLAY_VERSION"
echo ""

# ── Check mode: verify all locations match ──
if [ "$MODE" = "check" ]; then
    ERRORS=0

    # PEP version checks
    for f in .claude-plugin/plugin.json .claude-plugin/marketplace.json; do
        if ! grep -q "\"$PEP_VERSION\"" "$f" 2>/dev/null; then
            echo "MISMATCH: $f does not contain \"$PEP_VERSION\""
            ERRORS=$((ERRORS+1))
        else
            echo "  OK: $f"
        fi
    done

    # Display version checks (website)
    DISPLAY_ESCAPED=$(echo "$DISPLAY_VERSION" | sed 's/\./\\./g')
    SITE_COUNT=$(grep -c "$DISPLAY_ESCAPED" docs/index.html 2>/dev/null || true)
    SITE_COUNT=$(echo "$SITE_COUNT" | tr -d '[:space:]')
    if [ "$SITE_COUNT" -lt 3 ]; then
        echo "MISMATCH: docs/index.html has $SITE_COUNT refs (expected 3) for '$DISPLAY_VERSION'"
        ERRORS=$((ERRORS+1))
    else
        echo "  OK: docs/index.html ($SITE_COUNT refs)"
    fi

    # Doc header checks
    for f in docs/SRS.md docs/Architecture-and-Design.md docs/Test-Strategy-and-Plan.md docs/CICD-Strategy-and-Plan.md CONTRIBUTOR-GUIDE.md USER-GUIDE.md; do
        if ! grep -q "$DISPLAY_VERSION" "$f" 2>/dev/null; then
            echo "MISMATCH: $f does not contain '$DISPLAY_VERSION'"
            ERRORS=$((ERRORS+1))
        else
            echo "  OK: $f"
        fi
    done

    if [ "$ERRORS" -gt 0 ]; then
        echo ""
        echo "FAIL: $ERRORS version mismatches found. Run: bash scripts/version-stamp.sh --bump '<version>'"
        exit 1
    else
        echo ""
        echo "PASS: all 10 locations match version $DISPLAY_VERSION"
        exit 0
    fi
fi

# ── Stamp / Bump mode: update all locations ──
if [ "$MODE" = "bump" ]; then
    echo "Updating pyproject.toml..."
    sed -i '' "s/^version = \".*\"/version = \"$PEP_VERSION\"/" pyproject.toml
fi

echo "Updating .claude-plugin/plugin.json..."
sed -i '' "s/\"version\": \"[^\"]*\"/\"version\": \"$PEP_VERSION\"/" .claude-plugin/plugin.json

echo "Updating .claude-plugin/marketplace.json..."
sed -i '' "s/\"version\": \"[^\"]*\"/\"version\": \"$PEP_VERSION\"/" .claude-plugin/marketplace.json

echo "Updating docs/index.html..."
# Match any version pattern like v0.x.YYMMDDX... Phase
sed -i '' "s/v[0-9]*\.[0-9]*\.[0-9A-Za-z]* [A-Za-z]*/v$DISPLAY_VERSION/g" docs/index.html

echo "Updating doc headers..."
for f in docs/SRS.md docs/Architecture-and-Design.md docs/Test-Strategy-and-Plan.md docs/CICD-Strategy-and-Plan.md; do
    sed -i '' "s/\*\*Version:\*\* .*/\*\*Version:\*\* $DISPLAY_VERSION/" "$f"
done

echo "Updating CONTRIBUTOR-GUIDE.md..."
sed -i '' "s/\*\*Version:\*\* .* | \*\*Date:\*\*/\*\*Version:\*\* $DISPLAY_VERSION | \*\*Date:\*\*/" CONTRIBUTOR-GUIDE.md

echo "Updating USER-GUIDE.md..."
sed -i '' "s/\*\*Version:\*\* .* | \*\*Date:\*\*/\*\*Version:\*\* $DISPLAY_VERSION | \*\*Date:\*\*/" USER-GUIDE.md

echo ""
echo "Done. Version stamped to: $DISPLAY_VERSION (PEP: $PEP_VERSION)"
echo "Run 'bash scripts/version-stamp.sh --check' to verify."
