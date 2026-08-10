---
name: claude-usage-monitor
description: "Use when monitoring Claude Code (Pro/Max) weekly usage against a prorated daily budget. Fires persistent Windows Toast notifications (gentle chime, click-to-dismiss) via Claude Code's Stop hook using pythonw.exe — no pop-up windows. Includes desktop widget, Chrome web dashboard, and /budget slash command."
version: 1.8.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [claude-code, usage-monitor, toast-notification, windows, budget, task-scheduler, pythonw]
    related_skills: [claude-code, fix-transparent-cmd-popups, life-automation]
---

# Claude Usage Monitor — Weekly Prorated Budget with Toast Alerts

## Overview

A background monitor that tracks Claude Code (Pro/Max) weekly token usage against
a cumulative daily budget. The week runs **Friday (Day 1) through Thursday
(Day 7)** — configurable via `week_start_day` in config. On Friday you may use
up to 1/7 of your weekly allowance; on Saturday up to 2/7 even if Friday was
unused; ... on Thursday up to 7/7. If cumulative usage exceeds the day's
threshold, a persistent Windows Toast notification fires.

**Event-driven**: the check runs every time Claude Code finishes a response, via
Claude Code's built-in `Stop` hook. No polling, no cron — real-time on-demand.

**No pop-up windows**: the hook invokes `pythonw.exe` (Python's windowless
executable) directly — no `.ps1`, no `.bat`, no `cmd.exe`, no `powershell.exe`.
One process, zero console windows, not even a flash.

**Persistent toast**: `scenario='urgent'` + `duration='long'` keeps the
notification on screen until the user clicks to dismiss. Sound is a gentle
chime (`ms-winsoundevent:Notification.Default`), NOT a harsh alarm — per
user preference. The toast fires in a detached `pythonw.exe` subprocess so
the Stop hook returns immediately and Claude Code is not blocked.

## When To Use

- User wants to pace Claude Code usage across the week to avoid early burnout
- User wants Toast notifications when breaching the day's prorated budget
- User is on Claude Pro/Max subscription and uses the `claude` CLI

**Don't use for:**
- API-key-billed usage (different accounting model — use Anthropic Console instead)
- Time-based polling (this is event-driven, not scheduled)
- Non-Windows platforms (Toast notification is Windows-specific)

## User Preferences (embedded from session 2026-08-07)

- **Sound**: gentle chime, NOT alarm. Use `ms-winsoundevent:Notification.Default`.
  The `Notification.Looping.Alarm` sound is too harsh/loud. User said: "a little
  less volume would be great, maybe a gong something nice. Not alarms."
- **Message format**: "You've used X% of your weekly allowance" — natural,
  conversational tone. Include the day's budget and day index for context.
  Avoid emoji prefixes like ⚠️ — they add noise.
- **Persistence**: toast stays until clicked. User said: "keep it up instead of
  it goes away, I have to click to make it go away — it's pretty important."
- **File placement**: keep files off the Desktop. User said: "move feel files,
  they shouldn't be on the desktop. Somewhere they won't be messed with,
  C:\\local-ai maybe." The AHK file was moved to `C:\\local-ai\\XactMacros.ahk`.
- **Week starts Friday**: user's usage week runs Friday (Day 1) through Thursday
  (Day 7), NOT Saturday through Friday. User corrected: "we started on Friday,
  today is Saturday day 2." Config `week_start_day` is `"friday"`.
- **Burn rate = actual, not extrapolated**: user wants %/hour showing actual
  tokens consumed in the last 60 minutes from transcripts, not a rate
  extrapolated from delta between readings. User said: "%/hour for the last
  hour just to get an idea of usage not of total hours."

## Architecture

