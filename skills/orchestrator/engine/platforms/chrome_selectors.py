"""
chrome_selectors.py — CSS selectors for Claude-in-Chrome (Cowork) path.

Each platform entry contains:
  url            — URL to navigate to for a new conversation
  input_sel      — CSS selector for the prompt input element (textarea or contenteditable)
  submit_sel     — CSS selector for the send/submit button
  input_type     — 'textarea' | 'contenteditable' (affects JS injection strategy)
  login_signals  — substrings in page text that indicate the user is NOT signed in

These selectors are used by the orchestrator SKILL.md when running in Cowork via
mcp__Claude_in_Chrome__javascript_tool. Keep in sync with the Playwright platform files.
"""

PLATFORM_CHROME = {
    "gemini": {
        "url": "https://gemini.google.com",
        "input_sel": "rich-textarea .ql-editor, div[contenteditable='true'][role='textbox']",
        "submit_sel": "button[aria-label='Send message'], button.send-button",
        "input_type": "contenteditable",
        "login_signals": ["Sign in", "Log in", "sign in to continue"],
    },
    "claude_ai": {
        "url": "https://claude.ai/new",
        "input_sel": "div[contenteditable='true']",
        "submit_sel": "button[aria-label*='Send'], button[type='submit']",
        "input_type": "contenteditable",
        "login_signals": ["Sign in", "Log in", "Continue with Google"],
    },
    "chatgpt": {
        "url": "https://chat.openai.com",
        "input_sel": "#prompt-textarea",
        "submit_sel": "button[data-testid='send-button'], button[aria-label*='Send']",
        "input_type": "contenteditable",
        "login_signals": ["Log in", "Sign up", "Welcome back"],
    },
    "copilot": {
        "url": "https://copilot.microsoft.com",
        "input_sel": "textarea[placeholder*='Message'], textarea[aria-label*='message']",
        "submit_sel": "button[aria-label*='Submit'], button[aria-label*='Send'], button[type='submit']",
        "input_type": "textarea",
        "login_signals": ["Sign in", "Log in", "Microsoft account"],
    },
    "perplexity": {
        "url": "https://www.perplexity.ai",
        "input_sel": "textarea[placeholder*='Ask'], div[contenteditable='true']",
        "submit_sel": "button[aria-label*='Submit'], button[type='submit']",
        "input_type": "contenteditable",
        "login_signals": ["Log in", "Sign up", "Sign in"],
    },
    "grok": {
        "url": "https://grok.com",
        "input_sel": "div[contenteditable='true'].ProseMirror, div[contenteditable='true']",
        "submit_sel": "button[aria-label*='Send'], button[type='submit']",
        "input_type": "contenteditable",
        "login_signals": ["Log in", "Sign in", "Create account"],
    },
    "deepseek": {
        "url": "https://chat.deepseek.com",
        "input_sel": "textarea#chat-input, textarea",
        "submit_sel": "button[aria-label*='Send'], div[role='button'][aria-label*='send']",
        "input_type": "textarea",
        "login_signals": ["Log in", "Sign in", "Sign up"],
    },
}

# Ordered list for sequential Cowork execution (Gemini first, matches platform strip order)
PLATFORM_ORDER = ["gemini", "claude_ai", "chatgpt", "copilot", "perplexity", "grok", "deepseek"]

PLATFORM_DISPLAY = {
    "gemini":    "Google Gemini",
    "claude_ai": "Claude.ai",
    "chatgpt":   "ChatGPT",
    "copilot":   "Microsoft Copilot",
    "perplexity":"Perplexity",
    "grok":      "Grok",
    "deepseek":  "DeepSeek",
}
