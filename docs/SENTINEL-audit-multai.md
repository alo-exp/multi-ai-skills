# SENTINEL v2.3 Security Audit — MultAI Plugin

**Audit date**: 2026-04-08
**Auditor**: Claude Sonnet 4.6 (automated SENTINEL framework)
**Codebase**: `/Users/shafqat/Documents/Projects/MultAI` — branch `main`
**Scope**: Python/Playwright orchestration plugin (not a Claude skill)
**Audit steps**: SENTINEL Steps 0–8 applied to plugin code, scripts, and CI/CD

---

## Step 0 — Codebase Inventory

| Layer | Files | Notes |
|---|---|---|
| Engine core | `skills/orchestrator/engine/*.py` | CLI, orchestrator, prompt loader, rate limiter, agent fallback, config |
| Platform drivers | `skills/orchestrator/engine/platforms/*.py` | 7 platform drivers + base, inject, browser utils |
| Skills | `skills/comparator/`, `skills/landscape-researcher/`, `skills/orchestrator/` | SKILL.md + Python scripts |
| CI/CD | `.github/workflows/ci.yml` | Single workflow, no secrets stored in YAML |
| Hooks | `hooks/hooks.json`, `settings.json` | SessionStart hook runs `install.sh` |
| Setup scripts | `install.sh`, `setup.sh` | Bootstrap venv + Playwright |
| Dependencies | `pyproject.toml`, `requirements.txt` | Playwright 1.58.0, openpyxl 3.1.5, browser-use 0.12.2 |

---

## Step 1 — FINDING-1: Prompt Injection

**Assessment: LOW risk — partially mitigated, one residual gap**

### Primary path — Playwright injection (inject_utils.py)

The `_inject_exec_command` method passes the full user prompt to a browser contenteditable element via `page.evaluate(js, prompt)`. Playwright serialises the `prompt` argument as a JSON-encoded value and the JavaScript receives it as a typed string — it is not interpolated into the JS source string. This is the correct pattern; prompt content cannot break out of the JS string context.

```python
# inject_utils.py:23 — safe: prompt is a serialised argument, not string-interpolated
success = await page.evaluate("""(prompt) => { ... }""", prompt)
```

### Secondary path — Agent fallback task construction (agent_fallback.py)

The `full_platform_run` method constructs a task string that is sent verbatim to an external LLM (Anthropic Claude or Google Gemini). The prompt content is delimited with `<USER_PROMPT_START>` / `<USER_PROMPT_END>` markers and accompanied by a note to treat contents as literal user content. This delimiter approach is sound but not guaranteed to prevent a sophisticated adversarial prompt from escaping the delimiters and issuing instructions to the agent LLM.

```python
# agent_fallback.py — prompt embedded in LLM task string
f"<USER_PROMPT_START>\n{prompt_for_task}\n<USER_PROMPT_END>\n\n"
```

A prompt containing the text `<USER_PROMPT_END>` followed by additional instructions would escape the intended scope. No sanitisation of the delimiter tokens is performed before embedding.

**Patch recommendation (P1-1)**: Before constructing the task string in `full_platform_run`, strip the delimiter tokens from the prompt content:

```python
prompt_for_task = prompt_for_task.replace("<USER_PROMPT_END>", "[END]").replace("<USER_PROMPT_START>", "[START]")
```

---

## Step 2 — FINDING-2: Instruction Smuggling

**Assessment: No evidence found**

All configuration values are plain Python literals in `config.py`. No base64-encoded strings, hex-encoded payloads, or obfuscated data were found in any `.py`, `.json`, or `.sh` file. The `hooks/hooks.json` hook command is a straightforward conditional `bash install.sh` call with no embedded encoded content.

CI regression checks actively assert that no stray domain-specific prompt fragments are present in platform drivers:

```yaml
# ci.yml — regression guard
! grep -ri "solution.research" skills/orchestrator/engine/
! grep -r "_PROMPT_SIGS" skills/orchestrator/engine/platforms/*.py
```

---

## Step 3 — FINDING-3: Malicious Tool API / subprocess Misuse

**Assessment: MEDIUM — subprocess commands use fixed literals, but one vector is improvable**

### Clipboard tools (inject_utils.py)