```
Claude Code CLI
  ↓ Stop hook fires after each response
  ↓
pythonw.exe claude_usage_monitor.py     (1 process, 0 windows)
  ↓
  1. day_index = WEEK_MAP[today]         (Fri=1 .. Thu=7)
  2. threshold = day_index / divisor     (7 for prod)
  3. daily_pct = usage_pct / threshold * 100
  4. Parse session JSONLs for this week's tokens
  5. If daily_pct >= 60  → fire YELLOW toast (once/day)
  6. If daily_pct >= 80  → fire RED toast    (once/day)
  7. If daily_pct >= 100 → fire BREACH toast (once/day)
  ↓
  Toast fires in DETACHED pythonw subprocess
  → hook returns immediately, Claude Code not blocked
  → toast stays on screen until user clicks (gentle chime)
```

## Components

### 1. `scripts/claude_usage_monitor.py` — Core Logic

**Real implementation** — not pseudocode. See the actual file for full source.
Key functions:

| Function | Purpose |
|---|---|
| `get_day_index()` | Returns 1 (Fri) through 7 (Thu) |
| `get_week_bounds()` | Returns (friday, thursday) for current week |
| `get_threshold(config)` | `day_index / divisor` |
| `get_usage_percent(config)` | Parses `~/.claude/projects/*/*.jsonl` for weekly token sum |
| `get_hourly_pct(config)` | Scans transcripts for tokens in the last 60 min → % of weekly cap |
| `get_today_tokens(config)` | Scans transcripts for tokens since midnight (local) → raw token count |
| `get_5h_window(config)` | Returns `(tokens_5h, prompts_5h, minutes_to_reset)` using gap detection |
| `fire_toast(title, body, scenario)` | Persistent toast via `win11toast`, gentle chime |
| `fire_toast_detached(title, body, scenario)` | Spawns toast in `pythonw.exe` subprocess (non-blocking) |
| `should_notify(tier, daily_pct, config)` | 3-tier once-per-day dedup (yellow/red/breach) via `notify_state.json` |

CLI modes:
- `--dry-run` — prints day, threshold, tokens, would-fire status
- `--test-toast` — fires a test notification (what the desktop shortcut uses)
- `--fire-toast <title> <body> [scenario]` — internal mode for detached subprocess

### 2. No Launcher — `pythonw.exe` Runs `.py` Directly

No `.ps1`, no `.bat`, no `cmd.exe`, no `powershell.exe`. The Claude Code
Stop hook invokes `pythonw.exe` directly. `pythonw.exe` is `python.exe` with
the console subsystem compiled out — no window is ever created.

**Verified paths** on this machine:
- `C:\Users\Aloha\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe` (Hermes venv 3.11 — use this, has pip packages)
- `C:\Users\Aloha\AppData\Local\Programs\Python\Python312\pythonw.exe` (system 3.12 — backup)

### 3. `config.json` — Runtime Configuration

```json
{
  "claude_projects_dir": "C:/Users/Aloha/.claude/projects",
  "divisor": 7,
  "log_enabled": true,
  "max_log_size_mb": 5,
  "toast_app_id": "ClaudeUsageMonitor",
  "toast_title": "Claude Budget Breach",
  "usage_source": "session_transcripts",
  "week_start_day": "friday",
  "weekly_token_cap": 50000000
}
```

**Key fields**:
- `divisor`: **7** for production (stage-1 testing used 70 for 10x stricter threshold, then switched)
- `weekly_token_cap`: 50,000,000 (50M tokens — tuned to real weekly usage of ~40M)
- `claude_projects_dir`: use forward slashes in JSON (backslash escape issues with heredoc)
- `usage_source`: `session_transcripts` — parses JSONL files, the only working method

**Config gotcha**: never write config via bash heredoc with `\\` — bash mangles
backslash escapes. Use forward slashes (`C:/Users/...`) or `write_file`/`patch`.

### 4. Claude Code Stop Hook Registration

**Location**: `C:\Users\Aloha\.claude\settings.json`

