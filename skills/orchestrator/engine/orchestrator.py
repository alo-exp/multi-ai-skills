#!/usr/bin/env python3
"""
Multi-AI Orchestrator Engine.

Launches 7 AI platforms in parallel, injects a user-provided prompt,
waits for responses, extracts results, and saves them to the output directory.

This engine is generic — it accepts any pre-built prompt and has no
domain-specific or task-type-specific logic.

Usage:
    python3 orchestrator.py \
        --prompt-file /tmp/research-prompt.md \
        --mode REGULAR \
        --output-dir ../reports/

Dependencies are auto-installed on first run. To install manually:
    pip install -r requirements.txt
    playwright install chromium
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys

from datetime import datetime
from pathlib import Path

# Ensure the engine directory is on the path
_ENGINE_DIR = Path(__file__).resolve().parent       # .../skills/orchestrator/engine/
_PROJECT_ROOT = _ENGINE_DIR.parent.parent.parent    # .../multi-ai-skills/
_DEFAULT_OUTPUT_DIR = str(_PROJECT_ROOT / "reports")

sys.path.insert(0, str(_ENGINE_DIR))


# ---------------------------------------------------------------------------
# .env loader — reads <project-root>/.env into os.environ (stdlib only,
# no dotenv dependency required).  Existing env vars are never overwritten.
# ---------------------------------------------------------------------------
def _load_dotenv() -> None:
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
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


# ---------------------------------------------------------------------------
# Dependency bootstrap — auto-install on first run
# ---------------------------------------------------------------------------

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
        except Exception:
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
            sys.exit(1)
        print("  Installing Chromium browser (one-time download, ~130 MB)...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "playwright", "install", "chromium"],
            )
        except subprocess.CalledProcessError:
            print("  ERROR: Failed to install Chromium. Install manually:")
            print("    python3 -m playwright install chromium")
            sys.exit(1)
        installed = True

    # Verify playwright import and Chromium availability
    _verify_playwright(sys.executable)

    # 2. Optional: browser-use (only when ANTHROPIC_API_KEY or GOOGLE_API_KEY is set)
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
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


_ensure_venv()            # Create .venv/ and re-exec if not already in a venv
_ensure_dependencies()    # pip install missing packages (safe inside venv)

# ---------------------------------------------------------------------------
# External imports (safe after bootstrap)
# ---------------------------------------------------------------------------

from playwright.async_api import async_playwright, BrowserContext  # noqa: E402

from agent_fallback import AgentFallbackManager  # noqa: E402
from config import (  # noqa: E402
    AGENT_MAX_STEPS,
    CDP_PORT,
    DEEP_MODE,
    GLOBAL_TIMEOUT_DEEP,
    GLOBAL_TIMEOUT_REGULAR,
    PLATFORM_DISPLAY_NAMES,
    PLATFORM_URL_DOMAINS,
    PLATFORM_URLS,
    REGULAR_MODE,
    STAGGER_DELAY,
    STATUS_FAILED,
    STATUS_ICONS,
    STATUS_NEEDS_LOGIN,
    STATUS_RATE_LIMITED,
    STATUS_TIMEOUT,
    TIMEOUTS,
    detect_chrome_executable,
    detect_chrome_user_data_dir,
)
from platforms import ALL_PLATFORMS  # noqa: E402
from prompt_echo import auto_extract_prompt_sigs  # noqa: E402
from rate_limiter import RateLimiter  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orchestrator")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-AI Orchestrator Engine")

    # Prompt input (mutually exclusive, one required)
    prompt_group = p.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="Literal prompt text")
    prompt_group.add_argument("--prompt-file", help="Path to pre-built prompt file")

    # Optional condensed prompt for constrained platforms
    condensed_group = p.add_mutually_exclusive_group()
    condensed_group.add_argument("--condensed-prompt", default="",
                                 help="Condensed prompt text for constrained platforms")
    condensed_group.add_argument("--condensed-prompt-file", default="",
                                 help="Path to condensed prompt file")

    # Optional explicit prompt signatures (escape hatch)
    p.add_argument("--prompt-sigs", default="",
                   help="Comma-separated prompt-echo detection signatures (auto-detected if not set)")

    # Mode and platform selection
    p.add_argument("--mode", choices=["DEEP", "REGULAR"], default="REGULAR",
                   type=str.upper,
                   help="Orchestration mode (default: REGULAR)")
    p.add_argument("--task-name", default="",
                   help="Short name for this run — output goes to reports/{task-name}/ (recommended)")
    p.add_argument("--output-dir", default=_DEFAULT_OUTPUT_DIR,
                   help="Output directory for raw responses (default: <project-root>/reports/). "
                        "Overridden by --task-name if both are supplied.")
    p.add_argument("--chrome-profile", default="Default",
                   help="Chrome profile directory name (default: Default)")
    p.add_argument("--headless", action="store_true",
                   help="Run browsers headlessly (not recommended — some platforms block headless)")
    p.add_argument("--platforms", default="all",
                   help="Comma-separated platform names to run, or 'all' (default: all)")
    p.add_argument("--fresh", action="store_true",
                   help="Force launch a new Chrome (kill any existing). Default: reuse running Chrome.")
    p.add_argument("--followup", action="store_true",
                   help="Follow-up on the same topic: reuse existing conversations in open tabs "
                        "instead of starting new ones. Skips navigation and mode configuration.")

    # Rate limiting
    p.add_argument("--tier", choices=["free", "paid"], default="free",
                   help="Subscription tier for rate limit budgets (default: free)")
    p.add_argument("--skip-rate-check", action="store_true",
                   help="Bypass rate limit pre-flight checks (dangerous)")
    p.add_argument("--budget", action="store_true",
                   help="Show rate limit budget summary and exit")
    p.add_argument("--stagger-delay", type=int, default=STAGGER_DELAY,
                   help=f"Seconds between staggered platform launches (default: {STAGGER_DELAY})")

    return p.parse_args()


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompts(args: argparse.Namespace) -> tuple[str, str, list[str]]:
    """Load full prompt, condensed prompt, and auto-extract echo signatures.

    Returns:
        (full_prompt, condensed_prompt, prompt_sigs)
    """
    # Load full prompt
    if args.prompt:
        full_prompt = args.prompt
    else:
        path = Path(args.prompt_file)
        if not path.exists():
            log.error(f"Prompt file not found: {args.prompt_file}")
            sys.exit(1)
        _MAX_PROMPT_BYTES = 512_000  # 500 KB ceiling
        if path.stat().st_size > _MAX_PROMPT_BYTES:
            log.error(f"Prompt file exceeds 500 KB limit ({path.stat().st_size} bytes): {args.prompt_file}")
            sys.exit(1)
        full_prompt = path.read_text(encoding="utf-8")

    # Load condensed prompt (optional — falls back to full prompt)
    if args.condensed_prompt:
        condensed_prompt = args.condensed_prompt
    elif args.condensed_prompt_file:
        path = Path(args.condensed_prompt_file)
        if not path.exists():
            log.error(f"Condensed prompt file not found: {args.condensed_prompt_file}")
            sys.exit(1)
        condensed_prompt = path.read_text(encoding="utf-8")
    else:
        condensed_prompt = full_prompt

    # Extract prompt-echo detection signatures
    if args.prompt_sigs:
        prompt_sigs = [s.strip() for s in args.prompt_sigs.split(",") if s.strip()]
    else:
        prompt_sigs = auto_extract_prompt_sigs(full_prompt)

    log.info(f"Full prompt: {len(full_prompt)} chars | Condensed: {len(condensed_prompt)} chars | Sigs: {prompt_sigs}")
    return full_prompt, condensed_prompt, prompt_sigs


# ---------------------------------------------------------------------------
# Platform runner
# ---------------------------------------------------------------------------

async def run_single_platform(
    platform_name: str,
    context: BrowserContext,
    full_prompt: str,
    condensed_prompt: str,
    prompt_sigs: list[str],
    mode: str,
    output_dir: str,
    agent_manager: AgentFallbackManager | None = None,
    existing_page=None,
    followup: bool = False,
) -> dict:
    """Find or create a page, instantiate the platform class, and run it.

    Args:
        existing_page: An open Playwright Page for this platform (from a prior run).
                       If None, a new tab is opened.
        followup: Pass True to reuse the existing conversation (skip navigation/config).
    """
    cls = ALL_PLATFORMS[platform_name]
    platform = cls()
    platform.agent_manager = agent_manager
    platform.prompt_sigs = prompt_sigs

    # Use condensed prompt for platforms configured with use_condensed=True
    # (e.g. Grok, which has injection constraints on very long prompts)
    mode_cfg_map = DEEP_MODE if mode == "DEEP" else REGULAR_MODE
    mode_cfg = mode_cfg_map.get(platform_name)
    if mode_cfg and mode_cfg.use_condensed and condensed_prompt:
        prompt = condensed_prompt
        if condensed_prompt != full_prompt:
            log.info(f"[{platform_name}] Using condensed prompt ({len(condensed_prompt)} chars vs {len(full_prompt)} full)")
    else:
        prompt = full_prompt

    # Reuse existing tab or open a new one
    if existing_page is not None:
        page = existing_page
        tab_source = "reused"
    else:
        page = await context.new_page()
        tab_source = "new"
    log.info(f"[{PLATFORM_DISPLAY_NAMES.get(platform_name, platform_name)}] Tab: {tab_source}")

    try:
        result = await platform.run(page, prompt, mode, output_dir, followup=followup)
        return {
            "platform": result.platform,
            "display_name": result.display_name,
            "status": result.status,
            "chars": result.chars,
            "file": result.file,
            "mode_used": result.mode_used,
            "error": result.error,
            "duration_s": round(result.duration_s, 1),
        }
    except Exception as exc:
        log.exception(f"[{platform.display_name}] Unhandled error: {exc}")
        return {
            "platform": platform_name,
            "display_name": platform.display_name,
            "status": STATUS_FAILED,
            "chars": 0,
            "file": "",
            "mode_used": "",
            "error": str(exc),
            "duration_s": 0,
        }
    finally:
        pass  # Leave tab open so the user can inspect results after the run


# ---------------------------------------------------------------------------
# Rate-limited staggered runner
# ---------------------------------------------------------------------------

async def _staggered_run(
    platform_name: str,
    delay_seconds: float,
    context: BrowserContext,
    full_prompt: str,
    condensed_prompt: str,
    prompt_sigs: list[str],
    mode: str,
    output_dir: str,
    agent_manager: AgentFallbackManager | None,
    limiter: RateLimiter,
    existing_page=None,
    followup: bool = False,
) -> dict:
    """Wait for stagger delay, then run platform and record usage."""
    if delay_seconds > 0:
        log.info(f"[{PLATFORM_DISPLAY_NAMES.get(platform_name, platform_name)}] Stagger delay: {delay_seconds:.0f}s")
        await asyncio.sleep(delay_seconds)

    result = await run_single_platform(
        platform_name, context, full_prompt, condensed_prompt,
        prompt_sigs, mode, output_dir, agent_manager,
        existing_page=existing_page, followup=followup,
    )

    # Record usage for rate tracking
    limiter.record_usage(
        platform=platform_name,
        mode=mode,
        status=result["status"],
        duration_s=result.get("duration_s", 0),
    )

    return result


def show_budget(args: argparse.Namespace) -> None:
    """Print rate limit budget summary and exit."""
    limiter = RateLimiter(tier=args.tier)
    limiter.load_state()
    summary = limiter.get_budget_summary(args.mode)

    print(f"\n  Rate Limit Budget Summary (tier: {args.tier}, mode: {args.mode})")
    print("=" * 72)
    print(f"  {'Platform':<20} {'Used':>6} {'Budget':>8} {'Next Available':>16} {'Cooldown':>10}")
    print("-" * 72)

    for _platform_name, info in summary.items():
        used = info["total"] - info["remaining"]
        budget_str = f"{used}/{info['total']}"
        remaining_str = f"{info['remaining']} left"
        avail = "now" if info["next_available_in"] == 0 else f"in {info['next_available_in']}s"
        cooldown_m = info["cooldown"] // 60
        cooldown_str = f"{cooldown_m}m" if cooldown_m > 0 else f"{info['cooldown']}s"
        print(f"  {info['display_name']:<20} {budget_str:>6} {remaining_str:>8} {avail:>16} {cooldown_str:>10}")

    print("=" * 72)
    print()


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def _ensure_playwright_data_dir(real_chrome_dir: str, profile_name: str) -> str:
    """Create a persistent non-default data dir with COPIED login files.

    WHY: Chrome blocks --remote-debugging-pipe (used by Playwright) and
    --remote-debugging-port when user_data_dir IS Chrome's actual default
    profile path.  By using a different directory, Chrome sees a "non-default"
    path.  We COPY essential login files (Cookies, Login Data, Local Storage,
    etc.) from the real profile so that existing sessions are available on
    first launch.  Chrome gets its own cache/GPU/shader space, avoiding
    corruption from pkill'd sessions.

    The macOS keychain key ("Chrome Safe Storage") is user-scoped, not
    path-scoped, so cookie decryption works from any data directory.

    The directory is PERSISTENT (not temp) so Chrome can be left running
    between orchestrator runs, preserving session cookies and logins.
    """
    pw_dir = Path.home() / ".chrome-playwright"
    pw_dir.mkdir(parents=True, exist_ok=True)
    pw_dir.chmod(0o700)  # Owner-only access — protects copied session cookies

    profile_dst = pw_dir / profile_name
    profile_src = Path(real_chrome_dir) / profile_name

    # If Default is a stale symlink (from old code), remove it and start fresh
    if profile_dst.is_symlink():
        log.info("Removing stale profile symlink — switching to copy-based approach")
        profile_dst.unlink()

    profile_dst.mkdir(parents=True, exist_ok=True)

    # Essential login/auth files to copy from the real Chrome profile.
    _LOGIN_FILES = [
        "Cookies",
        "Cookies-journal",
        # "Login Data" intentionally excluded — contains saved passwords; not
        # needed for Playwright session reuse (session cookies are sufficient).
        # "Login Data-journal" excluded for the same reason.
        "Web Data",
        "Web Data-journal",
        "Extension Cookies",
        "Extension Cookies-journal",
        "Preferences",
        "Secure Preferences",
    ]
    _LOGIN_DIRS = [
        "Local Storage",
        "Session Storage",
        "IndexedDB",
    ]

    for fname in _LOGIN_FILES:
        src = profile_src / fname
        dst = profile_dst / fname
        if not src.exists():
            continue
        if fname.startswith("Cookies"):
            if not dst.exists() or os.path.getmtime(str(src)) > os.path.getmtime(str(dst)):
                shutil.copy2(str(src), str(dst))
                log.debug(f"Copied {fname} from real profile")
        else:
            if not dst.exists():
                shutil.copy2(str(src), str(dst))
                log.debug(f"Copied {fname} from real profile (first run)")

    for dname in _LOGIN_DIRS:
        src = profile_src / dname
        dst = profile_dst / dname
        if src.is_dir() and not dst.exists():
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
            log.debug(f"Copied {dname}/ from real profile (first run)")

    ls_src = os.path.join(real_chrome_dir, "Local State")
    ls_dst = pw_dir / "Local State"
    if os.path.exists(ls_src):
        if not ls_dst.exists() or os.path.getmtime(ls_src) > os.path.getmtime(str(ls_dst)):
            shutil.copy2(ls_src, str(ls_dst))

    return str(pw_dir)


# ---------------------------------------------------------------------------
# Tab state persistence — tracks open browser tabs across runs
# ---------------------------------------------------------------------------

_TAB_STATE_FILE = Path.home() / ".chrome-playwright" / "tab-state.json"


def _load_tab_state() -> dict:
    """Load the persisted mapping of platform_name → last known tab URL."""
    if _TAB_STATE_FILE.exists():
        try:
            return json.loads(_TAB_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_tab_state(tab_state: dict) -> None:
    """Persist the mapping of platform_name → current tab URL."""
    _TAB_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TAB_STATE_FILE.write_text(
        json.dumps(tab_state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


async def _find_existing_tab(context, platform_name: str):
    """Search open Chrome tabs for a page belonging to this platform.

    Matches by PLATFORM_URL_DOMAINS substring in the page URL.
    Returns the Page if found, None otherwise.
    """
    domain = PLATFORM_URL_DOMAINS.get(platform_name, "")
    if not domain:
        return None
    for page in context.pages:
        if domain in page.url:
            return page
    return None


async def orchestrate(args: argparse.Namespace, effective_output_dir: str) -> list[dict]:
    """Launch Chrome, run all platforms in parallel, return results."""
    full_prompt, condensed_prompt, prompt_sigs = load_prompts(args)

    # Determine which platforms to run
    if args.platforms == "all":
        platform_names = list(ALL_PLATFORMS.keys())
    else:
        platform_names = [p.strip() for p in args.platforms.split(",")]
        for name in platform_names:
            if name not in ALL_PLATFORMS:
                log.error(f"Unknown platform: {name}. Available: {', '.join(ALL_PLATFORMS)}")
                sys.exit(1)

    # Create output directory
    output_dir = Path(effective_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Detect Chrome paths
    chrome_exe = detect_chrome_executable()
    user_data = detect_chrome_user_data_dir()
    log.info(f"Chrome: {chrome_exe}")
    log.info(f"Profile: {user_data}/{args.chrome_profile}")

    # Fix "Restore pages?" dialog — reset exit_type to Normal before launch.
    prefs_path = Path(user_data) / args.chrome_profile / "Preferences"
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
            if prefs.get("profile", {}).get("exit_type") != "Normal":
                prefs.setdefault("profile", {})["exit_type"] = "Normal"
                prefs_path.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
                log.info("Fixed Chrome exit_type → Normal (prevents 'Restore pages?' dialog)")
        except Exception as exc:
            log.warning(f"Could not fix Chrome exit_type: {exc}")

    # Create persistent non-default data dir with copied profile
    pw_data_dir = _ensure_playwright_data_dir(user_data, args.chrome_profile)
    log.info(f"Playwright data dir: {pw_data_dir}")

    # Dynamic global timeout: max individual platform timeout + total stagger + 60s buffer.
    # This ensures even the last-staggered platform gets its full per-platform timeout.
    max_plat_timeout = max(
        (TIMEOUTS[n].deep if args.mode == "DEEP" else TIMEOUTS[n].regular)
        for n in platform_names
        if n in TIMEOUTS
    ) if any(n in TIMEOUTS for n in platform_names) else (
        GLOBAL_TIMEOUT_DEEP if args.mode == "DEEP" else GLOBAL_TIMEOUT_REGULAR
    )
    total_stagger = (len(platform_names) - 1) * args.stagger_delay
    global_timeout = max_plat_timeout + total_stagger + 60
    log.info(f"Mode: {args.mode} | Global timeout: {global_timeout}s "
             f"(max_plat={max_plat_timeout}s + stagger={total_stagger}s + 60s) | "
             f"Platforms: {len(platform_names)}")

    chrome_proc = None

    async with async_playwright() as p:
        context = None
        browser = None

        # Step 1: try CDP connect (reuse running Chrome)
        if not args.fresh:
            try:
                browser = await p.chromium.connect_over_cdp(
                    f"http://localhost:{CDP_PORT}",
                    timeout=5000,
                )
                context = browser.contexts[0]
                log.info(f"Connected to existing Chrome via CDP (port {CDP_PORT}) — logins preserved")
            except Exception as exc:
                log.info(f"No running Chrome on port {CDP_PORT} ({type(exc).__name__}), will launch new")
                browser = None
        else:
            log.info("--fresh flag: skipping CDP connect, launching new Chrome")

        # Step 2: launch Chrome via subprocess if connect failed
        if context is None:
            chrome_args = [
                chrome_exe,
                f"--user-data-dir={pw_data_dir}",
                f"--profile-directory={args.chrome_profile}",
                "--remote-debugging-host=127.0.0.1",  # Bind CDP to loopback only
                f"--remote-debugging-port={CDP_PORT}",
                "--no-first-run",
                "--hide-crash-restore-bubble",
                "--disable-infobars",
                "--no-default-browser-check",
                "--disable-search-engine-choice-screen",
                "about:blank",
            ]
            if args.headless:
                chrome_args.insert(1, "--headless=new")

            log.info("Launching Chrome via subprocess...")
            chrome_proc = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            # Wait for CDP port to become available (max 30s)
            import urllib.request
            cdp_url = f"http://localhost:{CDP_PORT}/json/version"
            for attempt in range(60):
                await asyncio.sleep(0.5)
                try:
                    urllib.request.urlopen(cdp_url, timeout=2)
                    break
                except Exception:
                    if chrome_proc.poll() is not None:
                        stderr = chrome_proc.stderr.read().decode() if chrome_proc.stderr else ""
                        raise RuntimeError(f"Chrome exited prematurely (code {chrome_proc.returncode}): {stderr}")
            else:
                raise RuntimeError(f"Chrome did not start CDP on port {CDP_PORT} within 30s")

            # Connect Playwright via CDP
            browser = await p.chromium.connect_over_cdp(
                f"http://localhost:{CDP_PORT}",
                timeout=10000,
            )
            context = browser.contexts[0]
            log.info(f"Launched Chrome (pid {chrome_proc.pid}) and connected via CDP")

        # Create Agent fallback manager (uses CDP to share the Chrome instance)
        agent_mgr = AgentFallbackManager(
            cdp_url=f"http://localhost:{CDP_PORT}",
            output_dir=str(output_dir),
            max_steps=AGENT_MAX_STEPS,
        )

        # Initialize rate limiter
        limiter = RateLimiter(tier=args.tier)
        limiter.load_state()

        # Pre-flight: WARN ONLY — never skip platforms based on rate budget.
        # Platforms are only excluded during the run itself if they:
        #   • Show a sign-in page (STATUS_NEEDS_LOGIN)
        #   • Are unreachable (network error → STATUS_FAILED)
        #   • Report actual quota exhaustion on-page (STATUS_RATE_LIMITED)
        if not args.skip_rate_check:
            for name in platform_names:
                check = limiter.preflight_check(name, args.mode)
                if check.allowed:
                    log.info(
                        f"[{PLATFORM_DISPLAY_NAMES.get(name, name)}] "
                        f"Budget OK — {check.budget_remaining}/{check.budget_total} remaining"
                    )
                else:
                    log.warning(
                        f"[{PLATFORM_DISPLAY_NAMES.get(name, name)}] "
                        f"Budget warning: {check.reason} — proceeding anyway"
                    )
        else:
            log.info("Rate limit checks bypassed (--skip-rate-check)")

        # All requested platforms proceed regardless of budget status
        allowed_platforms = list(platform_names)
        log.info(f"Browser ready — launching {len(allowed_platforms)} platforms")

        # Find existing tabs for each platform (tab reuse across runs)
        if args.followup:
            log.info("Follow-up mode: reusing existing conversations in open tabs")
        else:
            log.info("New topic mode: reusing tabs but starting new conversations")

        existing_tabs: dict[str, object] = {}
        for name in allowed_platforms:
            page = await _find_existing_tab(context, name)
            if page is not None:
                existing_tabs[name] = page
                log.info(
                    f"[{PLATFORM_DISPLAY_NAMES.get(name, name)}] "
                    f"Found existing tab: {page.url[:60]}"
                )

        # Get staggered launch order
        launch_order = limiter.get_staggered_order(
            allowed_platforms, args.mode, stagger_delay=args.stagger_delay,
        )

        # Launch all platforms with stagger delays
        launched_names = []
        async_tasks = []
        for name, delay in launch_order:
            launched_names.append(name)
            task = asyncio.create_task(
                _staggered_run(
                    name, delay, context, full_prompt, condensed_prompt,
                    prompt_sigs, args.mode, str(output_dir), agent_mgr, limiter,
                    existing_page=existing_tabs.get(name),
                    followup=args.followup and (name in existing_tabs),
                ),
                name=name,
            )
            async_tasks.append(task)

        # Wait for ALL platforms to complete (each self-times-out via per-platform timeout).
        # The outer timeout is a hard ceiling for truly stuck tasks.
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*async_tasks, return_exceptions=True),
                timeout=global_timeout,
            )
        except asyncio.TimeoutError:
            log.warning(f"Hard ceiling ({global_timeout}s) reached — cancelling stuck tasks")
            for task in async_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*async_tasks, return_exceptions=True)
            results = []
            for task in async_tasks:
                if task.done() and not task.cancelled():
                    exc = task.exception()
                    results.append(exc if exc else task.result())
                else:
                    results.append(asyncio.TimeoutError("Global ceiling exceeded"))

        # Save updated tab URLs to state file
        new_tab_state: dict[str, str] = {}
        for name in launched_names:
            page = await _find_existing_tab(context, name)
            if page is not None:
                new_tab_state[name] = page.url
        _save_tab_state(new_tab_state)

        # Convert exceptions to error dicts
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                name = launched_names[i]
                status = STATUS_TIMEOUT if isinstance(r, (asyncio.TimeoutError, asyncio.CancelledError)) else STATUS_FAILED
                final_results.append({
                    "platform": name,
                    "display_name": PLATFORM_DISPLAY_NAMES.get(name, name),
                    "status": status,
                    "chars": 0,
                    "file": "",
                    "mode_used": "",
                    "error": str(r),
                    "duration_s": 0,
                })
            else:
                final_results.append(r)

        # ---------------------------------------------------------------
        # Login retry — platforms that needed sign-in get a second chance.
        # The other platforms have already completed; the user is notified
        # and given 90s to sign in before the retry runs.
        # ---------------------------------------------------------------
        login_pending = [
            (i, r) for i, r in enumerate(final_results)
            if r.get("status") == STATUS_NEEDS_LOGIN
        ]
        if login_pending:
            print("\n" + "=" * 72)
            print("  🔑  SIGN-IN REQUIRED — the following platforms need you to log in:")
            for _, r in login_pending:
                url = PLATFORM_URLS.get(r["platform"], "")
                print(f"     {r['display_name']:20s}  {url}")
            print()
            print("  All other platforms have already been collected.")
            print("  Sign in to the platforms above in Chrome, then wait.")
            print("  Retrying automatically in 90 seconds...")
            print("=" * 72)
            for remaining in range(90, 0, -10):
                log.info(f"  Sign-in retry countdown: {remaining}s remaining...")
                await asyncio.sleep(10)
            log.info("Retrying sign-in-needed platforms...")
            for idx, r in login_pending:
                name = r["platform"]
                log.info(f"[{PLATFORM_DISPLAY_NAMES.get(name, name)}] Retrying after sign-in wait...")
                retry = await run_single_platform(
                    name, context, full_prompt, condensed_prompt,
                    prompt_sigs, args.mode, str(output_dir), agent_mgr,
                    existing_page=None, followup=False,
                )
                limiter.record_usage(name, args.mode, retry["status"], retry.get("duration_s", 0))
                final_results[idx] = retry

        # ---------------------------------------------------------------
        # Platform-level browser-use fallback — when all Playwright steps
        # failed for a platform, attempt a complete agent-driven run.
        # Only fires if ANTHROPIC_API_KEY (or GOOGLE_API_KEY) is set.
        # ---------------------------------------------------------------
        if agent_mgr.enabled:
            failed_idxs = [
                (i, r) for i, r in enumerate(final_results)
                if r.get("status") == STATUS_FAILED
            ]
            if failed_idxs:
                log.info(
                    f"Attempting full browser-use fallback for "
                    f"{len(failed_idxs)} failed platform(s)..."
                )
            for idx, r in failed_idxs:
                url = PLATFORM_URLS.get(r["platform"], "")
                if not url:
                    continue
                fallback = await agent_mgr.full_platform_run(
                    platform_name=r["platform"],
                    platform_url=url,
                    display_name=r["display_name"],
                    prompt=full_prompt,
                    mode=args.mode,
                    output_dir=str(output_dir),
                )
                if fallback:
                    final_results[idx] = fallback

        # Disconnect Playwright from Chrome (does NOT close Chrome)
        try:
            async with asyncio.timeout(10):
                await browser.close()
        except (asyncio.TimeoutError, Exception):
            log.debug("Browser disconnect timed out — continuing")
        log.info(
            "Chrome left running (logins preserved for next run). "
            "Use --fresh to force a new instance, or quit Chrome manually."
        )

    return final_results


# ---------------------------------------------------------------------------
# Status output
# ---------------------------------------------------------------------------

def write_status(results: list[dict], output_dir: str, mode: str) -> None:
    """Write status.json and print summary table."""
    status_path = Path(output_dir) / "status.json"
    status_data = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "platforms": results,
    }
    status_path.write_text(json.dumps(status_data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"Status written to {status_path}")

    # Print summary table
    print("\n" + "=" * 80)
    print(f"  ORCHESTRATION COMPLETE — {mode} mode")
    print("=" * 80)
    print(f"  {'Platform':<20} {'Status':<12} {'Chars':>8}  {'Time':>8}  Notes")
    print("-" * 80)
    for r in results:
        icon = STATUS_ICONS.get(r["status"], "?")
        name = r["display_name"]
        status = f"{icon} {r['status']}"
        chars = f"{r['chars']:,}" if r["chars"] else "-"
        time_s = f"{r['duration_s']:.0f}s" if r["duration_s"] else "-"
        notes = r.get("error", "") or r.get("mode_used", "")
        print(f"  {name:<20} {status:<12} {chars:>8}  {time_s:>8}  {notes}")
    print("=" * 80)

    complete = sum(1 for r in results if r["status"] == "complete")
    total = len(results)
    print(f"\n  {complete}/{total} platforms completed successfully.")
    print(f"  Raw responses saved to: {output_dir}/")
    print(f"  Status file: {status_path}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _resolve_output_dir(args: argparse.Namespace) -> str:
    """Resolve the effective output directory.

    If --task-name is supplied, output goes to <project-root>/reports/<task-name>/.
    Otherwise falls back to --output-dir (default: <project-root>/reports/).
    """
    if args.task_name:
        # Sanitise task-name: keep letters, numbers, hyphens, underscores, dots, spaces
        safe = "".join(c if c.isalnum() or c in "-_. " else "-" for c in args.task_name).strip()
        return str(_PROJECT_ROOT / "reports" / safe)
    # Validate --output-dir is within the project root to prevent path traversal
    resolved = Path(args.output_dir).resolve()
    if not str(resolved).startswith(str(_PROJECT_ROOT)):
        log.error(
            f"--output-dir must be within the project root ({_PROJECT_ROOT}). Got: {resolved}"
        )
        sys.exit(1)
    return args.output_dir


def main():
    args = parse_args()

    # Resolve effective output dir (task-name overrides output-dir)
    effective_output_dir = _resolve_output_dir(args)

    # Budget-only mode: print summary and exit
    if args.budget:
        show_budget(args)
        sys.exit(0)

    results = asyncio.run(orchestrate(args, effective_output_dir))
    write_status(results, effective_output_dir, args.mode)

    # Collate all raw responses into a single archive .md
    from collate_responses import collate  # noqa: E402 (imported late — after bootstrap)
    collate(effective_output_dir, args.task_name or Path(effective_output_dir).name)

    # Exit with non-zero if no platforms completed
    complete = sum(1 for r in results if r["status"] in ("complete", "partial"))
    sys.exit(0 if complete > 0 else 1)


if __name__ == "__main__":
    main()
