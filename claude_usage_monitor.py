#!/usr/bin/env python
"""
DOES:   Monitors Claude Code weekly token usage against a prorated daily budget.
        Fires persistent Windows Toast notifications (require click to dismiss)
        at two tiers: WARNING at 10% of the day's threshold, BREACH at threshold.
IN-OUT: Reads session JSONL files from ~/.claude/projects/, config.json.
        Writes to usage_monitor.log. Fires Toast on breach.
COSTS:  ~0.5s per run (reads local files only, no network).
        Toast fires in detached subprocess — does not block the Stop hook.
"""

import datetime
import json
import os
import sys
import glob
import subprocess
import traceback

# --- Paths ---
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
LOG_PATH = os.path.join(SCRIPT_DIR, "usage_monitor.log")
SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude_usage_monitor.py")

# --- Day-of-week mapping: Saturday=1 .. Friday=7 ---
# datetime: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
WEEK_MAP = {
    5: 1,  # Saturday  = Day 1
    6: 2,  # Sunday    = Day 2
    0: 3,  # Monday    = Day 3
    1: 4,  # Tuesday   = Day 4
    2: 5,  # Wednesday = Day 5
    3: 6,  # Thursday  = Day 6
    4: 7,  # Friday    = Day 7
}

# Pythonw path for firing non-blocking toast subprocesses
PYTHONW = r"C:\Users\Aloha\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe"


