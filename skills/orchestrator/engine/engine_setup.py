"""Engine dependency bootstrap and environment setup."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

_ENGINE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _ENGINE_DIR.parent.parent.parent


def _strip_quotes(val: str) -> str:
    """Remove matching outer quotes only (single or double)."""
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        return val[1:-1]
    return val


def _load_dotenv() -> None:
    """Read <project-root>/.env into os.environ (stdlib only). Existing vars are never overwritten."""
    env_file = _PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    with env_file.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = _strip_quotes(value.strip())
            if key and key not in os.environ:
                os.environ[key] = value


def _ensure_venv() -> None:
    """Ensure we're running inside a virtual environment.

    Homebrew / PEP 668 Python blocks pip install outside a venv.
    If we're not in one, create .venv/ beside this script and re-exec.
    """
    if sys.prefix != sys.base_prefix:
        return  # Already inside a venv — nothing to do

    venv_dir = Path(__file__).parent / ".venv"
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python3"

    if not venv_python.exists():
        print("  Creating virtual environment (.venv/)...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])

    # Re-exec with the venv python — replaces the current process
    print("  Activating virtual environment...")
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)


def _verify_playwright(python_exe: str) -> None:
    """Verify that Playwright is importable and Chromium can be launched headlessly.

    Prints a warning (does not exit) if verification fails so the user knows
    their installation is broken before they hit a confusing runtime error.

    Results are cached via a stamp file in the venv directory. The stamp records
    the Playwright package version; if it matches, the expensive headless launch
    check is skipped on subsequent runs.
    """
    venv_dir = Path(python_exe).parent.parent  # .../engine/.venv/
    stamp_file = venv_dir / ".playwright-verified"
    try:
        pw_version = importlib.metadata.version("playwright")
    except Exception:
        pw_version = None
    if pw_version and stamp_file.exists():
        try:
            if stamp_file.read_text(encoding="utf-8").strip() == pw_version:
                return  # Already verified for this version
        except Exception:
            pass

    # Import check
    try:
        result = subprocess.run(
            [python_exe, "-c", "from playwright.async_api import async_playwright; print('OK')"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or "OK" not in result.stdout:
            print(
                "  WARNING: Playwright is installed but failed to import. "
                "Run: pip install playwright==1.58.0"
            )
            return
    except Exception as exc:
        print(f"  WARNING: Could not verify Playwright import: {exc}")
        return

    # Headless launch check
    _LAUNCH_SCRIPT = (
        "import asyncio\n"
        "from playwright.async_api import async_playwright\n"
        "async def _t():\n"
        "    async with async_playwright() as p:\n"
        "        b = await p.chromium.launch(headless=True)\n"
        "        pg = await b.new_page()\n"
        "        await pg.goto('about:blank')\n"
        "        await b.close()\n"
        "        print('OK')\n"
        "asyncio.run(_t())\n"
    )
    try:
        result = subprocess.run(
            [python_exe, "-c", _LAUNCH_SCRIPT],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0 or "OK" not in result.stdout:
            print(
                "  WARNING: Playwright is installed but Chromium failed to launch. "
                "Run: python3 -m playwright install chromium"
            )
            return
    except Exception as exc:
        print(f"  WARNING: Could not verify Playwright Chromium launch: {exc}")
        return

    # Write stamp on successful verification
    if pw_version:
        try:
            stamp_file.write_text(pw_version, encoding="utf-8")
        except Exception:  # pragma: no cover
            pass  # Non-fatal — will just re-verify next time


def _verify_browser_use(python_exe: str) -> None:
    """Verify that browser-use Agent can be imported.

    Prints a warning (does not exit) if verification fails.
    """
    try:
        result = subprocess.run(
            [python_exe, "-c", "from browser_use import Agent; print('OK')"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or "OK" not in result.stdout:
            print(
                "  WARNING: browser-use is installed but failed to import. "
                "Run: pip install browser-use==0.12.2"
            )
    except Exception as exc:
        print(f"  WARNING: Could not verify browser-use import: {exc}")


def _ensure_dependencies() -> None:
    """Auto-install required Python packages and browser binaries on first use."""
    installed = False

    # 1. Mandatory: playwright
    if importlib.util.find_spec("playwright") is None:
        print("  Installing playwright...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", "playwright==1.58.0"],
            )
        except subprocess.CalledProcessError:
            print("  ERROR: Failed to install playwright. Install manually:")
            print("    pip install playwright==1.58.0")
            sys.exit(1)  # pragma: no cover
        print("  Installing Chromium browser (one-time download, ~130 MB)...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "playwright", "install", "chromium"],
            )
        except subprocess.CalledProcessError:
            print("  ERROR: Failed to install Chromium. Install manually:")
            print("    python3 -m playwright install chromium")
            sys.exit(1)  # pragma: no cover
        installed = True

    # Verify playwright import and Chromium availability
    _verify_playwright(sys.executable)

    # 2. Optional: browser-use (install whenever Python supports it; API key
    #    absence only disables the runtime manager, not the package itself)
    optional = []
    if importlib.util.find_spec("browser_use") is None:
        optional.append("browser-use==0.12.2")
    if optional:
        print(f"  Installing Agent fallback packages: {', '.join(optional)}")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet"] + optional,
            )
        except subprocess.CalledProcessError:
            print(f"  WARNING: Failed to install optional packages: {', '.join(optional)}")
            print("  Agent fallback will be disabled. To install manually:")
            print(f"    pip install {' '.join(optional)}")
            # Don't exit — these are optional
        else:
            installed = True
            _verify_browser_use(sys.executable)

    if installed:
        print("  All dependencies ready.\n")
