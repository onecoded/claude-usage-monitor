# Claude Usage Monitor

Monitors your **Claude Code** (Pro/Max) weekly token usage against a prorated daily budget. Fires persistent Windows Toast notifications on budget breach, plus a beautiful Chrome dashboard with live usage %, 5-hour rate window, weekly breakdown, and a prompt template library.

## Features

- 📊 **Chrome Dashboard** — Matrix-inspired dark theme with glassmorphism cards, animated counters, breathing glow, scan-line effect
- 🧮 **Token Clock** — big daily allowance % (green/yellow/red), auto-refreshes every 3 seconds
- 📈 **Progress Bars** — today's budget + weekly allowance with glowing "today" overlay
- ⏱️ **5-Hour Rate Window** — tracks Claude Code's rolling 5h rate limit with reset countdown
- 📋 **Weekly Breakdown** — day-by-day table showing allowed tokens vs actual usage
- 🔔 **Toast Notifications** — gentle chime, stays on screen until you click to dismiss
  - Yellow at 60% of daily allowance
  - Red at 80%
  - Breach at 100%
- 📚 **Prompt Library** — 27 prompt templates (prom0-4, OPUS1-4, SONNET1-4, FABLE1-4, HAIKU1-4, DEEP1-3) with one-click copy to clipboard
- 🎨 **Dark/Light Mode** — toggle in header, remembers your choice
- ⚙️ **Settings Panel** — configure projects dir, weekly cap, week start day, alert thresholds, theme
- 🖥️ **Desktop Widget** — small always-on-top floating window
- ⚡ **Event-Driven** — fires on every Claude Code response via Stop hook (no polling)
- 🚫 **No Pop-up Windows** — uses `pythonw.exe` (no console subsystem)
- 📱 **Mobile Responsive** — works on phone screens, PWA-capable

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
```

### Configure Claude Code Hooks

Edit `~/.claude/settings.json` and add these hooks:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "C:\\path\\to\\pythonw.exe C:\\path\\to\\claude_usage_monitor.py",
            "timeout": 15
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cmd.exe /c start \"\" \"http://127.0.0.1:7871/\"",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### Hooks Explained

| Hook | When it fires | What it does |
|---|---|---|
| `Stop` | After every Claude Code response | Runs the usage monitor, checks budget, fires toast on breach, writes `usage.json` for the dashboard |
| `SessionStart` | When you launch Claude Code | Opens the Chrome dashboard at `http://127.0.0.1:7871/` automatically |

### Launch the Dashboard Server

```bash
# Start the HTTP server (serves dashboard on port 7871)
pythonw dashboard_server.pyw

# Or run it in the foreground for debugging
python dashboard_server.pyw
```

Then open `http://127.0.0.1:7871/` in Chrome.

### Auto-Start with Windows (Task Scheduler)

```powershell
# Dashboard server (starts at logon)
$action = New-ScheduledTaskAction -Execute "C:\path\to\pythonw.exe" -Argument "C:\path\to\dashboard_server.pyw"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "ClaudeUsageDashboard-Startup" -Action $action -Trigger $trigger -Force

# Desktop widget (starts at logon)
$action2 = New-ScheduledTaskAction -Execute "C:\path\to\pythonw.exe" -Argument "C:\path\to\claude_usage_widget.pyw"
Register-ScheduledTask -TaskName "ClaudeUsageWidget-Startup" -Action $action2 -Trigger $trigger -Force
```

### Test

```bash
# Dry run (see your current usage without firing toasts)
python claude_usage_monitor.py --dry-run

# Test toast notification
python claude_usage_monitor.py --test-toast
```

### Claude Code Slash Command

Create `~/.claude/commands/budget.md`:
```
Run the usage monitor and show the output:
C:\path\to\python.exe C:\path\to\claude_usage_monitor.py --dry-run
```

Then type `/budget` in Claude Code to see your current usage.

## Config

| Field | Default | Description |
|---|---|---|
| `divisor` | `7` | Daily threshold = day_index / divisor. Use `70` for 10x stricter testing. |
| `weekly_token_cap` | `50000000` | Your weekly token allowance |
| `week_start_day` | `friday` | First day of the usage week |
| `claude_projects_dir` | `~/.claude/projects` | Where Claude Code stores session JSONL files |

## Day-of-Week Threshold Table (divisor=7)

| Day | Day Index | Threshold |
|---|---|---|
| Friday | 1 | 14.3% |
| Saturday | 2 | 28.6% |
| Sunday | 3 | 42.9% |
| Monday | 4 | 57.1% |
| Tuesday | 5 | 71.4% |
| Wednesday | 6 | 85.7% |
| Thursday | 7 | 100.0% |

## Dashboard Settings

Click the gear icon (top-right) to open the settings panel:

- **Claude Projects Directory** — path to `~/.claude/projects`
- **Weekly Token Cap** — your weekly allowance
- **Week Starts On** — Friday, Saturday, Sunday, or Monday
- **Yellow Alert %** — when the daily % turns yellow (default 60)
- **Red Alert %** — when the daily % turns red (default 80)
- **Theme** — Matrix Deep (dark) or Light

Click the sun/moon icon (top-left) to toggle dark/light mode.

## Prompt Library

The dashboard includes 27 prompt templates organized by model tier:

| Tier | Prompts | Purpose |
|---|---|---|
| **Core** | prom0, prom, prom1, S0-S4 | General workflow: debugging, rulings, ingestion, architecture, execution, release, wrap-up |
| **Opus** | OPUS1-4 | Macro architecture: genesis, schema loop, handoff, wrap-up |
| **Sonnet** | SONNET1-4 | Core code engineering: genesis, build loop, handoff, wrap-up |
| **Fable** | FABLE1-4 | CLI execution: genesis, build loop, handoff, wrap-up |
| **Haiku** | HAIKU1-4 | Fast utility: triage, syntax repair, formatting, documentation |
| **DeepSeek** | DEEP1-3 | Local inference ($0 cost): genesis, build loop, vault sync |

Click any prompt card to copy the full template to your clipboard. Use the search bar and tier filter buttons to find what you need.

## Files

- `claude_usage_monitor.py` — Core monitor (runs via Stop hook, fires toasts, writes usage.json)
- `claude_usage_widget.pyw` — Desktop widget (always-on-top, live usage %)
- `dashboard_server.pyw` — HTTP server for the Chrome dashboard (port 7871)
- `dashboard.html` — The dashboard UI (Matrix-inspired, dark/light mode, prompt library)
- `prompts.json` — 27 prompt templates for the library
- `config.example.json` — Sample config (copy to `config.json`)
- `usage.json` — Generated runtime data (gitignored)

## Widget Controls

- **Drag** — click and drag to move
- **Right-click** — close
- **Color** — green (<60%), yellow (60-80%), red (>80%) of daily allowance

## License

MIT