The Stop hook sits alongside existing `PreToolUse` and `UserPromptSubmit` hooks:

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "C:\\Users\\Aloha\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\pythonw.exe C:\\Users\\Aloha\\AppData\\Local\\hermes\\skills\\productivity\\claude-usage-monitor\\scripts\\claude_usage_monitor.py",
        "timeout": 15
      }]
    }]
  }
}
```

### 5. Desktop Widget — `scripts/claude_usage_widget.pyw`

Small always-on-top tkinter window (decorated, not borderless) showing:
- **Big number**: daily allowance % used (font 24, green <60% / yellow 60-80% / red ≥80%)
- **Small text**: "of Day X/7 budget (Y%)" + weekly % (font 8)
- **Burn rate**: "Last hr: X.X%/hr" — actual tokens consumed in last 60 min from transcripts (not extrapolated)
- Updates every 10s + instantly when Stop hook writes `widget_refresh.tmp`
- Drag to move (click anywhere), right-click to close
- Runs via `pythonw.exe` — no console window
- NOT borderless (`overrideredirect(True)` hides windows on Windows 11 — see pitfall #9)

**Launch pattern (CRITICAL)**: never run `pythonw.exe widget.pyw` directly
from the terminal tool — it blocks. Use PowerShell `Start-Process` to launch
detached:

```powershell
Start-Process -FilePath "C:\...\pythonw.exe" -ArgumentList "C:\...\claude_usage_widget.pyw"
```

Or in Python via `subprocess.Popen`:
```python
subprocess.Popen(["pythonw.exe", "widget.pyw"],
    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
```

**Task Scheduler**: `ClaudeUsageWidget-Startup` — at logon, runs widget via `pythonw.exe`.

### 6. `/budget` Slash Command

**Path**: `C:\Users\Aloha\.claude\commands\budget.md`

Type `/budget` in Claude Code to see current usage in the terminal.
Runs `claude_usage_monitor.py --dry-run` and prints the output.

### 7. Task Scheduler Entry (Monitor)

**Task name**: `ClaudeUsageMonitor-Startup`
**Trigger**: At logon (user Aloha)
**Action**: `pythonw.exe claude_usage_monitor.py` (no shell, no window)

### 8. Web Dashboard — `scripts/dashboard.html` + `scripts/dashboard_server.pyw`

When you can't embed UI inside Claude Code's terminal, serve a tiny local
dashboard that opens as a Chrome tab beside the terminal.

- **Server**: `dashboard_server.pyw` — Python stdlib `http.server` on port
  7871. Runs via `pythonw.exe` (no console). Serves `dashboard.html` +
  `usage.json` with no-cache headers.
- **HTML**: `dashboard.html` — dark theme, big daily % number (96px), progress
  bars (daily + weekly), stats grid showing time-to-limit, tokens left today,
  burn rate (%/hr), and weekly remaining tokens. Auto-refreshes every 3s via `fetch()`.
- **Data**: monitor writes `usage.json` on every Stop hook fire with:
  `daily_pct`, `usage_pct`, `threshold_pct`, `day_index`, `hourly_pct`,
  `hourly_tokens`, `today_tokens`, `today_pct`, `tokens_5h`, `prompts_5h`,
  `minutes_to_reset`, `total_tokens`, `weekly_cap`, `remaining_today_tokens`,
  `remaining_today_pct`, `hours_to_limit`, `weekly_remaining_tokens`,
  `timestamp`.
  Dashboard polls it. No external dependencies (vanilla JS, no frameworks).
- **Time-to-limit calculation**: `hours = ((100 - daily_pct) * threshold_pct) / (hourly_pct * 100)`.
  Converts daily % remaining into hours at current burn rate. Shows `∞` when idle.
- **5-hour rate window**: shows tokens consumed in the last 5 hours, prompt count,
  and minutes until the window resets (when oldest prompt falls outside 5h).
  Timestamps in JSONL are UTC; local time is HST (UTC-10) — `get_5h_window()`
  converts local now to UTC (`now_utc = now_local + 10h`) before comparing.
- **Budget breakdown table**: 7-row table (Fri→Thu) showing each day's allowed %,
  allowed tokens, and cumulative tokens used. Today's row highlighted green.
- **Tokens/hour stat**: shows actual tokens (not just %) consumed in the last hour,
  computed as `int(weekly_cap * hourly_pct / 100)`.
- **Open**: `cmd.exe //c start "" "http://127.0.0.1:7871/"`
- **Startup**: Task Scheduler `ClaudeUsageDashboard-Startup` at logon.

See `references/dashboard-implementation.md` for full architecture details.

### 9. Desktop Shortcut

**Path**: `C:\Users\Aloha\Desktop\Claude Usage Monitor.lnk`
**Target**: `pythonw.exe` with `--test-toast` argument
**Purpose**: double-click to fire a test notification anytime

## Three-Tier Alert System

Notifications are based on **daily allowance % used** (weekly usage / today's
threshold × 100), not raw weekly %.

| Tier | Fires when daily % hits | Widget Color | Toast Title | Once/day? |
|---|---|---|---|---|
| **Yellow** | 60% | 🟡 Yellow | Claude Budget — 60% Used | Yes (`notify_state.json`) |
| **Red** | 80% | 🔴 Red | Claude Budget — 80% Used | Yes |
| **Breach** | 100% | 🔴 Red | Claude Budget Breach | Yes |

State file (`notify_state.json`) resets daily. Each tier fires at most once
per day. Breach takes priority > red > yellow (only one fires per run).

**Message format** (per user preference — natural tone, no emoji):
- Yellow (60%): "You've used 60% of today's allowance (Day 2/7). Weekly: 8.5%. Heads up — 40% left for today."
- Red (80%): "You've used 80% of today's allowance (Day 2/7). Weekly: 11.3%. 20% left for today — almost at the limit."
- Breach (100%): "You've used 100% of today's allowance — over the daily budget (Day 2/7). Weekly usage: 14.3%. Stop to keep access all week."

**Widget color thresholds** (matching the toast tiers):
- Green: daily % < 60%
- Yellow: 60% ≤ daily % < 80%
- Red: daily % ≥ 80%

## Day-of-Week Threshold Table

| Day | weekday() | Day Index | Threshold (prod ÷7) | Threshold (stage-1 ÷70) |
|---|---|---|---|---|
| Friday | 4 | 1 | 14.29% | 1.43% |
| Saturday | 5 | 2 | 28.57% | 2.86% |
| Sunday | 6 | 3 | 42.86% | 4.29% |
| Monday | 0 | 4 | 57.14% | 5.71% |
| Tuesday | 1 | 5 | 71.43% | 7.14% |
| Wednesday | 2 | 6 | 85.71% | 8.57% |
| Thursday | 3 | 7 | 100.00% | 10.00% |

## Token Data Source

Claude Code stores session transcripts as JSONL in
`~/.claude/projects/<project>/<session-id>.jsonl`. Each assistant message
has a `usage` dict with `input_tokens` and `output_tokens`. The script:

1. Globs all `*.jsonl` under all project directories
2. Skips files not modified this week (mtime check for speed)
3. Parses each line, filters to `type == "assistant"` with a timestamp in this week
4. Sums `input_tokens + output_tokens` (cache reads excluded — cheap/free on subscription)
5. Computes `total_tokens / weekly_token_cap * 100`

**Verified**: 40,382,733 tokens found across real sessions for the week of
2026-08-01 to 2026-08-07.

## Installation Steps

1. `pip install win11toast` (in the Hermes venv)
2. Create `config.json` with `divisor=7` (production), `weekly_token_cap=50000000`
3. Merge `Stop` hook into `~/.claude/settings.json`
4. Create Task Scheduler entries: `ClaudeUsageMonitor-Startup` + `ClaudeUsageWidget-Startup` (both at logon)
5. Create desktop shortcut pointing to `pythonw.exe --test-toast`
6. Create `/budget` slash command at `~/.claude/commands/budget.md`
7. Test: fire `--test-toast`, confirm gentle chime + persistent (click to dismiss)
8. Launch widget via `Start-Process pythonw.exe -ArgumentList "widget.pyw"`
9. Move any AHK files off Desktop to `C:\local-ai\`, update startup shortcuts

## Verification

```bash
# Dry-run — prints day, threshold, token count, would-fire status
python .../claude_usage_monitor.py --dry-run

# Test toast — fires persistent notification with gentle chime
python .../claude_usage_monitor.py --test-toast

# Check hook is registered
python -c "import json; d=json.load(open('C:/Users/Aloha/.claude/settings.json')); print(json.dumps(d.get('hooks',{}), indent=2))"

# Check task scheduler
schtasks /query /tn "ClaudeUsageMonitor-Startup" /fo csv /v

# Check log
cat .../usage_monitor.log

# Verify no ghost windows
powershell -Command "Get-Process cmd -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }"
```

A full 54-check ad-hoc verification script was used during build. See
`references/verification-recipe.md` for the verification approach.

## Common Pitfalls

1. **JSON config backslash escapes**: writing config via bash heredoc mangles
   `\\U` into invalid JSON. Use forward slashes (`C:/Users/...`) or `write_file`/`patch`.
   **Happened this session**: config failed to load with "Invalid \\escape" error.

2. **Alarm sound too harsh**: user rejected `Notification.Looping.Alarm`.
   Always use `ms-winsoundevent:Notification.Default` (gentle chime). See
   User Preferences above.

3. **Stop hook blocking**: if the toast fires inline (not detached), it blocks
   Claude Code until the user clicks it. Always use `fire_toast_detached()` which
   spawns a separate `pythonw.exe` subprocess.

4. **Ghost cmd windows**: never use `.bat`, `.ps1`, `cmd.exe`, or `powershell.exe`
   in the hook command. Use `pythonw.exe` directly — it has no console subsystem.
   See `fix-transparent-cmd-popups` skill.

5. **`weekly_token_cap` too low**: if the cap is unrealistically small (e.g. 1M),
   usage shows as 4038% and every run fires. Tune to real usage (~50M for this user).

6. **Token parsing speed**: globbing all JSONL files can be slow if there are many.
   The mtime pre-filter skips files not modified this week — keeps it under 1s.

7. **Multiple Claude Code sessions**: each fires its own Stop hook. The
   `notify_state.json` dedup file must handle concurrent writes gracefully
   (currently uses simple read-modify-write — acceptable for single-user).

8. **GUI widgets block the terminal tool**: never run `pythonw.exe widget.pyw`
   directly from the Hermes terminal tool — `pythonw.exe` blocks the tool even
   though no window appears. The session hung for 180s before timeout. **Always
   launch detached** via `Start-Process pythonw.exe -ArgumentList "widget.pyw"`
   (PowerShell) or `subprocess.Popen([...], creationflags=DETACHED_PROCESS)`.

9. **`overrideredirect(True)` hides tkinter windows on Windows 11**: borderless
   tkinter windows become invisible on Windows 11 with Windows Terminal. The
   widget process runs (visible in `Get-Process`) but no window appears on
   screen. **Fix**: use a normal decorated window with `resizable(False, False)`
   and fixed `minsize`/`maxsize` instead of `overrideredirect(True)`. The title
   bar is a small price for actually being visible. If you need borderless,
   test on the target machine first — don't assume it works.

10. **Burn rate (%/hr) — use actual last-hour token scan, not delta tracking**:
    The initial approach tracked `prev_tokens`/`prev_time` between widget
    refreshes (every 10s) and extrapolated. User corrected: wants actual
    usage in the last hour, not an extrapolation. **Fix**: scan transcripts
    for tokens with timestamps in the last 60 minutes, sum them, divide by
    `weekly_token_cap`. This gives real %/hr consumed, not a rate estimate.
    First reading shows a real number immediately (no "measuring…" delay).
    Implemented as `get_hourly_pct(config)` in the monitor and `get_usage()`
    returning `hourly_pct` as a 5th value in the widget.

11. **Moving files off Desktop**: user prefers files not live on Desktop. AHK
    files, config files, scripts — move to `C:\local-ai\` or the skill directory.
    Archive the original (never delete per CLAUDE.md rule 3). Update any shortcuts
    or startup entries that pointed to the old location.

12. **Week start day must be confirmed with the user**: the initial build assumed
    Saturday=Day 1, but user's week starts Friday. Always ask which day the
    usage week begins before coding the `WEEK_MAP`. Config `week_start_day`
    field documents the choice but the Python `WEEK_MAP` dict is hardcoded —
    if the user changes their mind, both must be updated.

13. **`should_notify()` signature changed**: the function now takes
    `(tier, daily_pct, config)` — NOT the old `(tier, usage_pct, threshold_pct, config)`.
    The tiers compare against `daily_pct` (60/80/100) directly, not against
    `threshold_pct`. If you copy old call sites, the comparison logic breaks
    silently (threshold_pct is ~14-100, so everything fires at tier 1).

14. **5-hour rate window timestamps are UTC, not local**: JSONL timestamps
    end in `Z` (UTC). If the machine is in HST (UTC-10), comparing local
    `datetime.now()` directly against these timestamps is off by 10 hours.
    **Fix**: `now_utc = datetime.datetime.now() + datetime.timedelta(hours=10)`
    (hardcoded for HST — make configurable if used in other timezones). The
    `get_5h_window()` function handles this. Without the offset, the window
    shows prompts from 10 hours ago as "current" and the reset time is
    completely wrong.

15. **5-hour window reset is NOT the oldest prompt**: the first approach used
    the oldest prompt + 5h, which showed "0 minutes to reset" constantly
    because some prompt is always ~5h old in a rolling window. The actual
    reset happens after a **gap in activity > 5 minutes** — that gap is when
    Claude Code's internal rate limiter resets and starts a fresh window.
    **Fix**: collect all prompt timestamps, sort them, find the most recent
    gap > 300 seconds. The window starts from the first prompt after that gap.
    `window_start + 5h` is the reset time. Verified 2026-08-09: gap detection
    found a 5-minute gap at 14:04 UTC, giving 4.6h to reset — matching the
    user's reported "4h43m" from Claude Code's UI.
    See `references/five-hour-window.md` for the full technique.

16. **Dashboard server can die silently**: the `dashboard_server.pyw` process
    runs via `pythonw.exe` with no console, so if it crashes or hangs, the
    dashboard shows a blank page with no error. **Symptom**: Chrome tab loads
    but shows empty/dark page; `curl http://127.0.0.1:7871/` returns 0 bytes.
    **Fix**: check `Get-Process pythonw` — if no process, restart via
    `Start-Process pythonw.exe -ArgumentList "dashboard_server.pyw"`. The
    server is simple (`http.server.serve_forever()`) so crashes are rare but
    can happen if the port is already in use or the script has an import error.

17. **JS snake_case vs camelCase naming kills the dashboard silently**: when
    writing dashboard JS, Python habits leak in — `weekly_cap` (snake_case,
    undefined in JS) instead of `weeklyCap` (camelCase, the actual parameter).
    This throws a `ReferenceError` that stops the entire script — the page
    loads but shows nothing. **No error is visible** because there's no console
    open. **Symptom**: dashboard HTML loads (9KB returned by curl) but the page
    is blank/dark with no data. **Fix**: open Chrome DevTools (F12) → Console
    to see the `ReferenceError`. Always use camelCase in JS, snake_case in
    Python. When a parameter is passed from Python to JS via JSON, the JSON
    keys are snake_case (`weekly_cap`, `daily_pct`) but JS variables that
    receive them must be camelCase. **Happened this session**:
    `buildBreakdown(dayIdx, totalTokens, weekly_cap)` — `weekly_cap` was
    undefined, crashing the entire render loop.

## Verification Checklist

- [ ] `claude_usage_monitor.py` runs in `--dry-run` mode without errors
- [ ] `pythonw.exe` runs the script with zero windows (no flash, no ghost)
- [ ] `config.json` loads as valid JSON with `divisor: 7` (production)
- [ ] Stop hook registered in `~/.claude/settings.json` using `pythonw.exe`
- [ ] Task Scheduler `ClaudeUsageMonitor-Startup` visible in `schtasks /query`
- [ ] Task Scheduler `ClaudeUsageWidget-Startup` visible in `schtasks /query`
- [ ] `--test-toast` fires persistent toast with gentle chime, stays until clicked
- [ ] `usage_monitor.log` contains entries showing the check ran
- [ ] No ghost `cmd.exe` windows (verified with `Get-Process cmd`)
- [ ] No `powershell.exe` or `cmd.exe` in any hook or task command
- [ ] No API keys or credentials read by the script
- [ ] Desktop shortcut exists and fires test toast when double-clicked
- [ ] Widget launches via `Start-Process` (detached, non-blocking)
- [ ] Widget shows big daily % (green/yellow/red) + small weekly % + "Last hr: X%/hr"
- [ ] Widget updates when Stop hook fires (refresh signal file)
- [ ] Widget is NOT borderless (decorated window — `overrideredirect` hides on Win11)
- [ ] Burn rate shows actual last-hour token consumption from transcripts (not extrapolated)
- [ ] `/budget` slash command exists at `~/.claude/commands/budget.md`
- [ ] Web dashboard server runs on `http://127.0.0.1:7871/` (via `pythonw.exe`)
- [ ] Dashboard shows big daily %, progress bars, weekly %, real %/hr, time-to-limit, tokens left today, weekly remaining
- [ ] Dashboard shows 5-hour rate window (tokens 5h, prompts 5h, minutes to reset)
- [ ] Dashboard shows budget breakdown table (7 rows Fri→Thu, today highlighted)
- [ ] Dashboard shows tokens/hour stat (actual tokens, not just %)
- [ ] Dashboard shows today overlay on weekly bar (bright green segment for today's contribution)
- [ ] Dashboard shows `(+X.X% today)` tag next to Weekly Allowance label
- [ ] Dashboard auto-refreshes every 3 seconds
- [ ] `usage.json` written by monitor on every Stop hook fire (with `hourly_pct` from `get_hourly_pct()`, `remaining_today_tokens`, `hours_to_limit`, `weekly_remaining_tokens`)
- [ ] Task Scheduler `ClaudeUsageDashboard-Startup` exists
- [ ] Public repo pushed: `github.com/onecoded/claude-usage-monitor`

## Public Repo

**URL**: https://github.com/onecoded/claude-usage-monitor

Contains: `claude_usage_monitor.py`, `claude_usage_widget.pyw`,
`config.example.json`, `README.md`, `LICENSE` (MIT), `SKILL.md`, `.gitignore`.

## References

- `references/widget-implementation.md` — widget pitfalls (`overrideredirect`
  trap, burn rate calc, layout, launch pattern, refresh signal)
- `references/verification-recipe.md` — 54-check ad-hoc verification approach
- `references/dashboard-implementation.md` — web dashboard architecture (HTTP
  server + auto-refreshing HTML + usage.json data flow)
- `references/five-hour-window.md` — 5-hour rate window technique (gap
  detection for reset time, UTC timezone handling, verification data)
- `templates/dashboard.html` — copy-and-modify dashboard HTML template
- `scripts/claude_usage_monitor.py` — core monitor script (full implementation)