def log(message):
    """Append a timestamped line to the log file."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


def get_day_index():
    """Return 1 (Saturday) through 7 (Friday)."""
    today = datetime.date.today().weekday()
    return WEEK_MAP[today]


def get_week_bounds():
    """Return (saturday, friday) datetime objects for the current usage week."""
    today = datetime.date.today()
    days_since_saturday = (today.weekday() - 5) % 7
    week_start = today - datetime.timedelta(days=days_since_saturday)
    week_end = week_start + datetime.timedelta(days=6)
    return week_start, week_end


def get_threshold(config):
    """Calculate the daily prorated threshold: day_index / divisor."""
    day_idx = get_day_index()
    divisor = config.get("divisor", 7)
    return day_idx / divisor


def get_usage_percent(config):
    """
    Sum tokens from all Claude Code session JSONL files for the current week.
    Returns (total_tokens, percentage_of_cap).

    Counts input_tokens + output_tokens (actual consumption).
    Cache reads are discounted (cheap/free on subscription).
    """
    projects_dir = config.get("claude_projects_dir", os.path.expanduser("~/.claude/projects"))
    weekly_cap = config.get("weekly_token_cap", 50000000)

    week_start, week_end = get_week_bounds()
    week_start_dt = datetime.datetime(week_start.year, week_start.month, week_start.day)
    week_end_dt = datetime.datetime(week_end.year, week_end.month, week_end.day, 23, 59, 59)

    total_input = 0
    total_output = 0

    jsonl_files = glob.glob(os.path.join(projects_dir, "*", "*.jsonl"))

    for jsonl_path in jsonl_files:
        try:
            mtime = os.path.getmtime(jsonl_path)
            mtime_dt = datetime.datetime.fromtimestamp(mtime)
            if mtime_dt < week_start_dt:
                continue

            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("type") != "assistant":
                            continue

                        ts_str = entry.get("timestamp", "")
                        if ts_str:
                            try:
                                ts = datetime.datetime.fromisoformat(
                                    ts_str.replace("Z", "+00:00")
                                ).replace(tzinfo=None)
                                if ts < week_start_dt or ts > week_end_dt:
                                    continue
                            except Exception:
                                pass

                        usage = entry.get("message", {}).get("usage", {})
                        if not usage:
                            continue

                        inp = usage.get("input_tokens", 0)
                        out = usage.get("output_tokens", 0)
                        total_input += inp
                        total_output += out
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            continue

    total_tokens = total_input + total_output
    pct = (total_tokens / weekly_cap * 100) if weekly_cap > 0 else 0
    return total_tokens, pct


def fire_toast(title, body, scenario="urgent"):
    """
    Fire a persistent Windows Toast notification using win11toast.
    scenario='urgent' keeps it on screen until the user clicks to dismiss.
    Uses a gentle chime sound (Notification.Default), not a harsh alarm.
    """
    try:
        from win11toast import toast
        toast(
            title, body,
            scenario=scenario,
            duration="long",
            audio="ms-winsoundevent:Notification.Default",
            on_click=lambda *args: None,
            on_dismissed=lambda *args: None,
        )
        return True
    except ImportError:
        log("win11toast not installed — toast failed")
        return False
    except Exception as e:
        log(f"Toast error: {e}")
        return False


def fire_toast_detached(title, body, scenario="urgent"):
    """
    Fire toast in a detached pythonw.exe subprocess so the Stop hook
    returns immediately. The toast stays on screen until the user clicks it,
    but Claude Code is not blocked.
    """
    try:
        subprocess.Popen(
            [PYTHONW, SCRIPT_PATH, "--fire-toast", title, body, scenario],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            close_fds=True
        )
        return True
    except Exception as e:
        log(f"Detached toast spawn failed: {e}")
        # Fallback: try inline (will block, but better than nothing)
        return fire_toast(title, body, scenario)


def should_notify(tier, usage_pct, threshold_pct, config):
    """
    Determine if we should notify for this tier.

    Uses a state file to avoid re-notifying for the same tier within
    the same day. State resets each day.

    Tiers:
      'warning' — fires when usage crosses 10% of the day's threshold
      'breach'  — fires when usage crosses the day's threshold
    """
    state_path = os.path.join(SCRIPT_DIR, "notify_state.json")
    today_str = datetime.date.today().isoformat()

    try:
        with open(state_path, "r") as f:
            state = json.load(f)
    except Exception:
        state = {}

    # Reset state if it's a new day
    if state.get("date") != today_str:
        state = {"date": today_str, "notified": []}

    notified = state.get("notified", [])

    if tier in notified:
        return False

    if tier == "warning":
        warning_level = threshold_pct * 0.10  # 10% of the threshold
        if usage_pct >= warning_level:
            notified.append("warning")
            state["notified"] = notified
            _save_state(state_path, state)
            return True
    elif tier == "breach":
        if usage_pct >= threshold_pct:
            notified.append("breach")
            state["notified"] = notified
            _save_state(state_path, state)
            return True

    return False


def _save_state(path, state):
    try:
        with open(path, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def main():
    dry_run = "--dry-run" in sys.argv
    force_toast = "--test-toast" in sys.argv
    fire_toast_mode = "--fire-toast" in sys.argv

    # --- Direct toast firing mode (called by fire_toast_detached) ---
    if fire_toast_mode:
        # Args: --fire-toast <title> <body> [scenario]
        idx = sys.argv.index("--fire-toast")
        title = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "Claude Usage Monitor"
        body = sys.argv[idx + 2] if idx + 2 < len(sys.argv) else ""
        scenario = sys.argv[idx + 3] if idx + 3 < len(sys.argv) else "urgent"
        fire_toast(title, body, scenario)
        return

    # --- Load config ---
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        log(f"ERROR loading config: {e}")
        config = {"divisor": 70, "weekly_token_cap": 50000000}

    day_idx = get_day_index()
    threshold = get_threshold(config)
    threshold_pct = threshold * 100
    warning_pct = threshold_pct * 0.10  # 10% of the day's threshold

    # --- Dry run ---
    if dry_run:
        week_start, week_end = get_week_bounds()
        log(f"DRY RUN — Day {day_idx}/7, week: {week_start} to {week_end}")
        log(f"  divisor={config.get('divisor')}")
        log(f"  threshold={threshold_pct:.2f}%, warning={warning_pct:.2f}%")
        total_tokens, usage_pct = get_usage_percent(config)
        log(f"  tokens this week: {total_tokens:,}, cap: {config.get('weekly_token_cap', '?'):,}")
        log(f"  usage: {usage_pct:.2f}%")
        if usage_pct >= warning_pct:
            log(f"  WOULD FIRE WARNING: usage {usage_pct:.2f}% >= warning {warning_pct:.2f}%")
        if usage_pct >= threshold_pct:
            log(f"  WOULD FIRE BREACH: usage {usage_pct:.2f}% >= threshold {threshold_pct:.2f}%")
        return

    # --- Test toast ---
    if force_toast:
        log("TEST TOAST — forcing persistent notification")
        fire_toast(
            "Claude Usage Monitor",
            "TEST: You've used 80.8% of your weekly allowance. "
            "Today's budget is 10.0% (Day 7/7). "
            "Click to dismiss — this is what real alerts will look like.",
            scenario="urgent"
        )
        log("Test toast dismissed by user.")
        return

    # --- Normal run ---
    total_tokens, usage_pct = get_usage_percent(config)

    log(f"Day {day_idx}/7, threshold={threshold_pct:.2f}%, warning={warning_pct:.2f}%, "
        f"usage={usage_pct:.2f}% ({total_tokens:,} tokens)")

    # Write refresh signal for the desktop widget (if running)
    try:
        with open(os.path.join(SCRIPT_DIR, "widget_refresh.tmp"), "w") as f:
            f.write("1")
    except Exception:
        pass

    # Check tiers: warning first, then breach
    # Only fire one per run (breach takes priority if both crossed)
    fired = False

    if should_notify("breach", usage_pct, threshold_pct, config):
        msg = (
            f"You've used {usage_pct:.1f}% of your weekly allowance — "
            f"that's over today's budget of {threshold_pct:.1f}% (Day {day_idx}/7). "
            f"Slow down to keep access all week."
        )
        log(f"BREACH — firing persistent toast: {msg}")
        fire_toast_detached("Claude Budget Breach", msg, "urgent")
        fired = True
    elif should_notify("warning", usage_pct, threshold_pct, config):
        msg = (
            f"You've used {usage_pct:.1f}% of your weekly allowance. "
            f"Today's budget is {threshold_pct:.1f}% (Day {day_idx}/7) — "
            f"you're approaching the limit."
        )
        log(f"WARNING — firing persistent toast: {msg}")
        fire_toast_detached("Claude Budget Warning", msg, "urgent")
        fired = True

    if not fired:
        log(f"OK — usage {usage_pct:.1f}% within bounds (warning={warning_pct:.1f}%, threshold={threshold_pct:.1f}%)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"UNHANDLED ERROR: {e}")
        log(traceback.format_exc())
        sys.exit(0)
