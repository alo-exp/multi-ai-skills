"""Shared test fixtures and sys.modules stubs for platform unit tests."""

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ENGINE_DIR = str(Path(__file__).resolve().parent.parent)
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


def install_stubs(platform_name, platform_url):
    """Install minimal stubs for all heavy imports so platform modules load cleanly."""
    # playwright
    if "playwright" not in sys.modules:
        pw = types.ModuleType("playwright")
        pw_async = types.ModuleType("playwright.async_api")
        pw_async.Page = object
        pw.async_api = pw_async
        sys.modules["playwright"] = pw
        sys.modules["playwright.async_api"] = pw_async

    # config
    config = types.ModuleType("config")
    config.PLATFORM_URLS = {platform_name: platform_url}
    config.PLATFORM_DISPLAY_NAMES = {platform_name: platform_name.capitalize()}
    config.INJECTION_METHODS = {platform_name: "execCommand"}
    config.POLL_INTERVAL = 0
    config.TIMEOUTS = {}
    config.STATUS_COMPLETE = "complete"
    config.STATUS_FAILED = "failed"
    config.STATUS_NEEDS_LOGIN = "needs_login"
    config.STATUS_PARTIAL = "partial"
    config.STATUS_RATE_LIMITED = "rate_limited"
    config.STATUS_TIMEOUT = "timeout"
    sys.modules["config"] = config

    # prompt_echo
    pe = types.ModuleType("prompt_echo")
    pe.is_prompt_echo = lambda text, sigs: False
    pe.auto_extract_prompt_sigs = lambda text: []
    sys.modules["prompt_echo"] = pe

    # platforms package — point __path__ at the real directory so submodules load
    import os
    platforms_path = os.path.join(ENGINE_DIR, "platforms")
    pkg = types.ModuleType("platforms")
    pkg.__path__ = [platforms_path]
    pkg.__package__ = "platforms"
    sys.modules["platforms"] = pkg

    return config
