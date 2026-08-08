---
name: claude-usage-monitor
description: "Use when monitoring Claude Code (Pro/Max) weekly usage against a prorated daily budget. Fires persistent Windows Toast notifications (gentle chime, click-to-dismiss) via Claude Code's Stop hook using pythonw.exe — no pop-up windows."
version: 1.1.0
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
a cumulative daily budget. The week runs Saturday (Day 1) through Friday (Day 7).
On Saturday you may use up to 1/7 of your weekly allowance; on Sunday up to 2/7
even if Saturday was unused; ... on Friday up to 7/7. If cumulative usage exceeds
the day's threshold, a persistent Windows Toast notification fires.

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
  C:\local-ai maybe." The AHK file was moved to `C:\local-ai\XactMacros.ahk`.

## Architecture

```
Claude Code CLI
  ↓ Stop hook fires after each response
  ↓
pythonw.exe claude_usage_monitor.py     (1 process, 0 windows)
  ↓
  1. day_index = WEEK_MAP[today]         (Sat=1 .. Fri=7)
  2. threshold = day_index / divisor     (70 for stage-1, 7 for prod)
  3. warning  = threshold * 10%          (10% of threshold = early alert)
  4. Parse session JSONLs for this week's tokens
  5. If usage >= warning → fire WARNING toast (once/day)
  6. If usage >= threshold → fire BREACH toast (once/day)
  ↓
  Toast fires in DETACHED pythonw subprocess
  → hook returns immediately, Claude Code not blocked
  → toast stays on screen until user clicks
```

## Components

### 1. `scripts/claude_usage_monitor.py` — Core Logic

**Real implementation** — not pseudocode. See the actual file for full source.
Key functions:

| Function | Purpose |
|---|---|
| `get_day_index()` | Returns 1 (Sat) through 7 (Fri) |
| `get_week_bounds()` | Returns (saturday, friday) for current week |
| `get_threshold(config)` | `day_index / divisor` |
| `get_usage_percent(config)` | Parses `~/.claude/projects/*/*.jsonl` for weekly token sum |
| `fire_toast(title, body, scenario)` | Persistent toast via `win11toast`, gentle chime |
| `fire_toast_detached(title, body, scenario)` | Spawns toast in `pythonw.exe` subprocess (non-blocking) |
| `should_notify(tier, ...)` | Once-per-day dedup via `notify_state.json` |

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
  "divisor": 70,
  "log_enabled": true,
  "max_log_size_mb": 5,
  "toast_app_id": "ClaudeUsageMonitor",
  "toast_title": "Claude Budget Breach",
  "usage_source": "session_transcripts",
  "week_start_day": "saturday",
  "weekly_token_cap": 50000000
}
```

**Key fields**:
- `divisor`: **70** for stage-1 testing (fires easily), **7** for production
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

### 5. Task Scheduler Entry

**Task name**: `ClaudeUsageMonitor-Startup`
**Trigger**: At logon (user Aloha)
**Action**: `pythonw.exe claude_usage_monitor.py` (no shell, no window)

### 6. Desktop Shortcut

**Path**: `C:\Users\Aloha\Desktop\Claude Usage Monitor.lnk`
**Target**: `pythonw.exe` with `--test-toast` argument
**Purpose**: double-click to fire a test notification anytime

## Two-Tier Alert System

| Tier | Fires when | Scenario | Title | Once/day? |
|---|---|---|---|---|
| **WARNING** | usage ≥ 10% of day's threshold | `urgent` | Claude Budget Warning | Yes (`notify_state.json`) |
| **BREACH** | usage ≥ day's threshold | `urgent` | Claude Budget Breach | Yes |

State file (`notify_state.json`) resets daily. Each tier fires at most once
per day. Breach takes priority if both are crossed in the same run.

**Message format** (per user preference — natural tone, no emoji):
- Warning: "You've used 80.8% of your weekly allowance. Today's budget is 10.0% (Day 7/7) — you're approaching the limit."
- Breach: "You've used 80.8% of your weekly allowance — that's over today's budget of 10.0% (Day 7/7). Slow down to keep access all week."

## Day-of-Week Threshold Table

| Day | weekday() | Day Index | Threshold (prod ÷7) | Threshold (stage-1 ÷70) |
|---|---|---|---|---|
| Saturday | 5 | 1 | 14.29% | 1.43% |
| Sunday | 6 | 2 | 28.57% | 2.86% |
| Monday | 0 | 3 | 42.86% | 4.29% |
| Tuesday | 1 | 4 | 57.14% | 5.71% |
| Wednesday | 2 | 5 | 71.43% | 7.14% |
| Thursday | 3 | 6 | 85.71% | 8.57% |
| Friday | 4 | 7 | 100.00% | 10.00% |

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
2. Create `config.json` with `divisor=70` (stage-1), `weekly_token_cap=50000000`
3. Merge `Stop` hook into `~/.claude/settings.json`
4. Create Task Scheduler entry: `Register-ScheduledTask -TaskName "ClaudeUsageMonitor-Startup" ...`
5. Create desktop shortcut pointing to `pythonw.exe --test-toast`
6. Test: double-click shortcut, confirm toast appears with gentle chime, stays until clicked
7. Production: change `divisor` from 70 to 7 in config.json

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

## Verification Checklist

- [ ] `claude_usage_monitor.py` runs in `--dry-run` mode without errors
- [ ] `pythonw.exe` runs the script with zero windows (no flash, no ghost)
- [ ] `config.json` loads as valid JSON with `divisor: 70` (stage-1)
- [ ] Stop hook registered in `~/.claude/settings.json` using `pythonw.exe`
- [ ] Task Scheduler `ClaudeUsageMonitor-Startup` visible in `schtasks /query`
- [ ] `--test-toast` fires persistent toast with gentle chime, stays until clicked
- [ ] `usage_monitor.log` contains entries showing the check ran
- [ ] No ghost `cmd.exe` windows (verified with `Get-Process cmd`)
- [ ] No `powershell.exe` or `cmd.exe` in any hook or task command
- [ ] No API keys or credentials read by the script
- [ ] Desktop shortcut exists and fires test toast when double-clicked
