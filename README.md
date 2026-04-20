# macOS AI Ops Dashboard

Automated macOS health scanner powered by Claude AI. Collects system metrics, generates AI-powered recommendations, and publishes a dashboard to GitHub Pages.

## Features

- **4 Skill Modes** — `all`, `dev`, `vulnerability`, `ui`
- **AI Analysis** — Claude API (claude-sonnet-4-6) with prompt caching
- **Rollback Agent** — snapshot state before cleanup, restore if something breaks
- **Post-Cleanup Checker** — verifies 6 system health dimensions after any cleanup
- **GitHub Pages** — auto-published dashboard at `docs/index.html`

## Quick Start

```bash
# Install dependencies
pip3 install -r requirements.txt

# Copy and fill in your API key
cp .env.example .env

# Full scan (opens dashboard)
python3 main.py

# Skip AI analysis (no API key needed)
python3 main.py --no-ai

# Security audit mode
python3 main.py --mode vulnerability

# Developer mode (focuses on build artifacts)
python3 main.py --mode dev

# Post-cleanup health check
python3 main.py --post-check
```

## Rollback

```bash
# List available snapshots
python3 main.py --list-snapshots

# Restore from snapshot
python3 main.py --rollback 2026-04-20_143022

# Purge snapshot after confirming all is well
python3 main.py --purge 2026-04-20_143022
```

## Modes

| Mode | Focus |
|---|---|
| `all` | Full scan — CPU, memory, disk, security, startup |
| `dev` | Developer tools: node_modules, build artifacts, IDE processes |
| `vulnerability` | Security audit: exposed files, ports, SIP, FileVault |
| `ui` | Visual dashboard only, no cleanup suggestions |

## GitHub Pages Setup

1. Push this repo to GitHub
2. Settings → Pages → Source: `docs/` folder
3. Add `ANTHROPIC_API_KEY` to repo Secrets
4. The workflow at `.github/workflows/scan.yml` runs daily at 8 AM UTC

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...      # Required for AI analysis
AI_OPS_MODEL=claude-sonnet-4-6    # Optional model override
AI_OPS_MODE=all                   # Default mode
AI_OPS_OUTPUT_DIR=docs            # Dashboard output directory
AI_OPS_DATA_DIR=data              # Scan JSON directory
```
