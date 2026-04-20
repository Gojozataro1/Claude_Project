# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

macOS AI Ops is a system health scanner for macOS. It collects system metrics (CPU, memory, disk, startup apps, security), sends them to Claude for analysis, and generates an HTML dashboard with prioritized recommendations. It also supports rollback snapshots and post-cleanup health checks.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure env
cp .env.example .env  # then set ANTHROPIC_API_KEY

# Run full scan (all modes: all, dev, ui, vulnerability)
python main.py
python main.py --mode dev
python main.py --mode vulnerability

# Skip Claude API (no ANTHROPIC_API_KEY needed)
python main.py --no-ai

# Rollback management
python main.py --list-snapshots
python main.py --rollback <SNAPSHOT_ID>
python main.py --purge <SNAPSHOT_ID>

# Post-cleanup health check only
python main.py --post-check
```

## Architecture

**Data flow:** `SkillRouter` (selects collectors by mode) → `collectors/` (gather raw metrics) → `ClaudeAnalyzer` (sends JSON to Claude API, gets prioritized suggestions back) → `data/latest_scan.json` + `DashboardGenerator` (renders Jinja2 HTML to `docs/`).

**Modes and profiles:** Each mode (`all`, `dev`, `ui`, `vulnerability`) maps to a JSON profile in `router/profiles/`. Profiles define which collectors run, the `analyzer_focus` string injected into Claude's prompt, and the dashboard layout. To add a new mode, add a profile JSON and extend `VALID_MODES` in `router/skill_router.py`.

**Claude integration** (`analyzer/claude_analyzer.py`): Uses prompt caching (`cache_control: ephemeral`) on the system prompt. The analyzer expects Claude to return strict JSON matching the output schema defined in `SYSTEM_PROMPT`. If JSON parsing fails, falls back to regex extraction, then to a neutral fallback result.

**Rollback** (`rollback/rollback_agent.py`): Snapshots are stored under `snapshots/<YYYY-MM-DD_HHMMSS>/` with a `manifest.json` and backed-up files. Snapshots are created by callers passing a list of `{original_path: ...}` action dicts — the agent backs up files before they are modified.

**Post-check** (`post_check/health_checker.py`): Standalone health verifier that checks core macOS processes, DNS, disk usage (flags ≥95%), system services, app integrity, and CPU/memory. Returns `ALL_CLEAR` or `ISSUES_FOUND`.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Claude API access |
| `AI_OPS_MODEL` | `claude-sonnet-4-6` | Claude model to use |
| `AI_OPS_MODE` | `all` | Default scan mode |
| `AI_OPS_OUTPUT_DIR` | `docs` | HTML dashboard output |
| `AI_OPS_DATA_DIR` | `data` | Scan JSON output |
| `AI_OPS_LARGE_FILE_THRESHOLD_MB` | (collector default) | Flag large files above this size |
| `AI_OPS_OLD_FILE_DAYS` | (collector default) | Flag files not touched in N days |

## Key Design Decisions

- `ClaudeAnalyzer` caches the system prompt (contains all scoring rules) via `cache_control: ephemeral` to reduce token costs on repeated scans.
- The dashboard HTML is written to `docs/` so it can be served directly via GitHub Pages.
- Collectors are gated by `router.get_active_collectors()` — never run collectors directly without going through `SkillRouter`.
