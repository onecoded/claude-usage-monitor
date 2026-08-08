#!/usr/bin/env pythonw
"""
DOES:   Always-on-top desktop widget showing Claude Code daily allowance %.
        Big number = daily % used (green/yellow/red). Small = weekly %.
        On top of Claude Code app windows specifically.
IN-OUT: Reads config.json + session transcripts. Refreshes on 10s timer
        and instantly when Stop hook writes widget_refresh.tmp.
RUN:    pythonw.exe claude_usage_widget.pyw  (no console window)
"""

import tkinter as tk
import datetime
import json
import os
import sys
import glob
import subprocess
import ctypes

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
REFRESH_SIGNAL = os.path.join(SCRIPT_DIR, "widget_refresh.tmp")

WEEK_MAP = {5: 1, 6: 2, 0: 3, 1: 4, 2: 5, 3: 6, 4: 7}

BG = "#1a1a2e"
FG = "#c0c0c0"
GREEN = "#4ecca3"
YELLOW = "#f0a500"
RED = "#e94560"
DIM = "#555"


def get_day_index():
    return WEEK_MAP[datetime.date.today().weekday()]


def get_week_bounds():
    today = datetime.date.today()
    days_since_sat = (today.weekday() - 5) % 7
    week_start = today - datetime.timedelta(days=days_since_sat)
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
    daily_pct = (usage_pct / threshold_pct * 100) if threshold_pct > 0 else 0
    return total_tokens, usage_pct, threshold_pct, daily_pct


class UsageWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Claude Usage")
        # Small borderless widget — width 160, height 80
        self.root.geometry("160x82+25+25")
        self.root.overrideredirect(True)
        # Topmost but we'll manage focus to be "on top of Claude" not everything
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.configure(bg=BG)

        # Drag handling
        self.drag_x = 0
        self.drag_y = 0
        self.root.bind("<Button-1>", self.start_drag)
        self.root.bind("<B1-Motion>", self.on_drag)
        self.root.bind("<Button-3>", lambda e: self.root.destroy())  # right-click = close

        # --- Layout: big daily % on top, small weekly below ---
        self.daily_label = tk.Label(
            self.root, text="...", font=("Consolas", 22, "bold"),
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
        self.weekly_label.pack(pady=(2, 4))

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
            total_tokens, usage_pct, threshold_pct, daily_pct = get_usage(config)
            day_idx = get_day_index()

            # Big number: daily allowance % used
            self.daily_label.config(text=f"{daily_pct:.0f}%")

            if daily_pct >= 100:
                color = RED
            elif daily_pct >= 80:
                color = YELLOW
            else:
                color = GREEN
            self.daily_label.config(fg=color)

            self.daily_sub.config(text=f"of Day {day_idx}/7 budget ({threshold_pct:.0f}%)")

            # Small: weekly %
            self.weekly_label.config(text=f"Weekly: {usage_pct:.1f}%")

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
