"""Platform configuration, URLs, timeouts, and mode settings."""

import platform as _platform
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Chrome detection (macOS / Linux / Windows)
# ---------------------------------------------------------------------------

def detect_chrome_executable() -> str:
    system = _platform.system()
    if system == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif system == "Linux":
        for p in ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium-browser"]:
            if Path(p).exists():
                return p
        return "google-chrome"
    elif system == "Windows":
        return r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    return "google-chrome"


# SECURITY NOTE (SENTINEL F-005): For best isolation, run Chrome with a dedicated profile
# (e.g. --chrome-profile MultAI) that contains only AI platform logins. This limits the
# CDP blast radius to AI platform sessions rather than the user's full browsing history.
def detect_chrome_user_data_dir() -> str:
    system = _platform.system()
    home = Path.home()
    if system == "Darwin":
        return str(home / "Library" / "Application Support" / "Google" / "Chrome")
    elif system == "Linux":
        return str(home / ".config" / "google-chrome")
    elif system == "Windows":
        return str(home / "AppData" / "Local" / "Google" / "Chrome" / "User Data")
    return str(home / ".config" / "google-chrome")


# ---------------------------------------------------------------------------
# Platform URLs
# ---------------------------------------------------------------------------

PLATFORM_URLS = {
    "claude_ai":  "https://claude.ai/new",
    "chatgpt":    "https://chat.openai.com",
    "copilot":    "https://copilot.microsoft.com",
    "perplexity": "https://www.perplexity.ai",
    "grok":       "https://grok.com",
    "deepseek":   "https://chat.deepseek.com",
    "gemini":     "https://gemini.google.com/app",
}

PLATFORM_DISPLAY_NAMES = {
    "claude_ai":  "Claude.ai",
    "chatgpt":    "ChatGPT",
    "copilot":    "Microsoft Copilot",
    "perplexity": "Perplexity",
    "grok":       "Grok",
    "deepseek":   "DeepSeek",
    "gemini":     "Google Gemini",
}

# URL domain fragments used to identify an existing browser tab for each platform.
# Matched against page.url via substring search.
PLATFORM_URL_DOMAINS = {
    "claude_ai":  "claude.ai",
    "chatgpt":    "openai.com",
    "copilot":    "copilot.microsoft.com",
    "perplexity": "perplexity.ai",
    "grok":       "grok.com",
    "deepseek":   "chat.deepseek.com",
    "gemini":     "gemini.google.com",
}


# ---------------------------------------------------------------------------
# Timeouts (seconds)
# ---------------------------------------------------------------------------

@dataclass
class TimeoutConfig:
    """Per-platform timeout ceilings."""
    deep: int = 600       # Max wait in DEEP mode (default: 10 min)
    regular: int = 600    # Max wait in REGULAR mode (default: 10 min)


TIMEOUTS = {
    "claude_ai":  TimeoutConfig(deep=3600, regular=900),   # 60 min / 15 min
    "chatgpt":    TimeoutConfig(deep=3000, regular=600),   # 50 min / 10 min
    "copilot":    TimeoutConfig(deep=3000, regular=600),
    "perplexity": TimeoutConfig(deep=600,  regular=600),   # 10 min / 10 min
    "grok":       TimeoutConfig(deep=600,  regular=600),
    "deepseek":   TimeoutConfig(deep=600,  regular=600),
    "gemini":     TimeoutConfig(deep=2400, regular=600),   # 40 min / 10 min
}

GLOBAL_TIMEOUT_DEEP = 3000       # 50-minute hard ceiling
GLOBAL_TIMEOUT_REGULAR = 900     # 15-minute hard ceiling

POLL_INTERVAL = 10               # Seconds between completion checks

# Agent fallback (browser-use)
CDP_PORT = 9222                  # Chrome DevTools Protocol port for browser-use
AGENT_MAX_STEPS = 5              # Maximum Agent steps per fallback invocation
AGENT_MODEL_ANTHROPIC = "claude-sonnet-4-6"   # Model for Anthropic-backed agent fallback
AGENT_MODEL_GOOGLE = "gemini-2.0-flash"       # Model for Google-backed agent fallback


