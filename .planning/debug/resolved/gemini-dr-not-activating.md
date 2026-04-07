---
status: investigating
trigger: "Gemini completed as regular response (9,867c, 91s) instead of triggering Deep Research, despite engine logging 'Clicked Start research button'"
created: 2026-04-08T00:00:00Z
updated: 2026-04-08T00:00:00Z
symptoms_prefilled: true
---

## Current Focus

hypothesis: post_send() waits a FIXED 20s for the DR plan to appear, then tries ONE set of button selectors. If Gemini's tab doesn't have focus during those 20s (due to 7-platform parallel run), the "Start research" button may appear and auto-dismiss before the click attempt, OR the click succeeds but Gemini requires a second confirmation step that isn't handled. After the click, post_send() does a 5s wait then checks for Stop/Cancel — if not found it simply returns with no error. completion_check() then starts from _seen_stop=False, and the 6-poll / 5000 char quick-response fallback fires after only ~52s.
test: Trace the exact code path in post_send() and completion_check() for this symptom
expecting: Confirm post_send() silently returns after clicking without verifying DR started; confirm _seen_stop stays False; confirm 5a fallback fires
next_action: confirmed via code reading — proceed to fix

## Symptoms

expected: Gemini should start Deep Research, show DR indicators, and produce a 50,000–70,000 char report in ~280s.
actual: Engine logs "Clicked 'Start research' button" then 52s later logs "No DR indicators seen, body 9867c stable for 6 polls — quick/regular response, declaring complete". Only 9,867c extracted.
errors: "WARNING [Gemini] Body text appears to be a prompt echo — skipping full-body fallback"
reproduction: Run full 7-platform DEEP orchestrator run. Gemini-only runs work correctly.
timeline: Observed in iter 25 (2026-04-07). Previous Gemini-only test (same day) worked with Share & Export detection (65,098c, 284s, v0.2.26040632).

## Eliminated

- hypothesis: Click never happened
  evidence: Log explicitly says "Clicked 'Start research' button" — the click was registered
  timestamp: 2026-04-08

- hypothesis: DR was never enabled in configure_mode
  evidence: mode=DEEP is passed through; configure_mode sets self._deep_mode=True when it clicks. If it failed there would be a warning, not a "Start research" click log.
  timestamp: 2026-04-08

## Evidence

- timestamp: 2026-04-08
  checked: post_send() in gemini.py lines 215-284
  found: After clicking "Start research", post_send() waits only 5s then checks for Stop/Cancel. If not found, it falls through and RETURNS without error or retry. The 20s wait before the click attempt is fixed and not repeated.
  implication: If the Stop/Cancel button hasn't appeared within 5s of the click (e.g. tab was not in focus and Gemini UI was slow), post_send() silently returns thinking it's fine.

- timestamp: 2026-04-08
  checked: completion_check() lines 286-420, specifically sections 4/5a
  found: _seen_stop starts False. Section 5a fires when: not _seen_stop AND body_len_check > 5000 AND _no_stop_polls >= 6. At 10s poll interval (POLL_INTERVAL), 6 polls = ~60s. Body of 9,867c > 5000 threshold. This is EXACTLY what the log shows: "52s later, 6 polls, 9867c".
  implication: Confirms the 5a fallback is the exit path. _seen_stop never became True because no Stop/Cancel/Thinking indicators were ever detected after post_send() returned.

- timestamp: 2026-04-08
  checked: completion_check() DR indicator selectors (lines 293-335)
  found: The Stop/Cancel check looks for 'button:has-text("Stop")', 'button:has-text("Cancel")' etc. The Thinking/Searching check is scoped to '[class*="progress"]', '[class*="deep-research"]', 'model-response'. These are reasonable but may miss Gemini's actual DR-in-progress UI elements if the tab is backgrounded.
  implication: Even if DR started, if the tab never gets focus and Gemini's Angular doesn't render the progress indicators in the DOM (some SPAs skip rendering for background tabs), _seen_stop stays False.

- timestamp: 2026-04-08
  checked: post_send() verification block (lines 264-272)
  found: After clicking Start research, post_send() waits 5s then checks Stop/Cancel. Crucially: if Stop IS found, it logs "Research crawl started" and returns. If Stop is NOT found, it falls through to lines 277-282 (checks again without waiting more) and if still not found, returns None with NO log warning or flag. The _seen_stop instance var is never set in post_send() — it's only set by completion_check() at poll time.
  implication: post_send() has no way to signal "DR didn't start" to the polling loop. The polling loop then relies on completion_check() seeing DR indicators organically, which may not happen if the tab is not in focus or Gemini's UI takes more than 5s to show the Stop button.

- timestamp: 2026-04-08
  checked: POLL_INTERVAL config usage and 5a threshold
  found: 6 polls at standard 10s interval = 60s. But the log says 52s. With the 20s wait in post_send() + 5s verification wait = 25s. Then 52s - 25s = ~27s of polling = ~3 polls before 5a fires? The count may reset. Either way, 5a fires with exactly 6 polls logged, which maps to the completion_check counter _no_stop_polls.
  implication: The timeline is consistent with 6 polls × 10s = 60s minus overhead.

## Resolution

root_cause: |
  Two compounding issues:
  
  1. post_send() silently succeeds after clicking "Start research" even when DR hasn't confirmed started.
     After the click, it waits only 5s for a Stop/Cancel button. In a 7-platform parallel run, 
     Gemini's tab may be backgrounded — the Angular SPA may not render interactive UI promptly, 
     and the Stop button may take >5s to appear. post_send() then returns with no error and no flag.
  
  2. completion_check()'s quick-response fallback (section 5a) fires too eagerly. It declares 
     completion after just 6 polls with body > 5000 chars when _seen_stop is False. This is designed 
     to handle "Gemini gave a regular response instead of DR", but it fires even when DR was supposed 
     to start — because _seen_stop is never set when DR indicators don't appear in the 5s window 
     post-click.
  
  Root trigger: In a parallel run, Gemini's tab is backgrounded during the critical 5s post-click 
  verification window in post_send(). Gemini's Angular SPA renders the DR progress UI lazily 
  (or with focus-dependent timing), so the Stop/Cancel button appears after post_send() has already 
  returned. With _seen_stop=False, the 5a fallback declares "regular response" after 6 polls.

fix: |
  1. In post_send(): After clicking "Start research", extend the Stop/Cancel check to poll for 
     up to 60s (not just 5s), with page.bring_to_front() called first to ensure the tab renders. 
     If Stop/Cancel still not found, set a self._dr_start_unconfirmed = True flag.
  
  2. In completion_check(): When _dr_start_unconfirmed is True (DR was supposed to start but 
     Stop wasn't confirmed in post_send), don't use the 6-poll quick-response fallback. Instead, 
     continue polling with the full no_stop_limit (180 polls) to give DR time to surface. Also 
     call page.bring_to_front() in the first few polls if _seen_stop is still False.

verification: |
  Fix applied. post_send() now brings tab to front before clicking, then polls Stop/Cancel
  for up to 60s (12 × 5s). If still not seen, sets _dr_start_unconfirmed=True.
  completion_check() section 5a now skips quick-response exit when _dr_start_unconfirmed=True,
  and brings tab to front at polls 6/12/24/48 to force Angular to render DR progress UI.
  Awaiting next full 7-platform DEEP run to confirm DR activates correctly.
files_changed:
  - skills/orchestrator/engine/platforms/gemini.py
