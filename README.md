# Claude Usage Monitor

Monitors your **Claude Code** (Pro/Max) weekly token usage against a prorated daily budget. Fires persistent Windows Toast notifications on budget breach, plus an always-on-top desktop widget showing live usage %.

## How It Works

- **Week runs Saturday (Day 1) through Friday (Day 7)**
- Saturday: you may use up to 1/7 of your weekly allowance
- Sunday: up to 2/7 (even if Saturday was unused)
- ... Friday: up to 7/7
- If cumulative usage exceeds the day's threshold → **persistent toast** (stays until you click it)

## Features

- 📊 **Desktop widget** — small borderless always-on-top window showing daily allowance % used (green/yellow/red) + weekly %
- 🔔 **Toast notifications** — gentle chime, stays on screen until dismissed
  - **Warning** at 10% of the day's threshold
  - **Breach** at the day's threshold
- ⚡ **Event-driven** — fires on every Claude Code response via the `Stop` hook (no polling)
- 🚫 **No pop-up windows** — uses `pythonw.exe` (no console subsystem)
- 📅 **Once-per-day dedup** — won't re-notify for the same tier on the same day

## Quick Start

### Prerequisites
- Python 3.11+ with `pythonw.exe`
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Windows 10/11

### Install

```bash
# 1. Clone
git clone https://github.com/onecoded/claude-usage-monitor.git
cd claude-usage-monitor

# 2. Install toast dependency
pip install win11toast

# 3. Copy config
cp config.example.json config.json
# Edit config.json: set weekly_token_cap, claude_projects_dir

# 4. Register the Stop hook in ~/.claude/settings.json
# Add to "hooks" section:
#   "Stop": [{"hooks": [{"type": "command", "command": "C:\\path\\to\\pythonw.exe C:\\path\\to\\claude_usage_monitor.py", "timeout": 15}]}]

# 5. Test
python claude_usage_monitor.py --dry-run
python claude_usage_monitor.py --test-toast

# 6. Launch widget
pythonw claude_usage_widget.pyw
```

### Auto-start with Windows (Task Scheduler)

```powershell
# Monitor (runs on every Claude Code response — no task needed)
# Widget (runs at logon):
$action = New-ScheduledTaskAction -Execute "C:\path\to\pythonw.exe" -Argument "C:\path\to\claude_usage_widget.pyw"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "ClaudeUsageWidget-Startup" -Action $action -Trigger $trigger -Force
```

## Config

| Field | Default | Description |
|---|---|---|
| `divisor` | `7` | Daily threshold = day_index / divisor. Use `70` for 10x stricter testing. |
| `weekly_token_cap` | `50000000` | Your weekly token allowance. Adjust to match your subscription. |
| `week_start_day` | `saturday` | First day of the usage week |
| `claude_projects_dir` | `~/.claude/projects` | Where Claude Code stores session JSONL files |

## Claude Code Slash Command

Create `~/.claude/commands/budget.md`:
```
Run the usage monitor and show the output:
C:\path\to\python.exe C:\path\to\claude_usage_monitor.py --dry-run
```

Then type `/budget` in Claude Code to see your current usage.

## Day-of-Week Threshold Table (divisor=7)

| Day | Day Index | Threshold |
|---|---|---|
| Saturday | 1 | 14.3% |
| Sunday | 2 | 28.6% |
| Monday | 3 | 42.9% |
| Tuesday | 4 | 57.1% |
| Wednesday | 5 | 71.4% |
| Thursday | 6 | 85.7% |
| Friday | 7 | 100.0% |

## Files

- `claude_usage_monitor.py` — Core monitor (runs via Stop hook, fires toasts)
- `claude_usage_widget.pyw` — Desktop widget (always-on-top, live usage %)
- `config.example.json` — Sample config (copy to `config.json`)
- `SKILL.md` — Full Hermes Agent skill spec

## Widget Controls

- **Drag** — click and drag to move
- **Right-click** — close
- **Color** — green (<80%), yellow (80-100%), red (>100%) of daily allowance

## License

MIT