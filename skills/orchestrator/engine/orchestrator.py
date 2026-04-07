#!/usr/bin/env python3
"""Multi-AI Orchestrator Engine — v0.2.26040635 Alpha

Usage:
    python3 orchestrator.py --prompt-file /tmp/prompt.md --mode REGULAR
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path

_ENGINE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _ENGINE_DIR.parent.parent.parent

sys.path.insert(0, str(_ENGINE_DIR))

from engine_setup import _load_dotenv, _ensure_venv, _ensure_dependencies  # noqa: E402
_load_dotenv()
_ensure_venv()
_ensure_dependencies()

from playwright.async_api import async_playwright, BrowserContext  # noqa: E402

from agent_fallback import AgentFallbackManager  # noqa: E402
from config import (  # noqa: E402
    AGENT_MAX_STEPS, CDP_PORT, DEEP_MODE, GLOBAL_TIMEOUT_DEEP, GLOBAL_TIMEOUT_REGULAR,
    PLATFORM_DISPLAY_NAMES, PLATFORM_URLS, REGULAR_MODE,
    STATUS_FAILED, STATUS_NEEDS_LOGIN, STATUS_TIMEOUT, TIMEOUTS,
    detect_chrome_executable, detect_chrome_user_data_dir,
)
from platforms import ALL_PLATFORMS  # noqa: E402
from prompt_loader import load_prompts  # noqa: E402
from rate_limiter import RateLimiter  # noqa: E402
from retry_handler import handle_login_retries, handle_agent_fallbacks  # noqa: E402
from status_writer import write_status  # noqa: E402
from tab_manager import _ensure_playwright_data_dir, _find_existing_tab, _save_tab_state  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("orchestrator")


async def run_single_platform(
    platform_name: str, context: BrowserContext,
    full_prompt: str, condensed_prompt: str, prompt_sigs: list[str],
    mode: str, output_dir: str, agent_manager=None, existing_page=None, followup: bool = False,
) -> dict:
    """Find or create a page, instantiate the platform class, and run it."""
    cls = ALL_PLATFORMS[platform_name]
    platform = cls()
    platform.agent_manager = agent_manager
    platform.prompt_sigs = prompt_sigs

    mode_cfg_map = DEEP_MODE if mode == "DEEP" else REGULAR_MODE
    mode_cfg = mode_cfg_map.get(platform_name)
    if mode_cfg and mode_cfg.use_condensed and condensed_prompt and condensed_prompt != full_prompt:
        prompt = condensed_prompt
        log.info(f"[{platform_name}] Using condensed prompt ({len(condensed_prompt)} vs {len(full_prompt)} chars)")
    else:
        prompt = full_prompt

    page = existing_page if existing_page is not None else await context.new_page()
    log.info(f"[{PLATFORM_DISPLAY_NAMES.get(platform_name, platform_name)}] Tab: {'reused' if existing_page else 'new'}")

    try:
        result = await platform.run(page, prompt, mode, output_dir, followup=followup)
        return {
            "platform": result.platform, "display_name": result.display_name,
            "status": result.status, "chars": result.chars, "file": result.file,
            "mode_used": result.mode_used, "error": result.error,
            "duration_s": round(result.duration_s, 1),
        }
    except Exception as exc:
        log.exception(f"[{platform.display_name}] Unhandled error: {exc}")
        return {
            "platform": platform_name, "display_name": platform.display_name,
            "status": STATUS_FAILED, "chars": 0, "file": "", "mode_used": "",
            "error": str(exc), "duration_s": 0,
        }


async def _staggered_run(
    platform_name: str, delay_seconds: float, context: BrowserContext,
    full_prompt: str, condensed_prompt: str, prompt_sigs: list[str],
    mode: str, output_dir: str, agent_manager, limiter: RateLimiter,
    existing_page=None, followup: bool = False,
) -> dict:
    if delay_seconds > 0:
        log.info(f"[{PLATFORM_DISPLAY_NAMES.get(platform_name, platform_name)}] Stagger delay: {delay_seconds:.0f}s")
        await asyncio.sleep(delay_seconds)
    result = await run_single_platform(
        platform_name, context, full_prompt, condensed_prompt, prompt_sigs,
        mode, output_dir, agent_manager, existing_page=existing_page, followup=followup,
    )
    limiter.record_usage(platform=platform_name, mode=mode, status=result["status"], duration_s=result.get("duration_s", 0))
    return result


async def _launch_chrome(p, args, pw_data_dir: str, chrome_exe: str):
    """Connect to existing Chrome or launch a new instance. Returns (browser, context, proc)."""
    if not args.fresh:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}", timeout=5000)
            context = browser.contexts[0]
            log.info(f"Connected to existing Chrome via CDP (port {CDP_PORT})")
            if sys.platform == "darwin" and not args.headless:
                subprocess.Popen(["osascript", "-e", 'tell application "Google Chrome" to set miniaturized of every window to true'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return browser, context, None
        except Exception as exc:
            log.info(f"No running Chrome on port {CDP_PORT} ({type(exc).__name__}), launching new")

    chrome_args = [
        chrome_exe, f"--user-data-dir={pw_data_dir}", f"--profile-directory={args.chrome_profile}",
        "--remote-debugging-host=127.0.0.1", f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run", "--hide-crash-restore-bubble", "--disable-infobars",
        "--no-default-browser-check", "--disable-search-engine-choice-screen", "about:blank",
    ]
    if args.headless:
        chrome_args.insert(1, "--headless=new")

    chrome_proc = subprocess.Popen(chrome_args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    import urllib.request
    for _ in range(60):
        await asyncio.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
            break
        except Exception:
            if chrome_proc.poll() is not None:
                stderr = chrome_proc.stderr.read().decode() if chrome_proc.stderr else ""
                raise RuntimeError(f"Chrome exited prematurely: {stderr}")
    else:
        raise RuntimeError(f"Chrome did not start CDP on port {CDP_PORT} within 30s")

    browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}", timeout=10000)
    context = browser.contexts[0]
    log.info(f"Launched Chrome (pid {chrome_proc.pid}) and connected via CDP")
    if sys.platform == "darwin" and not args.headless:
        subprocess.Popen(["osascript", "-e", 'tell application "Google Chrome" to set miniaturized of every window to true'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return browser, context, chrome_proc


async def _gather_with_timeout(async_tasks, global_timeout, launched_names):
    """Run tasks with a hard ceiling; cancel and collect results on timeout."""
    try:
        return list(await asyncio.wait_for(asyncio.gather(*async_tasks, return_exceptions=True), timeout=global_timeout))
    except asyncio.TimeoutError:
        log.warning(f"Hard ceiling ({global_timeout}s) reached — cancelling stuck tasks")
        for task in async_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*async_tasks, return_exceptions=True)
        results = []
        for task in async_tasks:
            if task.done() and not task.cancelled():
                try:
                    results.append(task.result())
                except (asyncio.CancelledError, Exception) as exc:
                    results.append(exc)
            else:
                results.append(asyncio.TimeoutError("Global ceiling exceeded"))
        return results


async def _run_all_platforms(context, args, platform_names, full_prompt, condensed_prompt,
                              prompt_sigs, output_dir, agent_mgr, limiter):
    """Launch all platforms with stagger delays, handle retries, return results."""
    existing_tabs: dict[str, object] = {}
    for name in platform_names:
        page = await _find_existing_tab(context, name)
        if page is not None:
            existing_tabs[name] = page
            log.info(f"[{PLATFORM_DISPLAY_NAMES.get(name, name)}] Found existing tab: {page.url[:60]}")

    max_plat_timeout = max(
        (TIMEOUTS[n].deep if args.mode == "DEEP" else TIMEOUTS[n].regular)
        for n in platform_names if n in TIMEOUTS
    ) if any(n in TIMEOUTS for n in platform_names) else (
        GLOBAL_TIMEOUT_DEEP if args.mode == "DEEP" else GLOBAL_TIMEOUT_REGULAR
    )
    global_timeout = max_plat_timeout + (len(platform_names) - 1) * args.stagger_delay + 60

    launch_order = limiter.get_staggered_order(platform_names, args.mode, stagger_delay=args.stagger_delay)
    launched_names, async_tasks = [], []
    for name, delay in launch_order:
        launched_names.append(name)
        async_tasks.append(asyncio.create_task(_staggered_run(
            name, delay, context, full_prompt, condensed_prompt, prompt_sigs,
            args.mode, str(output_dir), agent_mgr, limiter,
            existing_page=existing_tabs.get(name),
            followup=args.followup and (name in existing_tabs),
        ), name=name))

    raw = await _gather_with_timeout(async_tasks, global_timeout, launched_names)

    # Save tab state
    _save_tab_state({
        name: page.url
        for name in launched_names
        if (page := await _find_existing_tab(context, name)) is not None  # type: ignore[assignment]
    })

    # Convert exceptions to error dicts
    final_results = []
    for i, r in enumerate(raw):
        if isinstance(r, Exception):
            name = launched_names[i]
            status = STATUS_TIMEOUT if isinstance(r, (asyncio.TimeoutError, asyncio.CancelledError)) else STATUS_FAILED
            final_results.append({
                "platform": name, "display_name": PLATFORM_DISPLAY_NAMES.get(name, name),
                "status": status, "chars": 0, "file": "", "mode_used": "", "error": str(r), "duration_s": 0,
            })
        else:
            final_results.append(r)

    await handle_login_retries(final_results, context, full_prompt, condensed_prompt,
                                prompt_sigs, args, output_dir, agent_mgr, limiter, run_single_platform)
    await handle_agent_fallbacks(final_results, agent_mgr, full_prompt, args, output_dir)
    return final_results


async def orchestrate(args, effective_output_dir: str) -> list[dict]:
    """Launch Chrome, run all platforms in parallel, return results."""
    full_prompt, condensed_prompt, prompt_sigs = load_prompts(args)

    if args.platforms == "all":
        platform_names = list(ALL_PLATFORMS.keys())
    else:
        platform_names = [p.strip() for p in args.platforms.split(",")]
        for name in platform_names:
            if name not in ALL_PLATFORMS:
                log.error(f"Unknown platform: {name}. Available: {', '.join(ALL_PLATFORMS)}")
                sys.exit(1)

    output_dir = Path(effective_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    chrome_exe = detect_chrome_executable()
    user_data = detect_chrome_user_data_dir()
    log.info(f"Chrome: {chrome_exe} | Profile: {user_data}/{args.chrome_profile}")

    # Fix "Restore pages?" dialog — reset exit_type to Normal before launch
    prefs_path = Path(user_data) / args.chrome_profile / "Preferences"
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
            if prefs.get("profile", {}).get("exit_type") != "Normal":
                prefs.setdefault("profile", {})["exit_type"] = "Normal"
                import tempfile, os as _os
                with tempfile.NamedTemporaryFile('w', dir=prefs_path.parent, delete=False, suffix='.tmp') as _f:
                    _f.write(json.dumps(prefs, indent=2, ensure_ascii=False))
                    _tmp = _f.name
                _os.replace(_tmp, prefs_path)
        except Exception as exc:
            log.warning(f"Could not fix Chrome exit_type: {exc}")

    pw_data_dir = _ensure_playwright_data_dir(user_data, args.chrome_profile)

    async with async_playwright() as p:
        browser, context, _proc = await _launch_chrome(p, args, pw_data_dir, chrome_exe)

        agent_mgr = AgentFallbackManager(
            cdp_url=f"http://localhost:{CDP_PORT}", output_dir=str(output_dir), max_steps=AGENT_MAX_STEPS,
        )
        limiter = RateLimiter(tier=args.tier)
        limiter.load_state()

        if not args.skip_rate_check:
            for name in platform_names:
                check = limiter.preflight_check(name, args.mode)
                if not check.allowed:
                    log.warning(f"[{PLATFORM_DISPLAY_NAMES.get(name, name)}] Budget warning: {check.reason} — proceeding anyway")
        else:
            log.info("Rate limit checks bypassed (--skip-rate-check)")

        final_results = await _run_all_platforms(
            context, args, platform_names, full_prompt, condensed_prompt,
            prompt_sigs, output_dir, agent_mgr, limiter,
        )

        try:
            async with asyncio.timeout(10):
                await browser.close()
        except Exception:
            log.debug("Browser disconnect timed out — continuing")
        log.info("Chrome left running. Use --fresh to force a new instance.")

    return final_results


def main():
    from cli import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()
