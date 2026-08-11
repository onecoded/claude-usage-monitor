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

# --- Day-of-week mapping: Friday=1 .. Thursday=7 ---
# datetime: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
WEEK_MAP = {
    4: 1,  # Friday    = Day 1
    5: 2,  # Saturday  = Day 2
    6: 3,  # Sunday    = Day 3
    0: 4,  # Monday    = Day 4
    1: 5,  # Tuesday   = Day 5
    2: 6,  # Wednesday = Day 6
    3: 7,  # Thursday  = Day 7
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
    """Return (friday, thursday) datetime objects for the current usage week."""
    today = datetime.date.today()
    # Friday is weekday 4; go back to the most recent Friday
    days_since_friday = (today.weekday() - 4) % 7
    week_start = today - datetime.timedelta(days=days_since_friday)
    week_end = week_start + datetime.timedelta(days=6)
    return week_start, week_end


def get_threshold(config):
    """Calculate the daily prorated cumulative threshold: day_index / divisor of weekly cap."""
    day_idx = get_day_index()
    divisor = config.get("divisor", 7)
    return day_idx / divisor


def compute_daily_pct(config):
    """
    NEW DAILY %: today's tokens / remaining budget available today.
    - Remaining budget = max(0, cumulative_threshold_tokens - prior_days_tokens)
      where prior_days_tokens = tokens used before today this week.
    - Starts at 0% every morning. Goes up as you use tokens today.
    - If you blew past the cumulative threshold before today, 
      remaining_budget = 0 → daily_pct caps at 999%.
    Returns (daily_pct, today_tokens, remaining_budget_tokens).
    """
    weekly_cap = config.get("weekly_token_cap", 50000000)
    threshold_pct = get_threshold(config)
    cumulative_threshold = int(weekly_cap * threshold_pct)

    # Get today's tokens + prior days' tokens
    today_tokens = get_today_tokens(config)
    total_weekly, _ = get_usage_percent(config)
    prior_tokens = total_weekly - today_tokens

    remaining_budget = max(0, cumulative_threshold - prior_tokens)

    if remaining_budget > 0:
        daily_pct = (today_tokens / remaining_budget * 100)
    elif today_tokens > 0:
        daily_pct = 999  # Already blew past every budget — show max
    else:
        daily_pct = 0

    return daily_pct, today_tokens, remaining_budget


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


def get_hourly_pct(config):
    """Return % of weekly cap consumed in the last hour."""
    projects_dir = config.get("claude_projects_dir", os.path.expanduser("~/.claude/projects"))
    weekly_cap = config.get("weekly_token_cap", 50000000)
    one_hour_ago = datetime.datetime.now() - datetime.timedelta(hours=1)

    total_tokens = 0
    for jsonl_path in glob.glob(os.path.join(projects_dir, "*", "*.jsonl")):
        try:
            if datetime.datetime.fromtimestamp(os.path.getmtime(jsonl_path)) < one_hour_ago:
                continue
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("type") != "assistant":
                            continue
                        ts_str = entry.get("timestamp", "")
                        if not ts_str:
                            continue
                        ts = datetime.datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                        if ts < one_hour_ago:
                            continue
                        usage = entry.get("message", {}).get("usage", {})
                        if not usage:
                            continue
                        total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            continue

    return (total_tokens / weekly_cap * 100) if weekly_cap > 0 else 0


def get_today_tokens(config):
    """Return tokens consumed today only (since midnight)."""
    projects_dir = config.get("claude_projects_dir", os.path.expanduser("~/.claude/projects"))
    now_local = datetime.datetime.now()
    midnight = datetime.datetime(now_local.year, now_local.month, now_local.day)
    # Convert to UTC for comparison (HST = UTC-10)
    midnight_utc = midnight + datetime.timedelta(hours=10)

    total_tokens = 0
    for jsonl_path in glob.glob(os.path.join(projects_dir, "*", "*.jsonl")):
        try:
            if datetime.datetime.fromtimestamp(os.path.getmtime(jsonl_path)) < midnight:
                continue
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("type") != "assistant":
                            continue
                        ts_str = entry.get("timestamp", "")
                        if not ts_str:
                            continue
                        ts = datetime.datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                        if ts < midnight_utc:
                            continue
                        usage = entry.get("message", {}).get("usage", {})
                        if not usage:
                            continue
                        total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            continue

    return total_tokens


def get_5h_window(config):
    """Return (tokens_5h, prompts_5h, minutes_to_reset) for Claude Code's 5-hour rate limit."""
    projects_dir = config.get("claude_projects_dir", os.path.expanduser("~/.claude/projects"))
    # Timestamps in JSONL are UTC; local time is HST (UTC-10)
    # Convert local now to UTC for comparison
    now_local = datetime.datetime.now()
    now_utc = now_local + datetime.timedelta(hours=10)
    five_hours_ago_utc = now_utc - datetime.timedelta(hours=5)

    total_tokens = 0
    prompt_count = 0
    prompt_timestamps = []

    for jsonl_path in glob.glob(os.path.join(projects_dir, "*", "*.jsonl")):
        try:
            if datetime.datetime.fromtimestamp(os.path.getmtime(jsonl_path)) < (now_local - datetime.timedelta(hours=6)):
                continue
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        ts_str = entry.get("timestamp", "")
                        if not ts_str:
                            continue
                        ts = datetime.datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                        if ts < five_hours_ago_utc:
                            continue

                        if entry.get("type") == "user" and entry.get("message", {}).get("role") == "user":
                            prompt_count += 1
                            prompt_timestamps.append(ts)

                        if entry.get("type") == "assistant":
                            usage = entry.get("message", {}).get("usage", {})
                            if usage:
                                total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            continue

    if prompt_timestamps:
        sorted_timestamps = sorted(prompt_timestamps)
        # Find the most recent gap > 5 min between prompts — that's likely when
        # the rate limit reset and a new window started
        window_start = sorted_timestamps[0]
        for i in range(1, len(sorted_timestamps)):
            gap = (sorted_timestamps[i] - sorted_timestamps[i-1]).total_seconds()
            if gap > 300:  # > 5 min gap
                window_start = sorted_timestamps[i]
        reset_utc = window_start + datetime.timedelta(hours=5)
        minutes_to_reset = max(0, (reset_utc - now_utc).total_seconds() / 60)
    else:
        minutes_to_reset = 0

    return total_tokens, prompt_count, minutes_to_reset


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


def should_notify(tier, daily_pct, config):
    """
    Determine if we should notify for this tier.

    Uses a state file to avoid re-notifying for the same tier within
    the same day. State resets each day.

    Tiers:
      'yellow'   — fires when daily allowance hits 60%
      'red'      — fires when daily allowance hits 80%
      'breach'   — fires when daily allowance hits 100% (writes throttle flag)
      'critical' — fires when daily allowance hits 125% (alarm + throttle flag)
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

    if tier == "yellow":
        if daily_pct >= 60:
            notified.append("yellow")
            state["notified"] = notified
            _save_state(state_path, state)
            return True
    elif tier == "red":
        if daily_pct >= 80:
            notified.append("red")
            state["notified"] = notified
            _save_state(state_path, state)
            return True
    elif tier == "breach":
        if daily_pct >= 100:
            notified.append("breach")
            state["notified"] = notified
            _save_state(state_path, state)
            return True
    elif tier == "critical":
        if daily_pct >= 125:
            notified.append("critical")
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
    refresh_mode = "--refresh" in sys.argv

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
    daily_pct, today_tokens, remaining_budget = compute_daily_pct(config)
    threshold_pct = threshold * 100

    log(f"Day {day_idx}/7, threshold={threshold_pct:.2f}%, weekly={usage_pct:.2f}% "
        f"({total_tokens:,} tokens), daily={daily_pct:.0f}%, "
        f"remaining_budget={remaining_budget:,}")

    # Write refresh signal for the desktop widget (if running)
    try:
        with open(os.path.join(SCRIPT_DIR, "widget_refresh.tmp"), "w") as f:
            f.write("1")
    except Exception:
        pass

    # Write usage.json for the web dashboard
    try:
        weekly_cap = config.get("weekly_token_cap", 50000000)
        hourly_pct = get_hourly_pct(config)
        hourly_tokens = int(weekly_cap * hourly_pct / 100)
        tokens_5h, prompts_5h, minutes_to_reset = get_5h_window(config)
        today_tokens_val = get_today_tokens(config)
        today_pct = (today_tokens_val / weekly_cap * 100) if weekly_cap > 0 else 0
        threshold_tokens = int(weekly_cap * threshold_pct / 100)
        remaining_today_tokens = remaining_budget - today_tokens_val
        remaining_today_pct = max(0, 100 - daily_pct)

        # Time to limit: how many hours until daily_pct hits 100%
        if hourly_pct > 0 and daily_pct < 100 and remaining_budget > 0:
            tokens_left = max(0, remaining_budget - today_tokens_val)
            hourly_tokens_rate = max(1, int(weekly_cap * hourly_pct / 100))
            hours_to_limit = tokens_left / hourly_tokens_rate
        else:
            hours_to_limit = 0 if daily_pct < 100 else 0

        usage_data = {
            "daily_pct": daily_pct,
            "usage_pct": usage_pct,
            "threshold_pct": threshold_pct,
            "day_index": day_idx,
            "hourly_pct": hourly_pct,
            "hourly_tokens": hourly_tokens,
            "tokens_5h": tokens_5h,
            "prompts_5h": prompts_5h,
            "minutes_to_reset": minutes_to_reset,
            "today_tokens": today_tokens,
            "today_pct": today_pct,
            "total_tokens": total_tokens,
            "weekly_cap": weekly_cap,
            "remaining_today_tokens": remaining_today_tokens,
            "remaining_today_pct": remaining_today_pct,
            "hours_to_limit": hours_to_limit,
            "weekly_remaining_tokens": max(0, int(weekly_cap - total_tokens)),
            "timestamp": datetime.datetime.now().isoformat()
        }
        with open(os.path.join(SCRIPT_DIR, "scripts", "usage.json"), "w") as f:
            json.dump(usage_data, f)
    except Exception:
        pass

    # Check tiers: breach > red > yellow (only fire one per run, highest priority)
    fired = False

    if should_notify("critical", daily_pct, config):
        msg = (
            f"CRITICAL: {daily_pct:.0f}% of today's remaining budget used "
            f"(Day {day_idx}/7). You're 25% OVER the daily allowance. "
            f"Switch to Haiku or pause until tomorrow."
        )
        log(f"CRITICAL — firing blocking alarm toast: {msg}")
        fire_toast_detached("Claude Budget CRITICAL — Over Limit", msg, "alarm")
        # Write throttle flag to disk
        try:
            with open(os.path.join(SCRIPT_DIR, "throttle.flag"), "w") as f:
                f.write(str(daily_pct))
        except Exception:
            pass
        fired = True
    elif should_notify("breach", daily_pct, config):
        msg = (
            f"You've used {daily_pct:.0f}% of today's remaining budget "
            f"(Day {day_idx}/7). Weekly: {usage_pct:.1f}%. "
            f"Consider switching to /model haiku to preserve allowance."
        )
        log(f"BREACH — firing toast: {msg}")
        fire_toast_detached("Claude Budget Breach", msg, "urgent")
        # Write throttle suggestion
        try:
            with open(os.path.join(SCRIPT_DIR, "throttle.flag"), "w") as f:
                f.write(str(daily_pct))
        except Exception:
            pass
        fired = True
    elif should_notify("red", daily_pct, config):
        msg = (
            f"You've used {daily_pct:.0f}% of today's remaining budget "
            f"(Day {day_idx}/7). Weekly: {usage_pct:.1f}%. "
            f"Almost at the daily limit — slow down."
        )
        log(f"RED — firing toast: {msg}")
        fire_toast_detached("Claude Budget — 80% Used", msg, "urgent")
        fired = True
    elif should_notify("yellow", daily_pct, config):
        msg = (
            f"You've used {daily_pct:.0f}% of today's remaining budget "
            f"(Day {day_idx}/7). Weekly: {usage_pct:.1f}%. "
            f"Pacing OK — just a heads up."
        )
        log(f"YELLOW — firing toast: {msg}")
        fire_toast_detached("Claude Budget — 60% Used", msg, "urgent")
        fired = True

    if not fired:
        log(f"OK — daily {daily_pct:.0f}% (yellow=60%, red=80%, breach=100%)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"UNHANDLED ERROR: {e}")
        log(traceback.format_exc())
        sys.exit(0)
