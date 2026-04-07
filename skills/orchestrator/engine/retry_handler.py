"""Login-retry and agent-fallback post-processing for orchestration results."""

from __future__ import annotations

import asyncio
import logging

from config import PLATFORM_DISPLAY_NAMES, PLATFORM_URLS, STATUS_FAILED, STATUS_NEEDS_LOGIN

log = logging.getLogger(__name__)


async def handle_login_retries(
    final_results, context, full_prompt, condensed_prompt,
    prompt_sigs, args, output_dir, agent_mgr, limiter, run_single_platform_fn,
) -> None:
    """Wait for user to sign in, then retry STATUS_NEEDS_LOGIN platforms in-place."""
    login_pending = [
        (i, r) for i, r in enumerate(final_results)
        if r.get("status") == STATUS_NEEDS_LOGIN
    ]
    if not login_pending:
        return

    print("\n" + "=" * 72)
    print("  SIGN-IN REQUIRED — the following platforms need you to log in:")
    for _, r in login_pending:
        print(f"     {r['display_name']:20s}  {PLATFORM_URLS.get(r['platform'], '')}")
    print("\n  Retrying automatically in 90 seconds...")
    print("=" * 72)
    for remaining in range(90, 0, -10):
        log.info(f"  Sign-in retry countdown: {remaining}s remaining...")
        await asyncio.sleep(10)

    for idx, r in login_pending:
        name = r["platform"]
        log.info(f"[{PLATFORM_DISPLAY_NAMES.get(name, name)}] Retrying after sign-in wait...")
        retry = await run_single_platform_fn(
            name, context, full_prompt, condensed_prompt,
            prompt_sigs, args.mode, str(output_dir), agent_mgr,
        )
        limiter.record_usage(name, args.mode, retry["status"], retry.get("duration_s", 0))
        final_results[idx] = retry


async def handle_agent_fallbacks(
    final_results, agent_mgr, full_prompt, args, output_dir,
) -> None:
    """Attempt full browser-use agent run for STATUS_FAILED platforms in-place."""
    if not agent_mgr.enabled:
        return
    # NOTE: failed_idxs is captured from results before login-retry runs.
    # A platform that recovers via login-retry will not appear in failed_idxs
    # and will not receive an agent-fallback attempt. This is intentional —
    # a successful login-retry means the platform ran; agent-fallback is for
    # structural failures only.
    failed_idxs = [
        (i, r) for i, r in enumerate(final_results)
        if r.get("status") == STATUS_FAILED
    ]
    if failed_idxs:
        log.info(f"Attempting full browser-use fallback for {len(failed_idxs)} failed platform(s)...")
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