`subprocess.run(["pbcopy"], input=prompt.encode("utf-8"), ...)` — The command name and arguments are all fixed string literals. No user-supplied data is interpolated into the command array. The prompt is passed via `stdin` (`input=`), not as a shell argument. `shell=False` is the default throughout. Shell injection is not possible. Clipboard state is cleared after paste (a good practice explicitly noted in the code).

### osascript (orchestrator.py)

```python
# orchestrator.py:113,146 — fixed string, no user input
subprocess.Popen(["osascript", "-e", 'tell application "Google Chrome" to set miniaturized of every window to true'], ...)
```

Fixed string only. Safe.

### Chrome launch (orchestrator.py)

```python
chrome_args = [chrome_exe, f"--user-data-dir={pw_data_dir}", f"--profile-directory={args.chrome_profile}", ...]
chrome_proc = subprocess.Popen(chrome_args, ...)
```

`chrome_exe` is derived from `detect_chrome_executable()` (hardcoded OS paths). `pw_data_dir` is constructed from `Path.home()` (not user-supplied). `args.chrome_profile` is user-supplied via `--chrome-profile` and is interpolated directly into a Chrome flag. While no shell injection is possible (`shell=False`), a maliciously crafted profile name such as `../../malicious` would cause Chrome to use an unexpected user data subdirectory.

**Patch recommendation (P2-2)**: Apply the same sanitisation used for `--task-name`:

```python
# In cli.py or orchestrator.py, before using args.chrome_profile:
safe_profile = "".join(c if c.isalnum() or c in "-_ " else "-" for c in args.chrome_profile)
```

### engine_setup.py subprocess calls

`subprocess.run([python_exe, "-c", _LAUNCH_SCRIPT], ...)` — `python_exe` is derived from `sys.executable` (the current interpreter) or the venv path, never from user input. The `-c` script is a fixed literal. Safe.

---

## Step 4 — FINDING-4: Hardcoded Secrets

**Assessment: No evidence found**

No API keys, tokens, or passwords are hardcoded in any source file. The codebase reads credentials exclusively from environment variables:

- `os.environ.get("ANTHROPIC_API_KEY")` — `agent_fallback.py`
- `os.environ.get("GOOGLE_API_KEY")` — `agent_fallback.py`

The `.env` loading in `engine_setup.py` uses a custom `_load_dotenv()` that reads `<project-root>/.env`. No `.env` file is committed to the repo.

CI secret detection scans for `sk-ant-` and `AIza` prefixes:

```yaml
! grep -rn "sk-ant-[a-zA-Z0-9]" . 2>/dev/null
! grep -rn "AIza[a-zA-Z0-9]" . 2>/dev/null
```

**Minor gap (P3-2)**: The CI regex does not cover OpenAI (`sk-`), HuggingFace (`hf_`), or generic `Bearer` tokens. None are present today, but coverage should be broadened.

---

## Step 5 — FINDING-5: Tool-Use Scope Escalation (Playwright / Browser Automation)

**Assessment: MEDIUM — CDP port exposes full browser control; dedicated-profile guidance is advisory only**

### CDP exposure

The orchestrator connects to Chrome via CDP on `localhost:9222` (`CDP_PORT = 9222`). Any process running as the same OS user can connect to this port and obtain full, unrestricted browser control — including all open tabs, all session cookies, and all web storage — not just AI platform tabs. No CDP authentication is possible (Chrome does not support it).

The code includes a security note:

```python
# config.py — SECURITY NOTE (SENTINEL F-005)
# For best isolation, run Chrome with a dedicated profile (--chrome-profile MultAI)...
```

However, this is advisory documentation only. The default `--chrome-profile` is `"Default"`, which is the user's primary Chrome profile containing all personal session cookies. This means the default configuration operates on the user's full browser identity.

**Patch recommendations**:

- P2-3: Change the `--chrome-profile` default from `"Default"` to `"MultAI"` in `cli.py`
- P2-3: Add a startup warning if the user is running with the `"Default"` profile
- P3-3: Add firewall/isolation guidance to `USER-GUIDE.md` (port 9222 must not be exposed beyond localhost)

### Playwright data directory

`tab_manager.py:_ensure_playwright_data_dir()` copies `Cookies`, `Login Data`, `Local Storage`, `Session Storage`, and `IndexedDB` from the real Chrome profile into `~/.chrome-playwright/`. This directory is created with `chmod 0o700` (owner-only), which is correct. The copied credential files are accessible to any process running as the same user — same risk profile as the originals.

