"""CLI entry point for the Multi-AI Orchestrator Engine."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_ENGINE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _ENGINE_DIR.parent.parent.parent
_DEFAULT_OUTPUT_DIR = str(_PROJECT_ROOT / "reports")

sys.path.insert(0, str(_ENGINE_DIR))

# Bootstrap env and venv before any other imports
from engine_setup import _load_dotenv, _ensure_venv, _ensure_dependencies  # noqa: E402
_load_dotenv()
_ensure_venv()
_ensure_dependencies()

from config import STAGGER_DELAY  # noqa: E402
from prompt_loader import load_prompts  # noqa: E402  # re-exported for callers
from rate_limiter import RateLimiter  # noqa: E402

log = logging.getLogger("orchestrator")


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
    p.add_argument("--chrome-profile", default="MultAI",
                   help="Chrome profile directory name (default: MultAI). "
                        "Using 'Default' is discouraged — it grants access to your primary browser profile.")
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


def _sanitise_chrome_profile(profile: str) -> str:
    """Sanitise the Chrome profile name: allow alphanumeric, hyphen, underscore, space."""
    return "".join(c if c.isalnum() or c in "-_ " else "-" for c in profile).strip() or "MultAI"


def _resolve_output_dir(args: argparse.Namespace) -> str:
    """Resolve the effective output directory."""
    if args.task_name:
        safe = "".join(c if c.isalnum() or c in "-_. " else "-" for c in args.task_name).strip()
        return str(_PROJECT_ROOT / "reports" / safe)
    resolved = Path(args.output_dir).resolve()
    try:
        resolved.relative_to(_PROJECT_ROOT.resolve())
    except ValueError:
        log.error(
            f"--output-dir must be within the project root ({_PROJECT_ROOT}). Got: {resolved}"
        )
        sys.exit(1)
    return str(resolved)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    args = parse_args()
    args.chrome_profile = _sanitise_chrome_profile(args.chrome_profile)
    effective_output_dir = _resolve_output_dir(args)

    if args.chrome_profile == "Default":
        log.warning(
            "Running with Chrome profile 'Default' (your primary profile). "
            "For better isolation, use --chrome-profile MultAI to create a dedicated profile."
        )

    if args.budget:
        show_budget(args)
        sys.exit(0)

    # Late import to avoid circular dependency at module load time
    from orchestrator import orchestrate, write_status  # noqa: E402

    results = asyncio.run(orchestrate(args, effective_output_dir))
    write_status(results, effective_output_dir, args.mode)

    from collate_responses import collate  # noqa: E402
    collate(effective_output_dir, args.task_name or Path(effective_output_dir).name)

    if args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if prompt_path.exists() and str(prompt_path).startswith("/tmp/"):
            try:
                prompt_path.unlink()
                log.debug(f"Cleaned up temp prompt file: {prompt_path}")
            except OSError:
                pass

    complete = sum(1 for r in results if r["status"] in ("complete", "partial"))
    sys.exit(0 if complete > 0 else 1)


if __name__ == "__main__":
    main()
