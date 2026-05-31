# Claude Project

A collection of AI engineering projects built while learning to work with Claude and the Anthropic API.

---

## Projects in this repo

| Project | Description |
|---|---|
| [macOS AI Ops Dashboard](#macos-ai-ops-dashboard) | Automated macOS health scanner powered by Claude AI |
| [Python Learning Projects](python-learning/README.md) | Weekly learning projects: ServiceNow, ticket classification, self-improving agent |
| [Otto](otto/README.md) | Two-page SaaS marketing mockup — pure HTML/CSS/JS |

---

## macOS AI Ops Dashboard

Automated macOS health scanner that collects system metrics, sends them to Claude for analysis, and publishes a prioritised recommendations dashboard to GitHub Pages.

### Features

- **4 Scan Modes** — `all`, `dev`, `vulnerability`, `ui`
- **Claude AI Analysis** — `claude-sonnet-4-6` with prompt caching to reduce token costs
- **Rollback Agent** — snapshots system state before any cleanup so you can restore if something breaks
- **Post-Cleanup Checker** — verifies 6 health dimensions after cleanup (CPU, memory, disk, DNS, services, app integrity)
- **GitHub Pages** — dashboard auto-published to `docs/index.html` via GitHub Actions

### Quick start

```bash
# Install dependencies
pip3 install -r requirements.txt

# Copy and fill in your API key
cp .env.example .env

# Full scan (all collectors, opens dashboard)
python3 main.py

# Skip Claude AI (no API key needed)
python3 main.py --no-ai

# Security audit mode
python3 main.py --mode vulnerability

# Developer mode — build artifacts, node_modules, IDE processes
python3 main.py --mode dev

# Post-cleanup health check only
python3 main.py --post-check
```

### Rollback

```bash
# List available snapshots
python3 main.py --list-snapshots

# Restore from snapshot
python3 main.py --rollback 2026-04-20_143022

# Purge snapshot after confirming all is well
python3 main.py --purge 2026-04-20_143022
```

### Scan modes

| Mode | What it focuses on |
|---|---|
| `all` | Full scan — CPU, memory, disk, security, startup apps |
| `dev` | Developer tools: node_modules, build artifacts, IDE processes |
| `vulnerability` | Security audit: exposed files, open ports, SIP, FileVault |
| `ui` | Visual dashboard only, no cleanup suggestions |

### Architecture

```
main.py                     ← entry point (argparse, wires all modules)
├── router/
│   ├── skill_router.py     ← selects which collectors run per mode
│   └── profiles/           ← JSON config per mode (all / dev / ui / vulnerability)
├── collectors/
│   ├── cpu_memory.py       ← CPU %, memory, swap, load average
│   ├── disk_storage.py     ← disk usage, large files, old artifacts
│   ├── startup_apps.py     ← launch agents, login items
│   └── security.py         ← SIP status, FileVault, open ports, file permissions
├── analyzer/
│   └── claude_analyzer.py  ← sends scan JSON to Claude, returns scored suggestions
├── dashboard/
│   └── generator.py        ← Jinja2 → docs/index.html (GitHub Pages)
├── agents/
│   ├── monitoring_agent.py    ← polls metrics continuously, fires alerts
│   ├── remediation_agent.py   ← applies safe fixes with rollback support
│   ├── report_agent.py        ← generates markdown/HTML reports
│   └── scheduled_scan_agent.py ← wraps main scan for cron/CI
├── rollback/
│   └── rollback_agent.py   ← snapshot, restore, purge
├── post_check/
│   └── health_checker.py   ← post-cleanup verification (6 checks)
├── data/                   ← scan output JSON
└── docs/                   ← generated dashboard HTML (served via GitHub Pages)
```

### GitHub Pages setup

1. Push this repo to GitHub
2. Go to **Settings → Pages → Source** and set it to the `docs/` folder
3. Add `ANTHROPIC_API_KEY` to **Settings → Secrets → Actions**
4. The workflow at `.github/workflows/scan.yml` runs a full scan daily at 8 AM UTC

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Claude API access |
| `AI_OPS_MODEL` | `claude-sonnet-4-6` | Claude model to use |
| `AI_OPS_MODE` | `all` | Default scan mode |
| `AI_OPS_OUTPUT_DIR` | `docs` | HTML dashboard output directory |
| `AI_OPS_DATA_DIR` | `data` | Scan JSON output directory |

---

## Repository structure

```
.
├── main.py                         ← AI Ops entry point
├── requirements.txt
├── agents/                         ← monitoring, remediation, report, scheduled scan
├── analyzer/                       ← Claude AI integration
├── collectors/                     ← system metric collectors
├── dashboard/                      ← HTML dashboard generator
├── post_check/                     ← post-cleanup health verifier
├── rollback/                       ← snapshot & restore
├── router/                         ← mode-based collector routing
├── data/                           ← scan output data
├── docs/                           ← generated dashboard (GitHub Pages)
├── python-learning/                ← weekly Python + AI learning projects
│   ├── week2_servicenow_fetcher.py
│   ├── week3_ticket_classifier.py
│   ├── week5_agent.py
│   └── README.md
├── otto/                           ← SaaS marketing web mockup
│   ├── index.html
│   └── README.md
└── design-grill-extracted/         ← Clean Architecture + DDD reference notes
```

---

## Security

Secrets are kept in `.env` (gitignored). The `.env.example` file shows all required variable names with no values. Never commit `.env` or `.mcp.json`.