---

## Step 6 — FINDING-6: Identity Spoofing

**Assessment: No evidence found**

No false authority claims, impersonation of Anthropic, or misleading identity assertions were found. Platform drivers interact only with their designated URLs (defined in `PLATFORM_URLS`). Agent fallback task strings include clear platform identification and do not claim to be human users. SKILL.md files accurately describe the plugin's capabilities.

---

## Step 7 — FINDING-7: Supply Chain Risk

**Assessment: MEDIUM — pip-audit runs but is non-blocking; pyproject.toml uses loose bounds**

### Pinned direct dependencies (good)

`requirements.txt` pins all direct dependencies to exact versions:

```
playwright==1.58.0
openpyxl==3.1.5
browser-use==0.12.2
anthropic==0.76.0
fastmcp==2.0.0
```

### pip-audit is non-blocking (finding)

```yaml
# ci.yml:109
- name: Dependency vulnerability scan
  run: pip-audit -r skills/orchestrator/engine/requirements.txt
  continue-on-error: true
```

`continue-on-error: true` means a known vulnerability in a dependency will not block the CI pipeline or prevent a release. This is a meaningful gap.

**Patch recommendation (P1-2)**: Remove `continue-on-error: true` or replace with severity-filtered failure:

```yaml
run: pip-audit -r skills/orchestrator/engine/requirements.txt --desc --severity HIGH
```

### pyproject.toml uses loose version bounds

`pyproject.toml` specifies `playwright>=1.40.0` and `openpyxl>=3.1.0` — loose bounds that allow pip to resolve any newer version when using `pip install .`. This diverges from `requirements.txt` (pinned), meaning installation method determines which versions are used.

**Patch recommendation (P2-4)**: Align `pyproject.toml` bounds with pinned `requirements.txt` versions, or explicitly document the divergence.

### browser-use==0.12.2 — elevated-trust third-party dependency

`browser-use` is an AI-driven browser automation library. When invoked, it executes LLM-directed browser actions with full CDP access. The version is pinned (good), but this library represents the highest-privilege third-party dependency in the stack.

**Patch recommendation (P3-4)**: Run `pip-compile` to generate a fully locked `requirements.txt` covering all transitive dependencies.

---

## Step 8 — FINDING-8: Data Exfiltration

**Assessment: LOW risk — one intentional disclosure, properly logged**

### Agent fallback API calls

When the agent fallback is triggered, up to 3000 characters of user prompt content are transmitted to the Anthropic or Google LLM API. This is intentional and necessary for the fallback to function. The code explicitly logs this:

```python
# agent_fallback.py — disclosure log
log.warning(
    f"[{display_name}] Agent fallback: up to {min(len(prompt), 3000)} chars of prompt "
    f"content will be transmitted to {self._llm_provider.upper()} API."
)
```

The transmission is disclosed, bounded (3000 chars), and logged. No additional exfiltration paths were found.

### urllib.request (orchestrator.py)

```python
# orchestrator.py:133 — CDP health check only, localhost-only
urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json/version", timeout=2)
```

Localhost call only, no user data transmitted.

### socket (landscape-researcher)

`launch_report.py:46` uses a socket to check local port availability. No external network calls.

---

## Step 9 — FINDING-9: Output Encoding

**Assessment: LOW risk — no web-facing output; file output is plain text**

All response extraction writes raw text (`.md` files) to the local filesystem. No HTML rendering or web interface is generated. No user-supplied data is interpolated into HTML templates. There is no XSS surface.

All structured output (rate limiter state, agent fallback log, tab state) uses `json.dumps(ensure_ascii=False)` — no manual string concatenation for JSON construction. Correct.

---

## Step 10 — FINDING-10: Persistence / Privilege Escalation

**Assessment: No evidence found**

No writes to shell rc files (`.bashrc`, `.zshrc`), crontab, launchd plist, or systemd units were found. The plugin writes only to:

- `~/.chrome-playwright/` — profile copies and state files (chmod 0o700)
- `<project-root>/reports/` — AI response output
- `<engine-dir>/.venv/` — Python virtual environment

The `hooks/hooks.json` `SessionStart` hook runs `install.sh` on first use, which creates a venv, installs pip packages, and downloads Playwright Chromium. No elevated privileges required; no system files modified.