# ---------------------------------------------------------------------------
# Mode configuration
# ---------------------------------------------------------------------------

@dataclass
class ModeConfig:
    """What model/mode to set on each platform."""
    model: str = ""
    deep_research: bool = False
    thinking: bool = False
    search: bool = False
    use_condensed: bool = False   # Use condensed prompt when one is provided
    notes: str = ""


# DEEP mode configuration per platform
DEEP_MODE = {
    "claude_ai":  ModeConfig(model="Sonnet", deep_research=True, notes="Research + Web search"),
    "chatgpt":    ModeConfig(deep_research=True, notes="Deep research from + picker"),
    "copilot":    ModeConfig(thinking=True, deep_research=True, notes="Think deeper + Start deep research"),
    "perplexity": ModeConfig(model="Sonar", deep_research=True, notes="Deep Research toggle if visible"),
    "grok":       ModeConfig(thinking=True, search=True, use_condensed=True, notes="DeepThink + Search"),
    "deepseek":   ModeConfig(thinking=True, search=True, notes="DeepThink + Search"),
    "gemini":     ModeConfig(model="Thinking", deep_research=True, notes="Thinking + Deep Research"),
}

# REGULAR mode configuration per platform
REGULAR_MODE = {
    "claude_ai":  ModeConfig(model="Sonnet", notes="Sonnet, regular chat"),
    "chatgpt":    ModeConfig(notes="Regular chat, reasoning model preferred"),
    "copilot":    ModeConfig(thinking=True, notes="Think deeper only"),
    "perplexity": ModeConfig(model="Sonar", notes="Sonar, no Deep Research"),
    "grok":       ModeConfig(thinking=True, search=True, use_condensed=True, notes="DeepThink + Search"),
    "deepseek":   ModeConfig(thinking=True, search=True, notes="DeepThink + Search"),
    "gemini":     ModeConfig(model="Thinking", notes="Thinking, no Deep Research"),
}


# ---------------------------------------------------------------------------
# Injection method per platform
# ---------------------------------------------------------------------------

# "execCommand"   → contenteditable div — use document.execCommand('insertText')
# "physical_type" → React <textarea> — use page.type() for physical typing
# "fill"          → React <textarea> — use page.fill() (triggers React state)
INJECTION_METHODS = {
    "claude_ai":  "execCommand",
    "chatgpt":    "execCommand",
    "copilot":    "fill",            # Uses textarea, not contenteditable
    "perplexity": "execCommand",
    "grok":       "execCommand",     # Uses ProseMirror contenteditable div
    "deepseek":   "fill",
    "gemini":     "execCommand",
}

# ---------------------------------------------------------------------------
# Terminal status codes
# ---------------------------------------------------------------------------

STATUS_COMPLETE = "complete"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_NEEDS_LOGIN = "needs_login"
STATUS_LOST = "lost"

STATUS_ICONS = {
    STATUS_COMPLETE:     "✅",
    STATUS_PARTIAL:      "⚠️",
    STATUS_FAILED:       "❌",
    STATUS_TIMEOUT:      "❌",
    STATUS_RATE_LIMITED: "❌",
    STATUS_NEEDS_LOGIN:  "🔑",
    STATUS_LOST:         "❌",
}


# ---------------------------------------------------------------------------
# Rate limiting — per-platform budgets (web client, March 2026)
# ---------------------------------------------------------------------------

@dataclass
class RateLimitConfig:
    """Rate limit budget for a single platform/tier/mode combination."""
    max_requests: int          # Max requests allowed in the rolling window
    window_seconds: int        # Rolling window duration in seconds
    cooldown_seconds: int      # Minimum seconds between consecutive requests
    daily_cap: int = 0         # Hard daily cap (0 = no daily cap, use window only)
    notes: str = ""            # Human-readable description


