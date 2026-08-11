#!/usr/bin/env pythonw
"""
DOES:   Always-on-top desktop widget showing Claude Code daily allowance %.
        Big number = daily % used (green/yellow/red). Small = weekly %.
RUN:    pythonw.exe claude_usage_widget.pyw  (no console window)
"""

import tkinter as tk
import datetime
import json
import os
import sys
import glob

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
REFRESH_SIGNAL = os.path.join(SCRIPT_DIR, "widget_refresh.tmp")

WEEK_MAP = {4: 1, 5: 2, 6: 3, 0: 4, 1: 5, 2: 6, 3: 7}

BG = "#1a1a2e"
FG = "#c0c0c0"
GREEN = "#4ecca3"
YELLOW = "#f0a500"
RED = "#e94560"
DIM = "#555"


def get_day_index():
    return WEEK_MAP[datetime.date.today().weekday()]

def get_week_bounds():
    """Return (friday, thursday) datetime objects for the current usage week."""
    today = datetime.date.today()
    # Friday is weekday 4; go back to the most recent Friday
    days_since_friday = (today.weekday() - 4) % 7
    week_start = today - datetime.timedelta(days=days_since_friday)
    week_end = week_start + datetime.timedelta(days=6)
    return week_start, week_end


def get_usage(config):
    projects_dir = config.get("claude_projects_dir", os.path.expanduser("~/.claude/projects"))
    weekly_cap = config.get("weekly_token_cap", 50000000)
    divisor = config.get("divisor", 7)

    day_idx = get_day_index()
    threshold_pct = day_idx / divisor * 100

    week_start, week_end = get_week_bounds()
    ws_dt = datetime.datetime(week_start.year, week_start.month, week_start.day)
    we_dt = datetime.datetime(week_end.year, week_end.month, week_end.day, 23, 59, 59)

    total_in = 0
    total_out = 0

    for jsonl_path in glob.glob(os.path.join(projects_dir, "*", "*.jsonl")):
        try:
            if datetime.datetime.fromtimestamp(os.path.getmtime(jsonl_path)) < ws_dt:
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
                                if ts < ws_dt or ts > we_dt:
                                    continue
                            except Exception:
                                pass
                        usage = entry.get("message", {}).get("usage", {})
                        if not usage:
                            continue
                        total_in += usage.get("input_tokens", 0)
                        total_out += usage.get("output_tokens", 0)
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            continue

    total_tokens = total_in + total_out
    usage_pct = (total_tokens / weekly_cap * 100) if weekly_cap > 0 else 0

    # NEW daily pct: today's tokens / remaining budget available today
    cumulative_threshold = int(weekly_cap * day_idx / divisor)
    # Count today's tokens from the already-parsed data
    today_in = sum(line_data.get('in', 0) for line_data in today_lines) if today_lines else 0
    today_out = sum(line_data.get('out', 0) for line_data in today_lines) if today_lines else 0
    today_tokens = today_in + today_out
    prior_tokens = total_tokens - today_tokens
    remaining_budget = max(0, cumulative_threshold - prior_tokens)
    daily_pct = (today_tokens / remaining_budget * 100) if remaining_budget > 0 else (999 if today_tokens > 0 else 0)

    # Tokens consumed in the last hour
    one_hour_ago = datetime.datetime.now() - datetime.timedelta(hours=1)
    hourly_in = 0
    hourly_out = 0

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
                        try:
                            ts = datetime.datetime.fromisoformat(
                                ts_str.replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                            if ts < one_hour_ago:
                                continue
                        except Exception:
                            continue
                        usage = entry.get("message", {}).get("usage", {})
                        if not usage:
                            continue
                        hourly_in += usage.get("input_tokens", 0)
                        hourly_out += usage.get("output_tokens", 0)
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            continue

    hourly_tokens = hourly_in + hourly_out
    hourly_pct = (hourly_tokens / weekly_cap * 100) if weekly_cap > 0 else 0

    return total_tokens, usage_pct, threshold_pct, daily_pct, hourly_pct


class UsageWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Claude Usage")
        self.root.geometry("170x105+25+25")
        self.root.minsize(170, 105)
        self.root.maxsize(170, 105)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.drag_x = 0
        self.drag_y = 0

        # --- Layout ---
        self.daily_label = tk.Label(
            self.root, text="...", font=("Consolas", 24, "bold"),
            bg=BG, fg=GREEN
        )
        self.daily_label.pack(pady=(6, 0))

        self.daily_sub = tk.Label(
            self.root, text="daily allowance", font=("Segoe UI", 7),
            bg=BG, fg=DIM
        )
        self.daily_sub.pack()

        self.weekly_label = tk.Label(
            self.root, text="", font=("Segoe UI", 8),
            bg=BG, fg=FG
        )
        self.weekly_label.pack(pady=(1, 0))

        self.burn_label = tk.Label(
            self.root, text="", font=("Segoe UI", 7),
            bg=BG, fg=DIM
        )
        self.burn_label.pack(pady=(0, 4))

        # Bind drag + right-click to all widgets
        all_widgets = [self.root, self.daily_label, self.daily_sub,
                       self.weekly_label, self.burn_label]
        for w in all_widgets:
            w.bind("<Button-1>", self.start_drag)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<Button-3>", lambda e: self.root.destroy())

        self.update_usage()
        self.check_refresh()

    def start_drag(self, event):
        self.drag_x = event.x
        self.drag_y = event.y

    def on_drag(self, event):
        x = self.root.winfo_x() + event.x - self.drag_x
        y = self.root.winfo_y() + event.y - self.drag_y
        self.root.geometry(f"+{x}+{y}")

    def update_usage(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
            total_tokens, usage_pct, threshold_pct, daily_pct, hourly_pct = get_usage(config)
            day_idx = get_day_index()

            self.daily_label.config(text=f"{daily_pct:.0f}%")

            if daily_pct >= 80:
                color = RED
            elif daily_pct >= 60:
                color = YELLOW
            else:
                color = GREEN
            self.daily_label.config(fg=color)

            self.daily_sub.config(text=f"of Day {day_idx}/7 budget ({threshold_pct:.0f}%)")
            self.weekly_label.config(text=f"Weekly: {usage_pct:.1f}%")
            self.burn_label.config(text=f"Last hr: {hourly_pct:.1f}%/hr")

        except Exception as e:
            self.daily_label.config(text="Err")
            self.daily_sub.config(text=str(e)[:25])

        self.root.after(10000, self.update_usage)

    def check_refresh(self):
        try:
            if os.path.exists(REFRESH_SIGNAL):
                os.remove(REFRESH_SIGNAL)
                self.update_usage()
        except Exception:
            pass
        self.root.after(2000, self.check_refresh)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    UsageWidget().run()