---

## Additional Observations

### Output Directory Path Traversal (cli.py) — LOW

`_resolve_output_dir` resolves the `--output-dir` path and checks it is within the project root. However, if the check passes, the function returns `args.output_dir` (the **unresolved** original string), not the resolved path:

```python
# cli.py:112–120
resolved = Path(args.output_dir).resolve()
try:
    resolved.relative_to(_PROJECT_ROOT.resolve())
except ValueError:
    sys.exit(1)
return args.output_dir  # returns unresolved original, not resolved path
```

In practice this is low-risk because the check blocks obvious traversal. However, symlink-based traversal (a symlink that passes the check but points outside the root) is not caught, and the unresolved string is inconsistent.

**Patch (P2-1)**: Return `str(resolved)` instead of `args.output_dir`.

### CDP Port Hardcoded — LOW

`CDP_PORT = 9222` is a well-known default. No authentication is available on the CDP endpoint. This is a fundamental limitation of the CDP approach, not a code bug. Documentation is the primary mitigation.

### Auto-install of browser-use in _ensure_dependencies() — LOW

`engine_setup.py:_ensure_dependencies()` auto-installs `browser-use==0.12.2` at runtime if not present, even if the user ran `setup.sh --no-fallback`. The explicit opt-out is not honoured at runtime.

**Patch (P3-1)**: Check for a venv-local `.no-fallback` sentinel file before auto-installing `browser-use`.

---

## Patch Plan (Step 7 — Patch Plan Mode)

All patches are targeted fixes. No architectural changes required.

### P1 — Address before next release

| ID | Location | Change |
|---|---|---|
| P1-1 | `agent_fallback.py:full_platform_run` | Sanitise delimiter tokens in `prompt_for_task`: replace `<USER_PROMPT_END>` and `<USER_PROMPT_START>` before embedding in the LLM task string |
| P1-2 | `.github/workflows/ci.yml:109` | Remove `continue-on-error: true` from `pip-audit` step (or restrict failure to HIGH/CRITICAL CVEs only) |

### P2 — Address within 1–2 sprints

| ID | Location | Change |
|---|---|---|
| P2-1 | `cli.py:_resolve_output_dir` | Return `str(resolved)` instead of `args.output_dir` |
| P2-2 | `cli.py:parse_args` | Sanitise `--chrome-profile` input: allow only alphanumeric, hyphen, underscore, space |
| P2-3 | `cli.py` / `config.py` | Change default `--chrome-profile` from `"Default"` to `"MultAI"`; add startup warning if `"Default"` is used |
| P2-4 | `pyproject.toml` | Align loose `>=` version bounds with pinned `requirements.txt` versions or document the intentional divergence |

### P3 — Address opportunistically

| ID | Location | Change |
|---|---|---|
| P3-1 | `engine_setup.py:_ensure_dependencies` | Honour `--no-fallback` opt-out at runtime via a `.no-fallback` sentinel file |
| P3-2 | `.github/workflows/ci.yml` | Extend secret-detection regex to cover `sk-` (OpenAI) and `hf_` (HuggingFace) prefixes |
| P3-3 | `USER-GUIDE.md` | Add security section: document that CDP port 9222 must be localhost-only; recommend dedicated `MultAI` Chrome profile |
| P3-4 | `requirements.txt` | Run `pip-compile` to lock all transitive dependencies |

---

## SENTINEL VERDICT

```
Overall: Acceptable with conditions
Deployment recommendation: Deploy with mitigations (P1 patches required before release)
Critical findings: 0
High findings: 0
Medium findings: 3  (FINDING-3 chrome-profile sanitisation, FINDING-5 CDP scope, FINDING-7 pip-audit non-blocking)
Low findings: 4     (FINDING-1 delimiter injection, output-dir unresolved return, CDP hardcoded port, browser-use auto-install)
```

**Summary**: MultAI is a well-structured plugin with no hardcoded secrets, no persistence writes, no data exfiltration beyond intentionally disclosed API calls, and no identity spoofing. The two P1 patches (prompt delimiter sanitisation and blocking pip-audit) are small and must be applied before the next release. The four P2 patches (output-dir resolution, chrome-profile sanitisation, default profile change, pyproject.toml alignment) close the remaining medium-risk gaps. No architectural changes are required.