# Structure: RATE_LIMITS[platform_name][tier][mode]
RATE_LIMITS: dict[str, dict[str, dict[str, RateLimitConfig]]] = {
    "claude_ai": {
        "free": {
            "REGULAR": RateLimitConfig(12, 18000, 300, notes="~15-40/5hrs, conservative at 12"),
            "DEEP":    RateLimitConfig(5,  18000, 600, notes="Extended thinking, token-heavy"),
        },
        "paid": {
            "REGULAR": RateLimitConfig(40, 18000, 120, notes="~45-900/5hrs, conservative at 40"),
            "DEEP":    RateLimitConfig(15, 18000, 300, notes="Token-based, 5-10x cost per msg"),
        },
    },
    "chatgpt": {
        "free": {
            "REGULAR": RateLimitConfig(8,  18000, 300, notes="~10/5hrs rolling"),
            "DEEP":    RateLimitConfig(3,  604800, 1800, daily_cap=5, notes="5/month free"),
        },
        "paid": {
            "REGULAR": RateLimitConfig(80, 10800, 60,  notes="160/3hrs Plus, conservative at 80"),
            "DEEP":    RateLimitConfig(8,  604800, 600, daily_cap=25, notes="10-25/month Plus"),
        },
    },
    "copilot": {
        "free": {
            "REGULAR": RateLimitConfig(5,  86400, 600, daily_cap=30, notes="5-30/conv, ~50/day"),
            "DEEP":    RateLimitConfig(3,  86400, 900, daily_cap=10, notes="Limited deep research"),
        },
        "paid": {
            "REGULAR": RateLimitConfig(15, 86400, 300, daily_cap=100, notes="Copilot Pro higher limits"),
            "DEEP":    RateLimitConfig(10, 86400, 600, daily_cap=30, notes="Paid deep research"),
        },
    },
    "perplexity": {
        "free": {
            "REGULAR": RateLimitConfig(50, 86400, 30,  notes="Unlimited basic, conservative cap"),
            "DEEP":    RateLimitConfig(3,  86400, 1800, daily_cap=3, notes="3 Pro/day free"),
        },
        "paid": {
            "REGULAR": RateLimitConfig(200, 86400, 10,  notes="Unlimited Pro searches"),
            "DEEP":    RateLimitConfig(15,  86400, 600, daily_cap=20, notes="20/day Pro"),
        },
    },
    "grok": {
        "free": {
            "REGULAR": RateLimitConfig(8,  7200, 300, notes="10-15/2hrs, conservative at 8"),
            "DEEP":    RateLimitConfig(2,  86400, 3600, daily_cap=3, notes="2-5/day free"),
        },
        "paid": {
            "REGULAR": RateLimitConfig(100, 7200, 30,  notes="SuperGrok ~unlimited"),
            "DEEP":    RateLimitConfig(20,  7200, 120, notes="~30/2hrs SuperGrok"),
        },
    },
    "deepseek": {
        "free": {
            "REGULAR": RateLimitConfig(8,  86400, 60,  notes="'Unlimited' but throttle after 8-10 rapid"),
            "DEEP":    RateLimitConfig(5,  86400, 120, notes="No separate deep tier"),
        },
        "paid": {  # DeepSeek has no paid web tier — alias to free
            "REGULAR": RateLimitConfig(8,  86400, 60,  notes="No paid tier — same as free"),
            "DEEP":    RateLimitConfig(5,  86400, 120, notes="No paid tier — same as free"),
        },
    },
    "gemini": {
        "free": {
            "REGULAR": RateLimitConfig(5,  86400, 900, daily_cap=5, notes="5/day Pro model free"),
            "DEEP":    RateLimitConfig(3,  2592000, 3600, daily_cap=5, notes="5/month free"),
        },
        "paid": {
            "REGULAR": RateLimitConfig(80, 86400, 60,  daily_cap=100, notes="100-500/day paid"),
            "DEEP":    RateLimitConfig(15, 86400, 600, daily_cap=20, notes="20-200/day paid"),
        },
    },
}

DEFAULT_TIER = "free"
STAGGER_DELAY = 5              # Seconds between staggered platform launches

# State file location (beside Chrome profile data, persists across projects)
RATE_LIMIT_STATE_DIR = str(Path.home() / ".chrome-playwright")
